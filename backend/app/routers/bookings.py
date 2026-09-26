"""
Counsellor slot bookings.

Three steps happen when Maya books a slot, in this order, and each later
step failing never undoes an earlier one:

  1. Save the booking. Always. The counsellor can see it and act on it even
     if nothing else below works.
  2. Create the meeting link (Zoom or Google Meet), if a provider is set.
  3. Send the WhatsApp confirmation with the link, if a provider is set.

Every failure is written onto the booking row (meeting_error,
whatsapp_error) and shown on the dashboard, so a missing link or an unsent
message is a visible task for a human, never a silent gap.

Endpoints:
  POST /api/bookings                  agent only     book a slot
  GET  /api/bookings                  dashboard      list upcoming (and recent past)
  POST /api/bookings/{id}/resend      dashboard      resend the WhatsApp
  POST /api/bookings/{id}/status      dashboard      mark completed / cancelled / no_show
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..config import get_settings
from ..db import db, execute, get_by_id, insert_one, update_by_id
from ..deps import require_agent_key, require_dashboard_key
from ..schemas import BookingCreate, BookingCreateResponse, BookingOut, BookingRow
from ..services.meetings import service as meetings
from ..services.meetings.base import MeetingError, MeetingNotConfigured
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
    # Some errors carry no message at all (a timeout is one), so always
    # include the type, and any message the client library tucked away.
    text = str(exc) or getattr(exc, "message", "") or ""
    kind = type(exc).__name__
    if "bookings" in text or "PGRST205" in text or "does not exist" in text:
        detail = f"{MIGRATION_HINT} (database said: {text[:200]})"
    elif "Timeout" in kind or "Connect" in kind or "timed out" in text.lower():
        detail = (
            f"Could not reach Supabase ({kind}) after three attempts. Check the laptop's "
            "internet connection or VPN, then press Refresh. If the Supabase project was "
            "paused for inactivity, open it in the dashboard to wake it."
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
    settings = get_settings()

    lead = await get_by_id("leads", payload.lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")

    when = _normalise(payload.scheduled_at)
    now = datetime.now(timezone.utc)
    if when < now + MIN_AHEAD:
        # The detail is written for the brain: it becomes the tool result.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"That time ({spoken_time(when)}) is already past or too soon. "
                "Ask the lead for a time at least a little later today, or another day."
            ),
        )
    if when > now + MAX_AHEAD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{spoken_time(when)} is more than two months away. Confirm the date with the lead.",
        )

    # ---- 1. Save. Always. --------------------------------------------------
    try:
        booking = await insert_one(
            "bookings",
            {
                "lead_id": lead["id"],
                "call_id": payload.call_id,
                "scheduled_at": when.isoformat(),
                "timezone": settings.booking_timezone,
                "duration_minutes": settings.booking_duration_minutes,
                "requested_text": payload.requested_text,
                "notes": payload.notes,
                "whatsapp_status": "pending",
                "status": "booked",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    booking_id = booking["id"]
    said = spoken_time(when)
    logger.info("Booking %s saved: %s for lead %s (%r)", booking_id, said, lead["id"], payload.requested_text)

    # Keep the lead record in step with what the counsellor already reads.
    stamp = now.strftime("%d %b %Y %H:%M UTC")
    lines = [f"Slot booked: {said}"]
    if payload.notes:
        lines.append(f"Asked on the call: {payload.notes.strip()}")
    existing = (lead.get("notes") or "").strip()
    addition = f"[Maya {stamp}] " + " | ".join(lines)
    await update_by_id(
        "leads",
        lead["id"],
        {"notes": f"{existing}\n{addition}".strip() if existing else addition, "status": "contacted"},
    )

    # ---- 2. Meeting link -------------------------------------------------
    patch: dict = {}
    meeting_url: str | None = None
    meeting_label: str | None = None
    platform_note: str | None = None
    if meetings.enabled():
        try:
            link, platform_note = await meetings.create_meeting(
                topic=f"{settings.company_name}: {lead['product_or_course']} counselling with {lead['name']}",
                start=when,
                duration_minutes=settings.booking_duration_minutes,
                timezone=settings.booking_timezone,
                invitee_email=lead.get("email"),
                platform=payload.meeting_platform,
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
    else:
        patch["meeting_error"] = "No meeting provider configured (MEETING_PROVIDER=none)"

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
        except (WhatsAppNotConfigured, WhatsAppError) as exc:
            logger.warning("Booking %s: WhatsApp not sent: %s", booking_id, exc)
            patch.update({"whatsapp_status": "failed", "whatsapp_error": str(exc)[:500]})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Booking %s: WhatsApp failed", booking_id)
            patch.update({"whatsapp_status": "failed", "whatsapp_error": f"Unexpected: {exc}"[:500]})
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

    return BookingCreateResponse(booking=BookingOut(**booking), spoken_time=said, link_status=link_status)


# ---------------------------------------------------------------------------
# The counsellor dashboard
# ---------------------------------------------------------------------------


@router.get("", response_model=list[BookingRow], dependencies=[Depends(require_dashboard_key)])
async def list_bookings(
    days_back: int = Query(default=1, ge=0, le=90),
    days_ahead: int = Query(default=30, ge=1, le=365),
) -> list[BookingRow]:
    """Upcoming bookings plus yesterday's, oldest first."""
    now = datetime.now(timezone.utc)
    try:
        result = await execute(
            db()
            .table("upcoming_bookings")
            .select("*")
            .gte("scheduled_at", (now - timedelta(days=days_back)).isoformat())
            .lte("scheduled_at", (now + timedelta(days=days_ahead)).isoformat())
            .order("scheduled_at")
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    return [BookingRow(**row) for row in (result.data or [])]


@router.post("/{booking_id}/resend", response_model=BookingOut, dependencies=[Depends(require_dashboard_key)])
async def resend_whatsapp(booking_id: str) -> BookingOut:
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
    except (WhatsAppNotConfigured, WhatsAppError) as exc:
        patch = {"whatsapp_status": "failed", "whatsapp_error": str(exc)[:500]}

    updated = await update_by_id("bookings", booking_id, patch) or {**booking, **patch}
    return BookingOut(**updated)


class BookingStatusUpdate(BaseModel):
    status: str


@router.post("/{booking_id}/status", response_model=BookingOut, dependencies=[Depends(require_dashboard_key)])
async def set_status(booking_id: str, payload: BookingStatusUpdate) -> BookingOut:
    if payload.status not in ("booked", "cancelled", "completed", "no_show"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status.")
    try:
        updated = await update_by_id("bookings", booking_id, {"status": payload.status})
    except Exception as exc:  # noqa: BLE001
        raise _db_failure(exc) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    return BookingOut(**updated)
