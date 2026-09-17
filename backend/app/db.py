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

import logging
from typing import Any

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
# Small helpers so routers do not repeat the same three lines.
# ---------------------------------------------------------------------------


async def insert_one(table: str, row: dict[str, Any]) -> dict[str, Any]:
    result = await db().table(table).insert(row).execute()
    if not result.data:
        raise RuntimeError(f"Insert into {table} returned no row")
    return result.data[0]


async def get_by_id(table: str, row_id: str) -> dict[str, Any] | None:
    # maybe_single returns None for zero rows rather than raising, which is
    # what a "not found" lookup wants.
    result = await db().table(table).select("*").eq("id", row_id).maybe_single().execute()
    return result.data if result and result.data else None


async def update_by_id(table: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    result = await db().table(table).update(patch).eq("id", row_id).execute()
    return result.data[0] if result.data else None


async def find_one(table: str, column: str, value: Any) -> dict[str, Any] | None:
    result = (
        await db().table(table).select("*").eq(column, value).maybe_single().execute()
    )
    return result.data if result and result.data else None
