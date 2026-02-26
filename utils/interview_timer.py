"""
Centralized interview timing.

Timer starts on first candidate message (set in session_time_store by TimeContextLLMWrapper).
All timing logic for the interview flow lives here; no timing logic outside this module.
"""

from datetime import datetime
from typing import Optional

try:
    from app.utils.datetime_utils import get_now_ist  # type: ignore
except ImportError:
    get_now_ist = datetime.utcnow


def get_time_remaining(
    start_time: datetime,
    duration_minutes: int,
    *,
    now: Optional[datetime] = None,
) -> int:
    """
    Minutes remaining until interview end.

    Args:
        start_time: When the interview started (first candidate message).
        duration_minutes: Total interview duration in minutes.
        now: Current time (default: get_now_ist()). Used for tests and consistency.

    Returns:
        Whole minutes remaining, >= 0.
    """
    if now is None:
        now = get_now_ist()
    elapsed = (now - start_time).total_seconds()
    remaining = duration_minutes * 60 - elapsed
    return max(0, int(remaining // 60))


def get_interview_focus(remaining_minutes: int) -> str:
    """
    Determine interview focus from time remaining (time-aware guidance).
    No phase enums or rigid transitions — single function for hybrid flow.

    Returns one of: "intro", "technical", "coding", "final", "wrap_up"
    """
    if remaining_minutes > 24:
        return "intro"
    elif remaining_minutes > 10:
        return "technical"
    elif remaining_minutes > 3:
        return "coding"
    elif remaining_minutes > 1:
        return "final"
    else:
        return "wrap_up"
