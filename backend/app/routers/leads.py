"""
Leads: intake from the public form, and everything the dashboard does with
them afterwards.

The ordering rule that must not be broken: the lead is written to the
database BEFORE any call is attempted. A carrier outage, a compliance block
or a bad number must never cost you the lead.

Public (no login):
  POST  /api/leads                 the enquiry form; saves, then Maya calls

Agent (shared secret):
  PATCH /api/leads/{id}/callback   callback time, notes, chosen language

Dashboard (signed in; counsellors see only leads assigned to them):
  GET   /api/leads                 list, with filters and paging
  GET   /api/leads/{id}            one lead
  GET   /api/leads/{id}/detail     lead + calls + transcripts + bookings + notes + timeline
  PATCH /api/leads/{id}            stage (editors), assigned_to (managers)
  POST  /api/leads/{id}/notes      add a note
  POST  /api/leads/{id}/call       ring them again, same rules as the form
  POST  /api/leads/manual          add a lead by hand; no automatic call
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .. import throttle
from ..auth import CurrentUser, require_editor, require_user
from ..config import get_settings
from ..db import db, execute, get_by_id, insert_one, update_by_id
from ..deps import client_ip, require_agent_key
from ..schemas import (
    BookingRow,
    BrowserJoin,
    CallDetailOut,
    CallOut,
    EventOut,
    LeadCallbackUpdate,
    LeadCreate,
    LeadCreateResponse,
    LeadDetailOut,
    LeadOut,
    LeadPage,
    LeadPatch,
    ManualLeadCreate,
    NoteCreate,
    NoteOut,
)
from ..services import calling, events
from ..services.scope import assert_can_see, scope_leads

logger = logging.getLogger("backend.leads")
router = APIRouter(prefix="/api/leads", tags=["leads"])

STAGES = ("new", "contacted", "qualified", "appointment", "converted", "lost")


def _db_failure(exc: Exception, what: str) -> HTTPException:
    text = str(exc) or type(exc).__name__
    logger.exception("%s failed: %s", what, text)
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{what} failed: {text[:300]}")


async def _overview(lead_id: str) -> dict | None:
    """The lead with its computed columns, from the lead_overview view."""
    result = await execute(db().table("lead_overview").select("*").eq("id", lead_id).maybe_single())
    return result.data if result and result.data else None


def _append_note(existing: str | None, addition: str) -> str:
    current = (existing or "").strip()
    return f"{current}\n{addition}".strip() if current else addition


def _person(row: dict, key: str) -> str | None:
    """Name out of an embedded profiles row, when PostgREST joined one."""
    who = row.get(key)
    return who.get("name") if isinstance(who, dict) else None


# ---------------------------------------------------------------------------
# Public form
# ---------------------------------------------------------------------------


@router.post("", response_model=LeadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadCreate, request: Request) -> LeadCreateResponse:
    settings = get_settings()

    # ---- 0. One brake before anything is written. ------------------------
    # A flood from one address is not a set of leads, so it is refused before
    # the database is touched. Real people never reach this limit.
    if not throttle.check_ip(client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many submissions from this connection. Please try again in an hour.",
        )

    # ---- 1. Save the lead. Always. ---------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    lead_row = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "product_or_course": payload.product_or_course,
        "notes": payload.notes,
        "source": "form",
        "status": "new",
        "stage": "new",
        "consent_given": payload.consent_given,
        # Consent evidence is written at the same instant as the lead so the
        # two can never disagree.
        "consent_at": now if payload.consent_given else None,
        "consent_ip": client_ip(request) if payload.consent_given else None,
        "consent_text": payload.consent_text if payload.consent_given else None,
    }
    try:
        lead = await insert_one("leads", lead_row)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Saving the lead") from exc

    lead_id = lead["id"]
    logger.info("Lead %s saved (%s, %s)", lead_id, payload.name, payload.product_or_course)
    await events.record(lead_id, "lead_created", "via the website form", data={"source": "form"})

    # ---- 2. No consent means no call. Stop here, cleanly. -----------------
    if not payload.consent_given:
        logger.info("Lead %s has no consent. Saved, not called.", lead_id)
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=None,
            call_skipped_reason="Saved, but no call was placed because consent was not given.",
        )

    # ---- 2b. Same number called minutes ago: keep the lead, skip the call. --
    try:
        last = await throttle.recent_call_to(payload.phone)
    except Exception:  # noqa: BLE001
        logger.exception("Phone cooldown lookup failed; proceeding without it")
        last = None
    if last is not None:
        minutes_ago = max(1, int((datetime.now(timezone.utc) - last).total_seconds() // 60))
        reason = (
            f"Saved, but not called: this number was already called {minutes_ago} minute(s) ago. "
            f"A second call is allowed after {settings.lead_phone_cooldown_minutes} minutes."
        )
        logger.info("Lead %s not called: %s", lead_id, reason)
        note = "[system] Repeat submission inside the call cooldown; not called again."
        lead = await update_by_id("leads", lead_id, {"notes": _append_note(lead.get("notes"), note)}) or lead
        return LeadCreateResponse(lead=LeadOut(**lead), call=None, call_skipped_reason=reason)

    # ---- 3. Call. ----------------------------------------------------------
    placed = await calling.place_call(lead, trigger="form")
    return LeadCreateResponse(
        lead=LeadOut(**lead),
        call=CallOut(**placed.call) if placed.call else None,
        join=BrowserJoin(**placed.join) if placed.join else None,
        call_skipped_reason=placed.skipped_reason,
    )


# ---------------------------------------------------------------------------
# Dashboard: add a lead by hand
# ---------------------------------------------------------------------------


@router.post("/manual", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_manual_lead(payload: ManualLeadCreate, user: CurrentUser = Depends(require_editor)) -> LeadOut:
    """
    A walk in, a phone enquiry, a name from a client's list. Saved with
    source "manual" and never auto called: the counsellor presses Call again
    on the lead page once the person has agreed to it.
    """
    if user.role == "counsellor":
        # A counsellor adding a lead keeps it; they cannot hand it to others.
        assigned_to: str | None = user.id
    else:
        assigned_to = payload.assigned_to or None
        if assigned_to:
            who = await get_by_id("profiles", assigned_to)
            if not who or not who.get("active"):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That team member does not exist or is deactivated.")

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "product_or_course": payload.product_or_course,
        "notes": payload.notes,
        "source": "manual",
        "status": "new",
        "stage": "new",
        "assigned_to": assigned_to,
        "consent_given": payload.consent_given,
        "consent_at": now if payload.consent_given else None,
        "consent_text": payload.consent_text if payload.consent_given else None,
    }
    try:
        lead = await insert_one("leads", row)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Saving the lead") from exc

    await events.record(lead["id"], "lead_created", f"added by {user.name}", data={"source": "manual"}, actor_id=user.id)
    if assigned_to:
        await events.record(lead["id"], "assigned", "assigned on creation", data={"assigned_to": assigned_to}, actor_id=user.id)
    logger.info("Lead %s added by hand by %s", lead["id"], user.email)
    return LeadOut(**(await _overview(lead["id"]) or lead))


# ---------------------------------------------------------------------------
# Dashboard: reads
# ---------------------------------------------------------------------------


@router.get("", response_model=LeadPage)
async def list_leads(
    user: CurrentUser = Depends(require_user),
    stage: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None, description="a profile id, or 'unassigned'"),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> LeadPage:
    query = db().table("lead_overview").select("*", count="exact")
    query = scope_leads(query, user)
    if stage:
        if stage not in STAGES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown stage {stage!r}.")
        query = query.eq("stage", stage)
    if assigned_to == "unassigned":
        query = query.is_("assigned_to", "null")
    elif assigned_to:
        query = query.eq("assigned_to", assigned_to)
    if source:
        query = query.eq("source", source)
    if search:
        # Commas and parentheses would break the PostgREST filter grammar.
        term = "".join(ch for ch in search.strip() if ch not in ",()")
        if term:
            query = query.or_(
                f"name.ilike.%{term}%,phone.ilike.%{term}%,product_or_course.ilike.%{term}%,email.ilike.%{term}%"
            )
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    try:
        result = await execute(query)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Loading leads") from exc

    return LeadPage(items=[LeadOut(**row) for row in (result.data or [])], total=result.count or 0)


@router.get("/{lead_id}", response_model=LeadOut)
async def read_lead(lead_id: str, user: CurrentUser = Depends(require_user)) -> LeadOut:
    lead = await _overview(lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)
    return LeadOut(**lead)


@router.get("/{lead_id}/detail", response_model=LeadDetailOut)
async def lead_detail(lead_id: str, user: CurrentUser = Depends(require_user)) -> LeadDetailOut:
    lead = await _overview(lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    try:
        calls_res = await execute(
            db().table("call_overview").select("*").eq("lead_id", lead_id).order("created_at", desc=True)
        )
        calls = calls_res.data or []
        transcripts: dict[str, list] = {}
        call_ids = [c["id"] for c in calls]
        if call_ids:
            conv_res = await execute(db().table("conversations").select("call_id,messages").in_("call_id", call_ids))
            for row in conv_res.data or []:
                transcripts[row["call_id"]] = row.get("messages") or []

        bookings_res = await execute(
            db().table("upcoming_bookings").select("*").eq("lead_id", lead_id).order("scheduled_at", desc=True)
        )
        notes_res = await execute(
            db().table("lead_notes").select("*, author:profiles(name)").eq("lead_id", lead_id).order("created_at", desc=True)
        )
        events_res = await execute(
            db().table("lead_events").select("*, actor:profiles(name)").eq("lead_id", lead_id).order("created_at", desc=True).limit(200)
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Loading the lead") from exc

    return LeadDetailOut(
        lead=LeadOut(**lead),
        calls=[CallDetailOut(**c, transcript=transcripts.get(c["id"], [])) for c in calls],
        bookings=[BookingRow(**b) for b in (bookings_res.data or [])],
        notes=[NoteOut(**{**n, "author_name": _person(n, "author")}) for n in (notes_res.data or [])],
        events=[EventOut(**{**e, "actor_name": _person(e, "actor")}) for e in (events_res.data or [])],
    )


# ---------------------------------------------------------------------------
# Dashboard: writes
# ---------------------------------------------------------------------------


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: str, payload: LeadPatch, user: CurrentUser = Depends(require_editor)) -> LeadOut:
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    patch: dict = {}

    if payload.stage is not None and payload.stage != lead.get("stage"):
        if payload.stage not in STAGES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown stage {payload.stage!r}.")
        patch["stage"] = payload.stage

    if "assigned_to" in payload.model_fields_set:
        if not user.is_one_of("admin", "manager"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and managers assign leads.")
        if payload.assigned_to:
            who = await get_by_id("profiles", payload.assigned_to)
            if not who or not who.get("active"):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That team member does not exist or is deactivated.")
        if payload.assigned_to != lead.get("assigned_to"):
            patch["assigned_to"] = payload.assigned_to

    if not patch:
        return LeadOut(**(await _overview(lead_id) or lead))

    try:
        await update_by_id("leads", lead_id, patch)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Updating the lead") from exc

    if "stage" in patch:
        await events.record(
            lead_id,
            "stage_changed",
            f"{str(lead.get('stage') or 'new').capitalize()} to {patch['stage'].capitalize()}",
            data={"from": lead.get("stage"), "to": patch["stage"]},
            actor_id=user.id,
        )
    if "assigned_to" in patch:
        name = None
        if patch["assigned_to"]:
            who = await get_by_id("profiles", patch["assigned_to"])
            name = who.get("name") if who else None
        await events.record(
            lead_id,
            "assigned",
            f"to {name}" if name else "moved back to the incoming queue",
            data={"assigned_to": patch["assigned_to"]},
            actor_id=user.id,
        )

    return LeadOut(**(await _overview(lead_id) or {**lead, **patch}))


@router.post("/{lead_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(lead_id: str, payload: NoteCreate, user: CurrentUser = Depends(require_editor)) -> NoteOut:
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    try:
        note = await insert_one("lead_notes", {"lead_id": lead_id, "author_id": user.id, "body": payload.body.strip()})
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc, "Saving the note") from exc

    await events.record(lead_id, "note_added", payload.body.strip()[:120], actor_id=user.id)
    return NoteOut(**note, author_name=user.name)


@router.post("/{lead_id}/call", response_model=LeadCreateResponse)
async def call_again(lead_id: str, user: CurrentUser = Depends(require_editor)) -> LeadCreateResponse:
    """
    Ring the lead again. Same consent gate, same compliance checks and the
    same cooldown as the public form; the only difference is who asked.
    """
    settings = get_settings()
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    live = await execute(
        db().table("calls").select("id").eq("lead_id", lead_id).in_("status", ["queued", "ringing", "in-progress"]).limit(1)
    )
    if live.data:
        return LeadCreateResponse(lead=LeadOut(**lead), call=None, call_skipped_reason="A call to this lead is already in progress.")

    try:
        last = await throttle.recent_call_to(lead["phone"])
    except Exception:  # noqa: BLE001
        last = None
    if last is not None:
        minutes_ago = max(1, int((datetime.now(timezone.utc) - last).total_seconds() // 60))
        return LeadCreateResponse(
            lead=LeadOut(**lead),
            call=None,
            call_skipped_reason=(
                f"This number was called {minutes_ago} minute(s) ago. "
                f"Another call is allowed after {settings.lead_phone_cooldown_minutes} minutes."
            ),
        )

    placed = await calling.place_call(lead, actor_id=user.id, trigger=f"call again by {user.name}")
    return LeadCreateResponse(
        lead=LeadOut(**(await _overview(lead_id) or lead)),
        call=CallOut(**placed.call) if placed.call else None,
        join=BrowserJoin(**placed.join) if placed.join else None,
        call_skipped_reason=placed.skipped_reason,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@router.patch("/{lead_id}/callback", response_model=LeadOut, dependencies=[Depends(require_agent_key)])
async def save_callback(lead_id: str, payload: LeadCallbackUpdate) -> LeadOut:
    """
    The agent calls this the moment the lead names a callback time, or
    chooses a language, not at the end of the call. If the line drops ten
    seconds later, the fact is already saved.
    """
    lead = await get_by_id("leads", lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    changes: dict = {}
    lines: list[str] = []
    if payload.callback_time and payload.callback_time.strip():
        lines.append(f"Callback requested: {payload.callback_time.strip()}")
    if payload.callback_notes and payload.callback_notes.strip():
        lines.append(f"Asked on the call: {payload.callback_notes.strip()}")
    if lines:
        stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
        addition = f"[Maya {stamp}] " + " | ".join(lines)
        changes["notes"] = _append_note(lead.get("notes"), addition)
        changes["status"] = "contacted"
        if lead.get("stage") == "new":
            changes["stage"] = "contacted"
    if payload.preferred_language and payload.preferred_language != lead.get("preferred_language"):
        changes["preferred_language"] = payload.preferred_language

    if changes:
        lead = await update_by_id("leads", lead_id, changes) or lead
        if lines:
            await events.record(lead_id, "callback_noted", " | ".join(lines))

    logger.info("Lead %s callback saved: %s", lead_id, list(changes))
    return LeadOut(**lead)
