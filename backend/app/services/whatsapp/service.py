"""
The WhatsApp façade. Routers call this and nothing else.
"""

from __future__ import annotations

import logging

from ...config import get_settings
from .meta import MetaWhatsApp, WhatsAppNotConfigured

logger = logging.getLogger("backend.whatsapp")

_PROVIDERS = {"meta": MetaWhatsApp()}


def enabled() -> bool:
    return get_settings().whatsapp_provider in _PROVIDERS


def get_provider() -> MetaWhatsApp:
    name = get_settings().whatsapp_provider
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise WhatsAppNotConfigured(
            "WHATSAPP_PROVIDER is 'none'. Set it to meta in backend/.env to send confirmations."
        )
    if not provider.is_configured():
        raise WhatsAppNotConfigured(f"{name} is selected but its credentials are missing in backend/.env")
    return provider


async def send_booking_confirmation(
    *,
    to_number: str,
    lead_name: str,
    course: str,
    when_text: str,
    meeting_url: str | None,
) -> str:
    """
    Send the booking template. Returns the provider's message id.
    Raises WhatsAppNotConfigured or WhatsAppError.
    """
    s = get_settings()
    link = meeting_url or "the counsellor will call you on this number"
    params = [lead_name, course, when_text, link, s.company_name]
    return await get_provider().send_template(to_number=to_number, params=params)
