"""
Plivo, reached through LiveKit's SIP bridge.

How a phone call happens:

    backend   asks LiveKit "put a SIP participant in room call-<id> by
              dialling +91xxxxxxxxxx through trunk ST_xxx"
    LiveKit   dials out through Plivo's SIP trunk (Zentrunk), which rings
              the lead's mobile from PLIVO_FROM_NUMBER
    agent     was dispatched the moment the room appeared; it waits until
              the lead answers, then greets exactly as it does in the browser

Plivo never fetches a webhook and never sees any XML. It is a wire between
LiveKit and the Indian phone network, nothing more. That is why this file
needs no public URL, which also means it works from a laptop.

Plivo was chosen over Twilio and Exotel because it is on LiveKit's tested
provider list, it issues Indian numbers (Twilio does not), and it
authenticates the SIP trunk with a username and password rather than an IP
allowlist, which matters because LiveKit Cloud dials out from many addresses.

This file is dormant until credentials exist. With none set, place_call
raises TelephonyNotConfigured naming exactly what is missing. It never
pretends to have dialled.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re

from google.protobuf.duration_pb2 import Duration
from livekit import api

from ...config import get_settings
from ..livekit_service import room_name_for_call
from .base import (
    CallStatus,
    PlacedCall,
    TelephonyError,
    TelephonyNotConfigured,
)

logger = logging.getLogger("backend.telephony.plivo")

# LiveKit's own words for where a SIP call is (participant attribute
# `sip.callStatus`), mapped to ours.
_SIP_STATUS = {
    "dialing": "ringing",
    "ringing": "ringing",
    "active": "in-progress",
    "automation": "in-progress",
    "hangup": "completed",
}

# How long a phone may ring before LiveKit gives up. Indian networks send a
# call to voicemail or "not reachable" well inside this.
RING_TIMEOUT_SECONDS = 40

# Hard ceiling on one call, so a stuck line cannot bill for an hour.
MAX_CALL_SECONDS = 15 * 60


def to_e164_india(raw: str) -> str:
    """
    +91 and ten digits, whatever the lead typed.

    Accepts "9876543210", "09876543210", "+91 98765 43210", "91-9876543210".
    Anything that does not reduce to a ten digit Indian mobile is rejected
    here, before a paisa is spent.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise TelephonyError(f"{raw!r} is not a valid Indian mobile number.")
    return f"+91{digits}"


def _lk() -> api.LiveKitAPI:
    s = get_settings()
    return api.LiveKitAPI(s.livekit_url, s.livekit_api_key, s.livekit_api_secret)


class PlivoProvider:
    name = "plivo"

    # -- configuration ------------------------------------------------------

    def _missing(self) -> list[str]:
        s = get_settings()
        gaps = []
        if not s.plivo_from_number:
            gaps.append("PLIVO_FROM_NUMBER")
        if not s.livekit_sip_trunk_id:
            gaps.append("LIVEKIT_SIP_TRUNK_ID")
        # The Auth ID and token are not needed to dial: LiveKit holds the SIP
        # username and password inside the trunk. They are only used to
        # verify Plivo webhooks, and are checked there.
        return gaps

    def is_configured(self) -> bool:
        return not self._missing()

    def describe(self) -> str:
        gaps = self._missing()
        if gaps:
            return f"Plivo NOT configured. Missing: {', '.join(gaps)}"
        s = get_settings()
        return (
            f"Plivo via LiveKit SIP trunk {s.livekit_sip_trunk_id}, "
            f"dialling from {s.plivo_from_number}"
        )

    # -- placing a call -----------------------------------------------------

    async def place_call(self, *, to_number: str, call_id: str, lead_name: str = "") -> PlacedCall:
        gaps = self._missing()
        if gaps:
            raise TelephonyNotConfigured(
                "Plivo is not configured. Missing in backend/.env: " + ", ".join(gaps)
            )

        s = get_settings()
        dial_to = to_e164_india(to_number)
        room = room_name_for_call(call_id)

        # Every field is documented for CreateSIPParticipantRequest. The newer
        # ones are dropped if the installed livekit-api predates them, with a
        # log line, rather than crashing the call.
        wanted = {
            "sip_trunk_id": s.livekit_sip_trunk_id,
            "sip_call_to": dial_to,
            "sip_number": s.plivo_from_number,
            "room_name": room,
            "participant_identity": f"phone-{call_id}",
            "participant_name": lead_name or dial_to,
            "ringing_timeout": Duration(seconds=RING_TIMEOUT_SECONDS),
            "max_call_duration": Duration(seconds=MAX_CALL_SECONDS),
            # Return at once. The agent watches the participant's call status
            # and greets only when it turns active; the backend must not hold
            # an HTTP request open for forty seconds of ringing.
            "wait_until_answered": False,
            # LiveKit's noise cancellation on the phone leg itself.
            "krisp_enabled": True,
        }
        allowed = api.CreateSIPParticipantRequest.DESCRIPTOR.fields_by_name
        request_kwargs = {k: v for k, v in wanted.items() if k in allowed}
        skipped = [k for k in wanted if k not in allowed]
        if skipped:
            logger.info("Installed livekit-api lacks %s; upgrade it to use them", ", ".join(skipped))

        lk = _lk()
        try:
            participant = await lk.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(**request_kwargs)
            )
        except api.TwirpError as exc:
            logger.error("LiveKit refused to dial %s for call %s: %s", dial_to, call_id, exc)
            raise TelephonyError(f"LiveKit could not place the call: {exc.message}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Dial failed for call %s", call_id)
            raise TelephonyError(f"Could not place the call: {exc}") from exc
        finally:
            await lk.aclose()

        sip_call_id = getattr(participant, "sip_call_id", "") or participant.participant_identity
        logger.info(
            "Dialling %s for call %s in room %s (sip call %s)", dial_to, call_id, room, sip_call_id
        )
        return PlacedCall(provider=self.name, provider_call_id=str(sip_call_id), status="ringing")

    # -- status -------------------------------------------------------------

    async def fetch_status(self, provider_call_id: str, *, call_id: str | None = None) -> CallStatus:
        """
        Where is the call? Asked of LiveKit, not Plivo.

        The phone participant carries a `sip.callStatus` attribute that
        LiveKit keeps current: dialing, ringing, active, hangup. Once the
        room is gone the agent has already written the final status, so
        this hands back "completed" and the stored value wins if it is more
        specific (no-answer, busy).
        """
        if not call_id:
            return CallStatus(status="in-progress")

        room = room_name_for_call(call_id)
        lk = _lk()
        try:
            listing = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
        except api.TwirpError as exc:
            if "not" in exc.message.lower():  # "room does not exist"
                return CallStatus(status="completed")
            return CallStatus(status="in-progress", error=exc.message)
        except Exception as exc:  # noqa: BLE001
            return CallStatus(status="in-progress", error=f"Could not read status: {exc}")
        finally:
            await lk.aclose()

        for p in listing.participants:
            sip_status = dict(p.attributes).get("sip.callStatus")
            if sip_status:
                return CallStatus(status=_SIP_STATUS.get(sip_status, "in-progress"))
        return CallStatus(status="in-progress")

    # -- webhook verification -----------------------------------------------

    def verify_webhook(self, *, url: str, body: bytes, headers: dict[str, str]) -> bool:
        """
        Confirm a status callback really came from Plivo.

        Not exercised on the SIP path, where LiveKit reports status, but it
        is the correct check for any Plivo Voice API callback and stays so
        the webhook route is never an open door: HMAC-SHA256 over
        `url + nonce`, base64, in X-Plivo-Signature-V3, with the nonce in
        X-Plivo-Signature-V3-Nonce. The header may carry several
        comma-separated signatures; any one matching is valid.
        """
        s = get_settings()
        if not s.plivo_auth_token:
            return False

        lowered = {k.lower(): v for k, v in headers.items()}
        signature_header = lowered.get("x-plivo-signature-v3", "")
        nonce = lowered.get("x-plivo-signature-v3-nonce", "")

        if not signature_header or not nonce:
            logger.warning("Plivo webhook arrived without a V3 signature")
            return False

        payload = f"{url}{nonce}".encode()
        expected = base64.b64encode(
            hmac.new(s.plivo_auth_token.encode(), payload, hashlib.sha256).digest()
        ).decode()

        for candidate in signature_header.split(","):
            if hmac.compare_digest(candidate.strip(), expected):
                return True

        logger.warning("Plivo webhook signature did not match")
        return False
