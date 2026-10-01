"""
Who is calling the dashboard endpoints.

The browser signs in with Supabase Auth and sends the resulting token as
`Authorization: Bearer <jwt>` on every request. This module checks that
token and loads the matching row from `profiles`, which is where the role
lives. The role is never read from the token or from the browser, so a user
cannot promote themselves by editing a request.

Verification is local: Supabase publishes the public half of its signing key
at /auth/v1/.well-known/jwks.json, this module fetches it once an hour, and
no network call is made per request. Older Supabase projects sign with a shared HS256 secret
instead; for those, SUPABASE_JWT_SECRET in backend/.env does the same job.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKSet

from .config import get_settings
from .db import db, execute

logger = logging.getLogger("backend.auth")

ROLES = ("admin", "manager", "counsellor", "viewer")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    role: str
    active: bool

    def is_one_of(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def sees_all_leads(self) -> bool:
        """Counsellors see only leads assigned to them; everyone else sees all."""
        return self.role in ("admin", "manager", "viewer")

    @property
    def can_edit(self) -> bool:
        return self.role in ("admin", "manager", "counsellor")


# ---------------------------------------------------------------------------
# Token verification
#
# The public keys come from Supabase once an hour, fetched with httpx and the
# same retry rule as every other Supabase call (a laptop connection drops a
# TLS handshake now and then). Between fetches nothing leaves this process.
# ---------------------------------------------------------------------------

_JWKS_TTL = 3600.0
_jwks_cache: tuple[float, PyJWKSet] | None = None
_jwks_lock = asyncio.Lock()

# Clock tolerance for the token's "issued at" and "expires" times. A laptop
# clock a few seconds behind Supabase's makes a brand new token look like it
# comes from the future ("The token is not yet valid (iat)") and sign in
# fails until the seconds pass. Sixty seconds covers every normal machine
# without weakening expiry in any way that matters.
_CLOCK_LEEWAY = 60


def _jwks_url() -> str:
    return f"{get_settings().supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


async def _fetch_jwks() -> PyJWKSet:
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(1, 4):
            try:
                response = await client.get(_jwks_url())
                response.raise_for_status()
                return PyJWKSet.from_dict(response.json())
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                logger.warning("JWKS fetch failed (%s), attempt %d/3", type(exc).__name__, attempt)
                await asyncio.sleep(0.6 * attempt)
    assert last is not None
    raise last


async def _get_jwks(force: bool = False) -> PyJWKSet:
    global _jwks_cache
    async with _jwks_lock:
        if not force and _jwks_cache and _jwks_cache[0] > time.monotonic():
            return _jwks_cache[1]
        jwks = await _fetch_jwks()
        _jwks_cache = (time.monotonic() + _JWKS_TTL, jwks)
        return jwks


def _key_for(jwks: PyJWKSet, kid: str | None) -> Any | None:
    for candidate in jwks.keys:
        if kid is None or candidate.key_id == kid:
            return candidate.key
    return None


async def _decode(token: str) -> dict[str, Any]:
    """Verify signature, expiry and audience. Raises jwt exceptions on failure."""
    settings = get_settings()
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    if alg == "HS256":
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "This Supabase project signs tokens with a shared secret. Put it in "
                    "backend/.env as SUPABASE_JWT_SECRET (Supabase dashboard > Project "
                    "Settings > JWT Keys > Legacy JWT Secret) and restart the backend."
                ),
            )
        return jwt.decode(
            token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated", leeway=_CLOCK_LEEWAY
        )

    kid = header.get("kid")
    key = _key_for(await _get_jwks(), kid)
    if key is None:
        # Supabase rotated its key since we last looked. Fetch once more.
        key = _key_for(await _get_jwks(force=True), kid)
    if key is None:
        raise jwt.InvalidKeyError(f"No signing key with id {kid!r} at {_jwks_url()}")
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated", leeway=_CLOCK_LEEWAY)


# ---------------------------------------------------------------------------
# Profile lookup, cached briefly so a page load does not hit the database
# once per request. A deactivation therefore takes up to a minute to bite.
#
# Two things keep the cache honest: the team endpoints drop an entry when
# they change someone, and GET /api/me (the first call every sign in makes)
# always reads fresh. So a role changed by hand in the SQL editor is picked
# up at the next sign in, not after a backend restart.
# ---------------------------------------------------------------------------

_PROFILE_TTL = 60.0
_profiles: dict[str, tuple[float, CurrentUser]] = {}


def forget_profile(user_id: str) -> None:
    """Drop the cached copy after the team page changes a role or deactivates someone."""
    _profiles.pop(user_id, None)


async def load_profile(user_id: str, *, fresh: bool = False) -> CurrentUser | None:
    cached = None if fresh else _profiles.get(user_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    result = await execute(
        db().table("profiles").select("id,email,name,role,active").eq("id", user_id).maybe_single()
    )
    row = result.data if result and result.data else None
    if not row:
        return None

    user = CurrentUser(
        id=str(row["id"]),
        email=row.get("email") or "",
        name=row.get("name") or "",
        role=row.get("role") or "viewer",
        active=bool(row.get("active", True)),
    )
    _profiles[user_id] = (time.monotonic() + _PROFILE_TTL, user)
    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def require_user(request: Request) -> CurrentUser:
    """
    The signed in dashboard user. 401 when the token is missing, expired or
    forged; 403 when the account has been deactivated.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    token = header[7:].strip()

    try:
        claims = await _decode(token)
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Sign in again.")
    except jwt.PyJWTError as exc:
        logger.warning("Rejected dashboard token: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid sign in token ({exc}).")
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Could not fetch Supabase signing keys from %s: %s", _jwks_url(), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Could not reach Supabase to verify your sign in "
                f"({type(exc).__name__}: {exc or 'connection dropped'}). Try again in a moment."
            ),
        )

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sign in token.")

    user = await load_profile(str(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has no profile yet. Ask an admin to run migration 0003 or add you to the team.",
        )
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated.")
    return user


def require_roles(*roles: str):
    """Dependency factory: `Depends(require_roles("admin", "manager"))`."""

    async def check(user: CurrentUser = Depends(require_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This needs the {' or '.join(roles)} role.",
            )
        return user

    return check


require_editor = require_roles("admin", "manager", "counsellor")
require_manager = require_roles("admin", "manager")
require_admin = require_roles("admin")
