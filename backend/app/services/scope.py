"""
Who may see which leads.

Admins, managers and viewers see every lead. A counsellor sees only the
leads assigned to them. The same rule applies to calls, bookings and the
numbers on the dashboard, always derived from the lead's assignee.

One place, so the multi tenant filter lands here later as one extra line
(docs/MULTI-TENANT.md, rule 3).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ..auth import CurrentUser


def assigned_filter(user: CurrentUser) -> str | None:
    """The profile id to filter on, or None for everything."""
    return None if user.sees_all_leads else user.id


def scope_leads(query: Any, user: CurrentUser, column: str = "assigned_to") -> Any:
    """Apply the role scope to a PostgREST query on leads or a leads view."""
    who = assigned_filter(user)
    return query if who is None else query.eq(column, who)


def assert_can_see(lead: dict[str, Any], user: CurrentUser) -> None:
    """404 rather than 403, so a counsellor cannot probe which ids exist."""
    who = assigned_filter(user)
    if who is not None and lead.get("assigned_to") != who:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
