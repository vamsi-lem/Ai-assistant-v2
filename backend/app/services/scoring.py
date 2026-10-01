"""
The lead score.

The number itself comes from Maya's structured end of call summary (the
model reads the transcript and scores engagement, stated interest, timeline,
budget and whether a slot was agreed). Two rules in code sit above the
model and cannot be argued with:

  - a booked slot means at least 70
  - a lead who asked not to be called, or a wrong number, means 0

Everything else is the model's judgement, clamped to 0..100.
"""

from __future__ import annotations

BOOKED_FLOOR = 70


def clamp(value: object) -> int | None:
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def apply_rules(model_score: int | None, *, has_booking: bool, do_not_call: bool) -> int | None:
    if do_not_call:
        return 0
    score = model_score
    if has_booking:
        score = max(score or 0, BOOKED_FLOOR)
    return score


def interest_for(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"
