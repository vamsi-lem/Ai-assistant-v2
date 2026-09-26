"""
LiveKit room naming and access tokens.

The room name is the only thing that ties a call to the agent. It is derived
from the call id and nothing else, so the agent can recover the call id from
the room name alone and fetch everything else from this backend. That is why
the same agent serves a browser participant today and a SIP participant later
without a line of it changing. On the phone path the backend asks LiveKit
to dial the lead INTO that room (see telephony/plivo_provider.py), so the
room name is again the only handle anyone needs.
"""

from __future__ import annotations

from datetime import timedelta

from livekit import api

from ..config import get_settings

ROOM_PREFIX = "call-"

# A browser token only needs to outlive the call. Thirty minutes is generous
# for a three minute conversation and short enough that a leaked token is
# close to worthless.
TOKEN_TTL = timedelta(minutes=30)


def room_name_for_call(call_id: str) -> str:
    return f"{ROOM_PREFIX}{call_id}"


def call_id_from_room(room_name: str) -> str | None:
    """Inverse of room_name_for_call. Returns None for any other room."""
    if not room_name or not room_name.startswith(ROOM_PREFIX):
        return None
    call_id = room_name[len(ROOM_PREFIX) :].strip()
    return call_id or None


def create_browser_token(call_id: str, lead_name: str) -> str:
    """
    Mint a join token for the lead's browser.

    Scoped to exactly one room and nothing else. It cannot create rooms, cannot
    list them, and cannot join any other call.
    """
    settings = get_settings()
    room = room_name_for_call(call_id)

    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_subscribe=True,
        # No reason for a lead's browser to publish screen share or data.
        can_publish_data=False,
    )

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"lead-{call_id}")
        .with_name(lead_name)
        .with_grants(grants)
        .with_ttl(TOKEN_TTL)
    )

    return token.to_jwt()
