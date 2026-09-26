"""
WhatsApp through Meta's Cloud API.

The one rule that shapes this file: a business may only START a WhatsApp
conversation with an approved message template. Free text is allowed only
within 24 hours of the person messaging you first. A booking confirmation
after a phone call is business-initiated, so it goes out as a template with
the details filled into its placeholders.

Template `booking_confirmation` (create it in Meta Business -> WhatsApp
Manager -> Message templates, category Utility, language English), body:

    Hi {{1}}, thanks for speaking with us about {{2}}.
    Your counsellor call is booked for {{3}}.
    Join here: {{4}}
    Team {{5}}

Five parameters, in that order: name, course, time, link, company. For a
booking with no link (no meeting provider yet), {{4}} carries the words
"the counsellor will call you on this number".

For the very first test, Meta's pre-approved `hello_world` template works
with no parameters: set WHATSAPP_TEMPLATE_NAME=hello_world, send, see it
arrive, then switch to the real template once approved.
"""

from __future__ import annotations

import logging

import httpx

from ...config import get_settings

logger = logging.getLogger("backend.whatsapp.meta")

GRAPH_API = "https://graph.facebook.com/v21.0"


class WhatsAppError(Exception):
    """Meta was reached and refused, or failed."""


class WhatsAppNotConfigured(Exception):
    """No provider, or a provider missing its credentials."""


class MetaWhatsApp:
    name = "meta"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.whatsapp_phone_number_id and s.whatsapp_access_token)

    async def send_template(self, *, to_number: str, params: list[str]) -> str:
        """
        Send the configured template to `to_number` (E.164) with `params`
        filling {{1}}..{{n}} in order. Returns Meta's message id.
        """
        if not self.is_configured():
            raise WhatsAppNotConfigured("Meta WhatsApp needs WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN")

        s = get_settings()
        template: dict = {
            "name": s.whatsapp_template_name,
            "language": {"code": s.whatsapp_template_language},
        }
        # hello_world has no placeholders; sending parameters to it is an error.
        if params and s.whatsapp_template_name != "hello_world":
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ]

        payload = {
            "messaging_product": "whatsapp",
            "to": to_number.lstrip("+"),
            "type": "template",
            "template": template,
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{GRAPH_API}/{s.whatsapp_phone_number_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
            )

        if response.status_code not in (200, 201):
            # Meta's error body says exactly what is wrong (template not
            # approved, number not in the test list, token expired). Keep it.
            detail = response.text[:400]
            try:
                err = response.json().get("error", {})
                detail = f"{err.get('message', '')} ({err.get('code')}) {err.get('error_data', {}).get('details', '')}".strip()
            except Exception:  # noqa: BLE001
                pass
            raise WhatsAppError(f"Meta refused the message ({response.status_code}): {detail}")

        body = response.json()
        messages = body.get("messages") or []
        message_id = messages[0].get("id", "") if messages else ""
        logger.info("WhatsApp template %s sent to %s (%s)", s.whatsapp_template_name, to_number, message_id)
        return message_id
