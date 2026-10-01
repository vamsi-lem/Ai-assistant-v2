"""
Who is signed in, and the team.

    GET   /api/me            the caller's own profile
    GET   /api/team          every member (any signed in role; the assign and
                             book screens need the counsellor list)
    POST  /api/team/invite   admin: Supabase emails an invitation, the person
                             sets a password from it, the trigger in
                             migration 0003 creates their profile
    PATCH /api/team/{id}     admin: role, active, name
    DELETE /api/team/{id}    admin: remove the login entirely (their leads go
                             back to the incoming queue; deactivate instead
                             when someone leaves and their history should
                             keep their name)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from ..auth import ROLES, CurrentUser, forget_profile, load_profile, require_admin, require_user
from ..config import get_settings
from ..db import db, execute, get_by_id, update_by_id
from ..schemas import ProfileOut

logger = logging.getLogger("backend.team")

router = APIRouter(prefix="/api", tags=["team"])


@router.get("/me", response_model=ProfileOut)
async def me(user: CurrentUser = Depends(require_user)) -> ProfileOut:
    # Every sign in starts here, so read the row fresh and refresh the cache:
    # whatever the dashboard shows as "your role" is what the backend will
    # enforce on the requests that follow.
    current = await load_profile(user.id, fresh=True)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    if not current.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")
    row = await get_by_id("profiles", user.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return ProfileOut(**row)


@router.get("/team", response_model=list[ProfileOut], dependencies=[Depends(require_user)])
async def list_team() -> list[ProfileOut]:
    result = await execute(db().table("profiles").select("*").order("name"))
    return [ProfileOut(**row) for row in (result.data or [])]


class InviteIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: str = "counsellor"


@router.post("/team/invite", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def invite(payload: InviteIn, admin: CurrentUser = Depends(require_admin)) -> ProfileOut:
    if payload.role not in ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Role must be one of {', '.join(ROLES)}.")

    email = payload.email.lower()
    existing = await execute(db().table("profiles").select("id").eq("email", email).maybe_single())
    if existing and existing.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already on the team.")

    settings = get_settings()
    redirect_to = f"{settings.frontend_base_url}/set-password"

    try:
        response = await db().auth.admin.invite_user_by_email(
            email,
            {"data": {"name": payload.name.strip(), "role": payload.role}, "redirect_to": redirect_to},
        )
    except Exception as exc:  # noqa: BLE001 - surface Supabase's own words
        message = str(exc)
        logger.warning("Invite failed for %s: %s", email, message)
        hint = ""
        lowered = message.lower()
        if "rate limit" in lowered or ("email" in lowered and "limit" in lowered):
            hint = " Supabase's built in mailer allows only a few emails an hour; set custom SMTP under Authentication > Emails for a real team."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Supabase refused the invitation: {message}.{hint}")

    user_id = str(response.user.id) if response and response.user else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Supabase sent no user id back for the invitation.")

    # The trigger normally creates the profile. Upsert anyway so a missing
    # trigger cannot leave a user without a role.
    row = await execute(
        db()
        .table("profiles")
        .upsert({"id": user_id, "email": email, "name": payload.name.strip(), "role": payload.role, "active": True})
    )
    profile = row.data[0] if row.data else await get_by_id("profiles", user_id)
    logger.info("Invited %s as %s (by %s)", email, payload.role, admin.email)
    return ProfileOut(**profile)


class MemberPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)


@router.patch("/team/{member_id}", response_model=ProfileOut)
async def update_member(member_id: str, payload: MemberPatch, admin: CurrentUser = Depends(require_admin)) -> ProfileOut:
    patch: dict = {}
    if payload.role is not None:
        if payload.role not in ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Role must be one of {', '.join(ROLES)}.")
        if member_id == admin.id and payload.role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role.")
        patch["role"] = payload.role
    if payload.active is not None:
        if member_id == admin.id and not payload.active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate yourself.")
        patch["active"] = payload.active
    if payload.name is not None:
        patch["name"] = payload.name.strip()
    if not patch:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nothing to change.")

    updated = await update_by_id("profiles", member_id, patch)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    forget_profile(member_id)
    return ProfileOut(**updated)


@router.delete("/team/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(member_id: str, admin: CurrentUser = Depends(require_admin)) -> None:
    if member_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account.")
    member = await get_by_id("profiles", member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    # Removing the auth user cascades to the profile (migration 0003). Leads,
    # notes, events and bookings that pointed at them keep their rows and
    # lose the pointer (on delete set null), so nothing else disappears.
    try:
        await db().auth.admin.delete_user(member_id)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "not found" in message.lower():
            # Auth user already gone; drop the orphaned profile ourselves.
            await execute(db().table("profiles").delete().eq("id", member_id))
        else:
            logger.warning("Delete failed for %s: %s", member.get("email"), message)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Supabase refused the deletion: {message}")
    forget_profile(member_id)
    logger.info("Deleted team member %s (by %s)", member.get("email"), admin.email)
