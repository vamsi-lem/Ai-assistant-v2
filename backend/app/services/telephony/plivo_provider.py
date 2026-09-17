"""
Plivo implementation.

Plivo was chosen over Twilio and Exotel for India because it is on LiveKit's
tested provider list, it actually issues Indian numbers (Twilio does not),
it is roughly ten times cheaper than Twilio per minute, and it authenticates
the SIP trunk with credentials rather than an IP allowlist, which matters
because LiveKit Cloud calls out from large address ranges.

This file is written and real, but stays DORMANT until credentials exist.
With none set, place_call raises TelephonyNotConfigured with a message saying
exactly what is missing. It never pretends to have dialled.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from xml.sax.saxutils import escape

from ...config import get_settings
from ..livekit_service import sip_uri_for_call
from .base import (
    CallStatus,
    PlacedCall,
    TelephonyError,
    TelephonyNotConfigured,
    normalise_status,
)

logger = logging.getLogger("backend.telephony.plivo")


class PlivoProvider:
    name = "plivo"

    # -- configuration ------------------------------------------------------

    def _missing(self) -> list[str]:
        """
        What Plivo needs before it can dial at all.

        LIVEKIT_SIP_URI is deliberately NOT in this list. Without it the call
        still happens, it just speaks a test line instead of bridging into the
        room. That distinction matters a lot in practice: bridging requires
        LiveKit region pinning, which is only sold on their Scale plan, so
        making the SIP URI mandatory here would mean you could not test your
        carrier setup at all until you had spent $500 a month.
        """
        s = get_settings()
        gaps = []
        if not s.plivo_auth_id:
            gaps.append("PLIVO_AUTH_ID")
        if not s.plivo_auth_token:
            gaps.append("PLIVO_AUTH_TOKEN")
        if not s.plivo_from_number:
            gaps.append("PLIVO_FROM_NUMBER")
        if not s.public_base_url:
            # Plivo has no inline-XML option like Twilio does. It can only
            # FETCH call instructions from a URL, so without a reachable
            # backend it has no way to learn what to do with an answered call.
            gaps.append("PUBLIC_BASE_URL")
        return gaps

    def is_configured(self) -> bool:
        return not self._missing()

    def bridges_to_livekit(self) -> bool:
        """True when a call will be joined to the room rather than just tested."""
        return bool(get_settings().livekit_sip_uri)

    def describe(self) -> str:
        gaps = self._missing()
        if gaps:
            return f"Plivo NOT configured. Missing: {', '.join(gaps)}"

        s = get_settings()
        mode = (
            f"bridging into LiveKit SIP at {s.livekit_sip_uri}"
            if self.bridges_to_livekit()
            else "TEST MODE, speaks one line and hangs up (LIVEKIT_SIP_URI unset)"
        )
        return f"Plivo ready, dialling from {s.plivo_from_number}, {mode}"

    # -- placing a call -----------------------------------------------------

    async def place_call(self, *, to_number: str, call_id: str) -> PlacedCall:
        gaps = self._missing()
        if gaps:
            raise TelephonyNotConfigured(
                "Plivo is not configured. Missing in backend/.env: " + ", ".join(gaps)
            )

        s = get_settings()

        # Plivo fetches this URL when the lead answers, and does whatever the
        # XML it returns says. See answer_xml() below.
        answer_url = f"{s.public_base_url}/api/webhooks/plivo/answer?call_id={call_id}"
        hangup_url = f"{s.public_base_url}/api/webhooks/telephony"

        if not self.bridges_to_livekit():
            logger.warning(
                "LIVEKIT_SIP_URI is not set, so the answered call will speak a test "
                "line and hang up rather than reaching the agent. That is enough to "
                "prove the carrier path. Set it once LiveKit region pinning is in place."
            )

        def _dial() -> dict:
            # The Plivo SDK is synchronous, so it runs in a worker thread. A
            # blocking HTTP call on the event loop would stall every other
            # request for the length of the round trip.
            import plivo  # imported lazily so the package is optional until used

            client = plivo.RestClient(s.plivo_auth_id, s.plivo_auth_token)
            return client.calls.create(
                from_=s.plivo_from_number,
                to_=to_number,
                answer_url=answer_url,
                answer_method="POST",
                hangup_url=hangup_url,
                hangup_method="POST",
            )

        try:
            response = await asyncio.to_thread(_dial)
        except Exception as exc:  # noqa: BLE001 - surface the provider's own words
            logger.exception("Plivo refused the call for %s", call_id)
            raise TelephonyError(f"Plivo rejected the call: {exc}") from exc

        # The SDK returns an object or dict depending on version; handle both
        # rather than assuming.
        request_uuid = (
            response.get("request_uuid")
            if isinstance(response, dict)
            else getattr(response, "request_uuid", None)
        )

        if not request_uuid:
            raise TelephonyError(f"Plivo accepted the call but returned no id: {response!r}")

        logger.info("Plivo dialling %s for call %s (uuid %s)", to_number, call_id, request_uuid)
        return PlacedCall(provider=self.name, provider_call_id=str(request_uuid), status="ringing")

    # -- the answer XML -----------------------------------------------------

    @staticmethod
    def answer_xml(call_id: str) -> str:
        """
        What Plivo does the moment the lead picks up.

        This is Plivo XML, their equivalent of Twilio's TwiML. Two modes, and
        which one you get depends only on whether LIVEKIT_SIP_URI is set.

          SIP unset  speak one line, hang up. Proves your Plivo account, your
                     KYC, your Indian number, the answer webhook and the status
                     callbacks all work. Costs about a rupee. Needs no LiveKit
                     plan at all.

          SIP set    transfer the live call into the LiveKit room. Plivo then
                     plays no further part in the conversation. No speech, no
                     menu, no recorded message: the XML is an address.

        Test in the first mode first. If the phone rings and you hear the line,
        every hard part of Indian telephony is already working and only the
        bridge remains, which is the part gated on region pinning.
        """
        sip_host = get_settings().livekit_sip_uri

        if not sip_host:
            message = (
                "Hello. This is a test call from the A I voice platform. "
                "Your telephony provider is connected correctly. Goodbye."
            )
            return (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<Response>\n"
                f'  <Speak language="en-IN">{escape(message)}</Speak>\n'
                "</Response>\n"
            )

        # VERIFY THIS ONE THING against Plivo's own LiveKit integration guide
        # before the first bridged call. <Dial><User>sip:...</User></Dial> is
        # the documented shape for dialling a SIP endpoint, but it could not be
        # tested from here, and a wrong element name presents as a call that
        # connects and then silently drops. The test mode above does not touch
        # this path, so prove that first.
        target = escape(sip_uri_for_call(call_id))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            "  <Dial>\n"
            f"    <User>{target}</User>\n"
            "  </Dial>\n"
            "</Response>\n"
        )

    # -- status -------------------------------------------------------------

    async def fetch_status(self, provider_call_id: str) -> CallStatus:
        """
        Poll Plivo for a call's outcome.

        Used when the backend has no public URL, so Plivo cannot reach us with
        a webhook. Once deployed, the webhook path is better: it is instant and
        costs no requests.
        """
        gaps = self._missing()
        if gaps:
            raise TelephonyNotConfigured("Plivo is not configured: " + ", ".join(gaps))

        s = get_settings()

        def _fetch() -> dict:
            import plivo

            client = plivo.RestClient(s.plivo_auth_id, s.plivo_auth_token)
            try:
                return client.calls.get(call_uuid=provider_call_id)
            except Exception:
                # A call still ringing is not in the completed-calls resource
                # yet; live calls live in a different one.
                return client.live_calls.get(live_call_uuid=provider_call_id)

        try:
            result = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001
            return CallStatus(status="in-progress", error=f"Could not read status: {exc}")

        raw = (
            result.get("call_status")
            if isinstance(result, dict)
            else getattr(result, "call_status", "")
        )
        return CallStatus(status=normalise_status(str(raw)))

    # -- webhook verification -----------------------------------------------

    def verify_webhook(self, *, url: str, body: bytes, headers: dict[str, str]) -> bool:
        """
        Confirm a status callback really came from Plivo.

        Plivo signs callbacks with V3 signatures: HMAC-SHA256 over
        `url + nonce`, base64 encoded, sent as X-Plivo-Signature-V3 with the
        nonce in X-Plivo-Signature-V3-Nonce. The header may carry several
        comma-separated signatures, and any one matching is valid.

        Hand-rolled rather than using the SDK helper for the same reason as in
        v1: it works identically whatever SDK version is installed, and when it
        fails the reason is visible here rather than inside a dependency.
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
