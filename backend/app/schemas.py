"""
Request and response shapes.

Pydantic validates every inbound body against these before a router sees it, so
a malformed request is a 422 with a useful message rather than a crash three
layers down.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# E.164: a leading + then 8 to 15 digits, first digit not zero.
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


class LeadCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    email: EmailStr | None = None
    product_or_course: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    # India prohibits cold calling. The form must collect consent and we must
    # be able to prove it later, so this is required to be true, not merely
    # present. A lead without consent is stored but never called.
    consent_given: bool = False
    consent_text: str | None = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def phone_must_be_e164(cls, value: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", value.strip())

        # A bare 10-digit Indian mobile is the single most common thing people
        # type. Accept it rather than bouncing the form.
        if re.fullmatch(r"[6-9]\d{9}", cleaned):
            cleaned = f"+91{cleaned}"
        elif cleaned.startswith("91") and len(cleaned) == 12:
            cleaned = f"+{cleaned}"

        if not E164.match(cleaned):
            raise ValueError(
                "Phone must be in international format, for example +919876543210"
            )
        return cleaned

    @field_validator("name", "product_or_course")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class LeadOut(BaseModel):
    id: str
    name: str
    phone: str
    email: str | None = None
    product_or_course: str
    notes: str | None = None
    source: str
    status: str
    consent_given: bool
    consent_at: datetime | None = None
    created_at: datetime


class LeadCallbackUpdate(BaseModel):
    """
    What the agent captured during the call. Either field may be absent; a
    call that ends before a time is agreed still records what was learned.
    Stored by appending to the lead's existing notes column, so no schema
    change is needed.
    """

    callback_time: str | None = Field(default=None, max_length=200)
    callback_notes: str | None = Field(default=None, max_length=2000)


class LeadCreateResponse(BaseModel):
    lead: LeadOut
    call: "CallOut | None" = None
    # Present only on the browser path. The frontend uses it to join the room.
    join: "BrowserJoin | None" = None
    # Set when the lead was saved but no call was placed, and why.
    call_skipped_reason: str | None = None


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


class CallOut(BaseModel):
    id: str
    lead_id: str
    status: str
    transport: str
    room_name: str | None = None
    provider: str | None = None
    provider_call_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime


class BrowserJoin(BaseModel):
    """Everything the browser needs to join the LiveKit room for this call."""

    url: str
    token: str
    room_name: str


class CallStatusOut(BaseModel):
    call: CallOut
    turns: int = 0
    summary: str | None = None


# ---------------------------------------------------------------------------
# Conversations - written by the agent, not the browser
# ---------------------------------------------------------------------------


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    at: datetime | None = None
    interrupted: bool = False


class ConversationUpsert(BaseModel):
    call_id: str

    # The agent posts the COMPLETE list every time, and we replace rather than
    # append. That makes a retried flush harmless: it can never duplicate turns.
    messages: list[ConversationMessage]

    summary: str | None = None

    # Lets the agent move the call along in the same request, saving a round
    # trip on a path where every millisecond is inside a live call.
    call_status: str | None = None


class ConversationOut(BaseModel):
    id: str
    call_id: str
    messages: list[dict[str, Any]]
    summary: str | None = None
    updated_at: datetime


# ---------------------------------------------------------------------------
# Agent context - what the agent fetches when it joins a room
# ---------------------------------------------------------------------------


class AgentCallContext(BaseModel):
    call_id: str
    lead_id: str
    name: str
    phone: str
    product_or_course: str
    notes: str | None = None
    transport: str
    # Email, if the lead gave one, so a Google Meet invite can include them.
    email: str | None = None
    # Meeting platforms the lead may choose from on this deployment, default
    # first: ["google", "zoom"], ["zoom"], or [] when no links are made.
    # Maya offers the choice only when there are two.
    meeting_platforms: list[str] = []


# ---------------------------------------------------------------------------
# Bookings - a counsellor slot Maya agreed on the call
# ---------------------------------------------------------------------------


class BookingCreate(BaseModel):
    lead_id: str
    call_id: str | None = None
    # ISO 8601 with an offset, e.g. 2026-09-22T18:00:00+05:30. The agent's
    # brain computes it from what the lead said plus the current time it was
    # given in its prompt. A naive value is read as BOOKING_TIMEZONE.
    scheduled_at: datetime
    # What the lead actually said, kept verbatim for the counsellor.
    requested_text: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    # The platform the lead asked for: "zoom", "google", or None for no
    # preference (the default platform is used). Anything else is treated
    # as no preference.
    meeting_platform: str | None = Field(default=None, max_length=40)


class BookingOut(BaseModel):
    id: str
    lead_id: str
    call_id: str | None = None
    scheduled_at: datetime
    timezone: str
    duration_minutes: int
    requested_text: str | None = None
    notes: str | None = None
    meeting_provider: str | None = None
    meeting_url: str | None = None
    meeting_error: str | None = None
    whatsapp_status: str
    whatsapp_error: str | None = None
    status: str
    created_at: datetime


class BookingCreateResponse(BaseModel):
    booking: BookingOut
    # The time as a person would say it, in the booking timezone, for the
    # agent to read back: "Tuesday, 22 September at 6 pm".
    spoken_time: str
    # One sentence for the agent to tell the lead about the link.
    link_status: str


class BookingRow(BaseModel):
    """One row of the counsellor dashboard (the upcoming_bookings view)."""

    id: str
    scheduled_at: datetime
    timezone: str
    duration_minutes: int
    status: str
    meeting_url: str | None = None
    meeting_provider: str | None = None
    meeting_error: str | None = None
    whatsapp_status: str
    whatsapp_error: str | None = None
    requested_text: str | None = None
    notes: str | None = None
    lead_id: str
    lead_name: str
    lead_phone: str
    lead_email: str | None = None
    product_or_course: str
    call_id: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    database: str
    transport: str
    telephony: str
    agent_auth: str
    bookings: str = ""


LeadCreateResponse.model_rebuild()
