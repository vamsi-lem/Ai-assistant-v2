"""
Two small brakes on the public lead form.

The form is the one endpoint anyone on the internet can hit, and every
accepted submission with consent places a paid phone call. Without a brake a
script could submit a few thousand forms and empty the carrier balance in an
afternoon. These two checks stop that without getting in the way of a real
lead:

1. Per address: at most LEAD_MAX_PER_IP_PER_HOUR submissions from one client
   address in a rolling hour. A family sharing one connection never gets near
   it; a script does in seconds. Kept in memory, which is right for one
   backend process. If the backend ever runs as several machines, move this
   to a table; the phone check below already lives in the database.

2. Per phone number: at most one call to the same number within
   LEAD_PHONE_COOLDOWN_MINUTES. The lead is still saved (that rule never
   bends), only the call is skipped, and the response says so. This also
   stops the double call when a lead submits twice because the page felt
   slow.

Both are off when their setting is 0.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from .config import get_settings
from .db import db, execute

logger = logging.getLogger("backend.throttle")

_WINDOW_SECONDS = 3600
_hits: dict[str, deque[float]] = defaultdict(deque)


def check_ip(ip: str) -> bool:
    """True if this address may submit now; records the hit when it may."""
    limit = get_settings().lead_max_per_ip_per_hour
    if limit <= 0:
        return True

    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > _WINDOW_SECONDS:
        window.popleft()

    if len(window) >= limit:
        logger.warning("Lead form throttled for %s: %d in the last hour", ip, len(window))
        return False

    window.append(now)

    # Keep the map from growing forever on a busy day. Anything idle for over
    # an hour is empty by now and can go.
    if len(_hits) > 5000:
        for key in [k for k, v in _hits.items() if not v]:
            del _hits[key]
    return True


async def recent_call_to(phone: str) -> datetime | None:
    """
    When this number was last accepted for a call inside the cooldown window,
    or None if it is clear to call. Reads the leads table so it holds across
    restarts and across machines.
    """
    minutes = get_settings().lead_phone_cooldown_minutes
    if minutes <= 0:
        return None

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await execute(
        db()
        .table("leads")
        .select("created_at,status")
        .eq("phone", phone)
        .gte("created_at", since.isoformat())
        .neq("status", "new")
        .order("created_at", desc=True)
        .limit(1)
    )
    rows = result.data or []
    if not rows:
        return None
    raw = rows[0]["created_at"]
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return since
