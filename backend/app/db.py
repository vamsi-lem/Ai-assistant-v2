"""
Supabase access.

One async client for the whole process, created at startup and reused. The
ASYNC client matters: the sync one uses a blocking httpx.Client, and a blocking
HTTP call inside FastAPI's event loop stalls every other request for the
duration of the round trip.

Everything here runs as the service role, which bypasses row level security.
Nothing in this module should ever be reachable from the browser.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from supabase import AsyncClient, AsyncClientOptions, create_async_client

from .config import get_settings

logger = logging.getLogger("backend.db")

_client: AsyncClient | None = None


async def init_db() -> AsyncClient:
    """Create the shared client. Called once from the FastAPI lifespan hook."""
    global _client

    if _client is not None:
        return _client

    settings = get_settings()

    # create_async_client is `async def` and must be awaited. This surprises
    # people: the sync version is a plain function.
    _client = await create_async_client(
        settings.supabase_url,
        settings.supabase_secret_key,
        options=AsyncClientOptions(
            # There is no user session with a service key, so both of these are
            # pointless work that can also throw on a cold start.
            auto_refresh_token=False,
            persist_session=False,
            postgrest_client_timeout=10,
        ),
    )

    logger.info("Supabase client ready (%s)", settings.supabase_url)
    return _client


def db() -> AsyncClient:
    """The shared client. Raises if init_db() has not run yet."""
    if _client is None:
        raise RuntimeError("Supabase client not initialised. init_db() must run at startup.")
    return _client


async def check_db() -> tuple[bool, str]:
    """
    Cheap liveness probe for /api/health.

    Selects zero rows from leads. That proves the URL, the key and the schema
    all work without reading any lead data.
    """
    try:
        await db().table("leads").select("id").limit(1).execute()
        return True, "connected"
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        return False, str(exc)


# ---------------------------------------------------------------------------
# Retrying transport failures
#
# On a laptop connection (and now and then in any data centre) the TLS
# handshake to Supabase occasionally fails outright: httpx.ConnectError with
# no message, or a read timeout. The query was never sent, so trying again a
# moment later is safe for reads AND writes. Three attempts, short backoff.
# Anything Supabase actually answers (a real error) is not retried.
# ---------------------------------------------------------------------------

_RETRY_ON = (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError)
_ATTEMPTS = 3
_BACKOFF_SECONDS = 0.6


async def execute(query: Any) -> Any:
    """Run a PostgREST query builder with retries on transport failure."""
    last: Exception | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return await query.execute()
        except _RETRY_ON as exc:
            last = exc
            if attempt < _ATTEMPTS:
                logger.warning(
                    "Supabase transport failure (%s), retrying %d/%d",
                    type(exc).__name__,
                    attempt,
                    _ATTEMPTS - 1,
                )
                await asyncio.sleep(_BACKOFF_SECONDS * attempt)
    assert last is not None
    raise last


# ---------------------------------------------------------------------------
# Small helpers so routers do not repeat the same three lines.
# ---------------------------------------------------------------------------


async def insert_one(table: str, row: dict[str, Any]) -> dict[str, Any]:
    result = await execute(db().table(table).insert(row))
    if not result.data:
        raise RuntimeError(f"Insert into {table} returned no row")
    return result.data[0]


async def get_by_id(table: str, row_id: str) -> dict[str, Any] | None:
    # maybe_single returns None for zero rows rather than raising, which is
    # what a "not found" lookup wants.
    result = await execute(db().table(table).select("*").eq("id", row_id).maybe_single())
    return result.data if result and result.data else None


async def update_by_id(table: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    result = await execute(db().table(table).update(patch).eq("id", row_id))
    return result.data[0] if result.data else None


async def find_one(table: str, column: str, value: Any) -> dict[str, Any] | None:
    result = await execute(db().table(table).select("*").eq(column, value).maybe_single())
    return result.data if result and result.data else None
