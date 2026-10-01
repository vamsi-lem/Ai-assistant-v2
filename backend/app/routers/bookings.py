"""
Counsellor slot bookings.

Three steps happen when a slot is booked, in this order, and each later
step failing never undoes an earlier one:

  1. Save the booking. Always. The counsellor can see it and act on it even
     if nothing else below works.
  2. Create the meeting link (Zoom or Google Meet), if a provider is set.
  3. Send the WhatsApp confirmation with the link, if a provider is set.

Every failure is written onto the booking row (meeting_error,
whatsapp_error) and shown on the lead page, so a missing link or an unsent
message is a visible task for a human, never a silent gap.

The same `_book` function serves Maya on a call and a counsellor on the
Appointments page, so both paths behave identically.

Endpoints:
  POST /api/bookings                    agent        book a slot
  GET  /api/bookings                    dashboard    list upcoming (and recent past)
  GET  /api/bookings/availability       dashboard    free slots for a counsellor on a day
  POST /api/bookings/dashboard          dashboard    book a slot from the Appointments page
  POST /api/bookings/{id}/resend        dashboard    resend the WhatsApp
  POST /api/bookings/{id}/status        dashboard    mark completed / cancelled / no_show
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth import CurrentUser, require_editor, require_user
from ..config import get_settings
from ..db import db, execute, get_by_id, insert_one, update_by_id
from ..deps import require_agent_key
from ..schemas import (
    AvailabilityOut,
    BookingCreate,
    BookingCreateResponse,
    BookingOut,
    BookingRow,
    DashboardBookingCreate,
)
from ..services import events
from ..services.meetings import service as meetings
from ..services.meetings.base import MeetingError, MeetingNotConfigured
from ..services.scope import assert_can_see
from ..services.whatsapp import service as whatsapp
from ..services.whatsapp.meta import WhatsAppError, WhatsAppNotConfigured

logger = logging.getLogger("backend.bookings")
router = APIRouter(prefix="/api/bookings", tags=["bookings"])

# A slot must be at least this far ahead and at most this far out. Outside
# that, the brain almost certainly misread the time and must ask again.
MIN_AHEAD = timedelta(minutes=10)
MAX_AHEAD = timedelta(days=60)

MIGRATION_HINT = (
    "The bookings table is missing or unreadable. Run "
    "supabase/migrations/0002_bookings.sql in the Supabase SQL editor, then retry."
)


def _db_failure(exc: Exception) -> HTTPException:
    """
    A database error as a proper 503, not a crash.

    A crash (500) leaves the response without CORS headers, so the browser
    reports it as a CORS error and the real cause is hidden. A 503 with the
    cause in `detail` reaches the page and the person reading it.
    """
    text = str(exc) or getattr(exc, "message", "") or ""
    kind = type(exc).__name__
    if "bookings" in text or "PGRST205" in text or "does not exist" in text:
        detail = f"{MIGRATION_HINT} (database said: {text[:200]})"
    elif "Timeout" in kind or "Connect" in kind or "timed out" in text.lower():
        detail = (
            f"Could not reach Supabase ({kind}) after three attempts. Check the connection, "
            "then try again. If the Supabase project was paused for inactivity, open it in the dashboard to wake it."
        )
    else:
        detail = f"Database error ({kind}): {text[:300]}"
    logger.exception("Bookings database failure (%s): %s", kind, text)
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


def _zone():
    """Booking timezone; fixed +05:30 if tzdata is missing on Windows."""
    try:
        return ZoneInfo(get_settings().booking_timezone)
    except (ZoneInfoNotFoundError, ModuleNotFoundError):
        logger.warning(
            "Timezone %s not found (pip install tzdata). Using fixed +05:30.",
            get_settings().booking_timezone,
        )
        return timezone(timedelta(hours=5, minutes=30), "IST")


def spoken_time(when: datetime) -> str:
    """'Tuesday, 22 September at 6 pm' in the booking timezone."""
    local = when.astimezone(_zone())
    hour = local.strftime("%I").lstrip("0") or "12"
    minute = local.strftime("%M")
    ampm = local.strftime("%p").lower()
    clock = f"{hour} {ampm}" if minute == "00" else f"{hour}:{minute} {ampm}"
    return f"{local.strftime('%A')}, {local.day} {local.strftime('%B')} at {clock}"


def _normalise(when: datetime) -> datetime:
    """Naive means booking timezone. Everything is stored in UTC."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=_zone())
    return when.astimezone(timezone.utc)


def _check_window(when: datetime) -> None:
    now = datetime.now(timezone.utc)
    if when < now + MIN_AHEAD:
        # The detail is written for the brain: it becomes the tool result.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"That time ({spoken_time(when)}) is already past or too soon. "
                "Ask for a time at least a little later today, or another day."
            ),
        )
    if when > now + MAX_AHEAD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{spoken_time(when)} is more than two months away. Confirm the date.",
        )


def _append_note(existing: str | None, addition: str) -> str:
    current = (existing or "").strip()
    return f"{current}\n{addition}".strip() if current else addition


# ---------------------------------------------------------------------------
# The one booking path
# ---------------------------------------------------------------------------


class Booked:
    def __init__(self, booking: dict[str, Any], said: str, link_status: str) -> None:
        self.booking = booking
        self.said = said
        self.link_status = link_status


async def _book(
    lead: dict[str, Any],
    when: datetime,
    *,
    call_id: str | None,
    counsellor_id: str | None,
    requested_text: str | None,
    notes: str | None,
    meeting_platform: str | None,
    want_video: bool,
    actor_id: str | None,
    booked_by: str,
) -> Booked:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # ---- 1. Save. Always. --------------------------------------------------
    try:
        booking = await insert_one(
            "bookings",
            {
                "lead_id": lead["id"],
                "call_id": call_id,
                "counsellor_id": counsellor_id,
                "scheduled_at": when.isoformat(),
                "timezone": settings.booking_timezone,
                "duration_minutes": settings.booking_duration_minutes,
                "requested_text": requested_text,
                "notes": notes,
                "whatsapp_status": "pending",
                "status": "booked",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    booking_id = booking["id"]
    said = spoken_time(when)
    logger.info("Booking %s saved: %s for lead %s by %s", booking_id, said, lead["id"], booked_by)

    # Keep the lead record in step with what the counsellor already reads.
    stamp = now.strftime("%d %b %Y %H:%M UTC")
    lines = [f"Slot booked: {said}"]
    if notes:
        lines.append(f"Asked: {notes.strip()}")
    addition = f"[{booked_by} {stamp}] " + " | ".join(lines)
    lead_patch: dict[str, Any] = {"notes": _append_note(lead.get("notes"), addition), "status": "contacted"}
    if lead.get("stage") in (None, "new", "contacted", "qualified"):
        lead_patch["stage"] = "appointment"
    await update_by_id("leads", lead["id"], lead_patch)
    await events.record(lead["id"], "booking_created", said, data={"booking_id": booking_id}, actor_id=actor_id)

    # ---- 2. Meeting link -------------------------------------------------
    patch: dict[str, Any] = {}
    meeting_url: str | None = None
    meeting_label: str | None = None
    platform_note: str | None = None
    if want_video and meetings.enabled():
        try:
            link, platform_note = await meetings.create_meeting(
                topic=f"{settings.company_name}: {lead['product_or_course']} counselling with {lead['name']}",
                start=when,
                duration_minutes=settings.booking_duration_minutes,
                timezone=settings.booking_timezone,
                invitee_email=lead.get("email"),
                platform=meeting_platform,
            )
            meeting_url = link.url
            meeting_label = meetings.LABELS.get(link.provider, link.provider)
            patch.update({"meeting_provider": link.provider, "meeting_url": link.url, "meeting_id": link.meeting_id})
            if platform_note:
                logger.info("Booking %s: %s", booking_id, platform_note)
        except (MeetingNotConfigured, MeetingError) as exc:
            logger.warning("Booking %s: no meeting link: %s", booking_id, exc)
            patch["meeting_error"] = str(exc)[:500]
        except Exception as exc:  # noqa: BLE001
            logger.exception("Booking %s: meeting link failed", booking_id)
            patch["meeting_error"] = f"Unexpected: {exc}"[:500]
    elif want_video:
        patch["meeting_error"] = "No meeting provider configured (MEETING_PROVIDER=none)"
    else:
        patch["meeting_provider"] = "phone"

    # ---- 3. WhatsApp -----------------------------------------------------
    if whatsapp.enabled():
        try:
            message_id = await whatsapp.send_booking_confirmation(
                to_number=lead["phone"],
                lead_name=lead["name"],
                course=lead["product_or_course"],
                when_text=said,
                meeting_url=meeting_url,
            )
            patch.update(
                {
                    "whatsapp_status": "sent",
                    "whatsapp_message_id": message_id,
                    "whatsapp_sent_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await events.record(lead["id"], "whatsapp_sent", "booking confirmation", data={"booking_id": booking_id})
        except (WhatsAppNotConfigured, WhatsAppError) as exc:
            logger.warning("Booking %s: WhatsApp not sent: %s", booking_id, exc)
            patch.update({"whatsapp_status": "failed", "whatsapp_error": str(exc)[:500]})
            await events.record(lead["id"], "whatsapp_failed", str(exc)[:200], data={"booking_id": booking_id})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Booking %s: WhatsApp failed", booking_id)
            patch.update({"whatsapp_status": "failed", "whatsapp_error": f"Unexpected: {exc}"[:500]})
            await events.record(lead["id"], "whatsapp_failed", str(exc)[:200], data={"booking_id": booking_id})
    else:
        patch.update({"whatsapp_status": "skipped", "whatsapp_error": "No WhatsApp provider configured"})

    booking = await update_by_id("bookings", booking_id, patch) or {**booking, **patch}

    # What Maya tells the lead. Honest about what actually happened.
    sent = booking.get("whatsapp_status") == "sent"
    if meeting_url and sent:
        link_status = f"The {meeting_label} link has been sent to their WhatsApp. Tell them so, naming {meeting_label}."
    elif meeting_url:
        link_status = f"A {meeting_label} link was created but the WhatsApp could not be sent. Say the counsellor will share the link before the call."
    elif sent:
        link_status = "A WhatsApp confirmation was sent. There is no video link; the counsellor will call them on this number."
    else:
        link_status = "No message could be sent right now. Say the counsellor will confirm the details before the call."
    if platform_note:
        link_status = f"{platform_note} {link_status}"

    return Booked(booking, said, link_status)


# ---------------------------------------------------------------------------
# The agent books a slot
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=BookingCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_agent_key)],
)
async def create_booking(payload: BookingCreate) -> BookingCreateResponse:
    lead = await get_by_id("leads", payload.lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    when = _normalise(payload.scheduled_at)
    _check_window(when)

    done = await _book(
        lead,
        when,
        call_id=payload.call_id,
        # Maya books with whoever owns the lead; unassigned stays open for the manager.
        counsellor_id=lead.get("assigned_to"),
        requested_text=payload.requested_text,
        notes=payload.notes,
        meeting_platform=payload.meeting_platform,
        want_video=True,
        actor_id=None,
        booked_by="Maya",
    )
    return BookingCreateResponse(booking=BookingOut(**done.booking), spoken_time=done.said, link_status=done.link_status)


# ---------------------------------------------------------------------------
# The dashboard
# ---------------------------------------------------------------------------


@router.get("", response_model=list[BookingRow])
async def list_bookings(
    user: CurrentUser = Depends(require_user),
    days_back: int = Query(default=1, ge=0, le=90),
    days_ahead: int = Query(default=30, ge=1, le=365),
) -> list[BookingRow]:
    """Upcoming bookings plus the recent past, oldest first."""
    now = datetime.now(timezone.utc)
    query = (
        db()
        .table("upcoming_bookings")
        .select("*")
        .gte("scheduled_at", (now - timedelta(days=days_back)).isoformat())
        .lte("scheduled_at", (now + timedelta(days=days_ahead)).isoformat())
        .order("scheduled_at")
    )
    try:
        result = await execute(query)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    rows = result.data or []
    if not user.sees_all_leads:
        # The view carries the counsellor, not the lead's assignee; a
        # counsellor sees sessions booked with them.
        rows = [r for r in rows if r.get("counsellor_id") == user.id]
    return [BookingRow(**row) for row in rows]


def _slot_grid(day_local: datetime) -> list[str]:
    """Every start time in working hours on that day, as HH:MM."""
    settings = get_settings()
    step = max(5, settings.booking_duration_minutes)
    out: list[str] = []
    minutes = settings.counsellor_work_start * 60
    end = settings.counsellor_work_end * 60
    while minutes + step <= end:
        out.append(f"{minutes // 60:02d}:{minutes % 60:02d}")
        minutes += step
    return out


@router.get("/availability", response_model=AvailabilityOut)
async def availability(
    counsellor_id: str = Query(...),
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: CurrentUser = Depends(require_user),
) -> AvailabilityOut:
    """
    Free slots for one counsellor on one day, in the booking timezone.
    Working hours and slot length come from the backend settings; taken
    slots are that counsellor's booked sessions on that day; past slots on
    today are dropped.
    """
    settings = get_settings()
    zone = _zone()
    try:
        day_local = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=zone)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date must be YYYY-MM-DD")

    if day_local.isoweekday() not in settings.counsellor_work_days:
        return AvailabilityOut(date=date, slots=[], taken=[], slot_minutes=settings.booking_duration_minutes, timezone=settings.booking_timezone)

    start_utc = day_local.astimezone(timezone.utc)
    end_utc = (day_local + timedelta(days=1)).astimezone(timezone.utc)
    try:
        result = await execute(
            db()
            .table("bookings")
            .select("scheduled_at,duration_minutes")
            .eq("counsellor_id", counsellor_id)
            .eq("status", "booked")
            .gte("scheduled_at", start_utc.isoformat())
            .lt("scheduled_at", end_utc.isoformat())
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc

    taken: set[str] = set()
    for row in result.data or []:
        at = datetime.fromisoformat(str(row["scheduled_at"]).replace("Z", "+00:00")).astimezone(zone)
        taken.add(at.strftime("%H:%M"))

    earliest = datetime.now(timezone.utc) + MIN_AHEAD
    slots: list[str] = []
    for hhmm in _slot_grid(day_local):
        hour, minute = (int(part) for part in hhmm.split(":"))
        at = day_local.replace(hour=hour, minute=minute)
        if at.astimezone(timezone.utc) < earliest:
            continue
        if hhmm in taken:
            continue
        slots.append(hhmm)

    return AvailabilityOut(
        date=date,
        slots=slots,
        taken=sorted(taken),
        slot_minutes=settings.booking_duration_minutes,
        timezone=settings.booking_timezone,
    )


@router.post("/dashboard", response_model=BookingRow, status_code=status.HTTP_201_CREATED)
async def create_booking_from_dashboard(payload: DashboardBookingCreate, user: CurrentUser = Depends(require_editor)) -> BookingRow:
    """A counsellor or manager books from the Appointments page. Same path as Maya."""
    lead = await get_by_id("leads", payload.lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    counsellor = await get_by_id("profiles", payload.counsellor_id)
    if not counsellor or not counsellor.get("active"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That counsellor does not exist or is deactivated.")

    try:
        when_local = datetime.strptime(f"{payload.date} {payload.time}", "%Y-%m-%d %H:%M").replace(tzinfo=_zone())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date must be YYYY-MM-DD and time HH:MM")
    when = when_local.astimezone(timezone.utc)
    _check_window(when)

    # The slot must still be free for that counsellor.
    clash = await execute(
        db().table("bookings").select("id").eq("counsellor_id", payload.counsellor_id).eq("status", "booked").eq("scheduled_at", when.isoformat()).limit(1)
    )
    if clash.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{counsellor['name']} already has a session at {spoken_time(when)}.")

    done = await _book(
        lead,
        when,
        call_id=None,
        counsellor_id=payload.counsellor_id,
        requested_text=None,
        notes=payload.notes,
        meeting_platform=None,
        want_video=payload.mode == "video",
        actor_id=user.id,
        booked_by=user.name,
    )
    row = await execute(db().table("upcoming_bookings").select("*").eq("id", done.booking["id"]).maybe_single())
    return BookingRow(**(row.data if row and row.data else {**done.booking, "lead_name": lead["name"], "lead_phone": lead["phone"], "product_or_course": lead["product_or_course"], "counsellor_name": counsellor["name"]}))


@router.post("/{booking_id}/resend", response_model=BookingOut)
async def resend_whatsapp(booking_id: str, user: CurrentUser = Depends(require_editor)) -> BookingOut:
    """Try the WhatsApp again, for example after the template was approved."""
    try:
        booking = await get_by_id("bookings", booking_id)
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    lead = await get_by_id("leads", booking["lead_id"])
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    assert_can_see(lead, user)

    when = datetime.fromisoformat(str(booking["scheduled_at"]).replace("Z", "+00:00"))
    try:
        message_id = await whatsapp.send_booking_confirmation(
            to_number=lead["phone"],
            lead_name=lead["name"],
            course=lead["product_or_course"],
            when_text=spoken_time(when),
            meeting_url=booking.get("meeting_url"),
        )
        patch = {
            "whatsapp_status": "sent",
            "whatsapp_message_id": message_id,
            "whatsapp_error": None,
            "whatsapp_sent_at": datetime.now(timezone.utc).isoformat(),
        }
        await events.record(lead["id"], "whatsapp_sent", "resent by hand", data={"booking_id": booking_id}, actor_id=user.id)
    except (WhatsAppNotConfigured, WhatsAppError) as exc:
        patch = {"whatsapp_status": "failed", "whatsapp_error": str(exc)[:500]}
        await events.record(lead["id"], "whatsapp_failed", str(exc)[:200], data={"booking_id": booking_id}, actor_id=user.id)

    updated = await update_by_id("bookings", booking_id, patch) or {**booking, **patch}
    return BookingOut(**updated)


class BookingStatusUpdate(BaseModel):
    status: str


@router.post("/{booking_id}/status", response_model=BookingOut)
async def set_status(booking_id: str, payload: BookingStatusUpdate, user: CurrentUser = Depends(require_editor)) -> BookingOut:
    if payload.status not in ("booked", "cancelled", "completed", "no_show"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status.")
    booking = await get_by_id("bookings", booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    lead = await get_by_id("leads", booking["lead_id"])
    if lead:
        assert_can_see(lead, user)
    try:
        updated = await update_by_id("bookings", booking_id, {"status": payload.status})
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    await events.record(booking["lead_id"], "booking_updated", payload.status.replace("_", " "), data={"booking_id": booking_id}, actor_id=user.id)
    return BookingOut(**updated)

