"""
Shared dependencies.

Proving a request came from our own agent before letting it read lead data
or write a transcript. Dashboard users are checked in app/auth.py.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from .config import get_settings

logger = logging.getLogger("backend.auth")


async def require_agent_key(x_agent_key: str | None = Header(default=None)) -> None:
    """
    Guard for the endpoints only the agent may call.

    The agent runs on our own server and holds a long-lived shared secret, so a
    header check is the right level of ceremony here. Two details matter:

    1. If AGENT_API_KEY is unset we return 503, not 200. An unset secret must
       never mean "let everyone in".
    2. Comparison is constant time. A plain == leaks how much of the key was
       correct through response timing, which is enough to recover it.
    """
    settings = get_settings()
    expected = settings.agent_api_key

    if not expected:
        logger.error("AGENT_API_KEY is not set. Agent endpoints are disabled.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent authentication is not configured on this server.",
        )

    supplied = (x_agent_key or "").strip()

    # compare_digest on differing lengths still short-circuits, so equalise the
    # length check first and always run the comparison.
    ok = len(supplied) == len(expected) and hmac.compare_digest(supplied, expected)

    if not ok:
        logger.warning("Rejected agent request: bad or missing X-Agent-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Agent-Key.",
        )


def client_ip(request: Request) -> str | None:
    """
    Best-effort caller IP, stored as consent evidence.

    Behind Render, Fly or Vercel the socket address is a proxy, so the real client
    is the first entry in X-Forwarded-For. This is evidence, not security: a
    client can forge the header, which is fine because its job is to show good
    faith in a complaint, not to authenticate anyone.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None
