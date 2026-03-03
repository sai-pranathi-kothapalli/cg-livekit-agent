"""
Centralized interview timing.

Timer starts on first candidate message (set in session_time_store by TimeContextLLMWrapper).
All timing logic for the interview flow lives here; no timing logic outside this module.
"""

import math
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
        Whole minutes remaining, >= 0. Uses ceiling to avoid skipping the remaining=1 window.
    """
    if now is None:
        now = get_now_ist()
    elapsed = (now - start_time).total_seconds()
    remaining = duration_minutes * 60 - elapsed
    # Use ceiling so that at 89 seconds remaining it returns 2 (not 1),
    # giving the soft wrap check a full minute window to catch it
    return max(0, math.ceil(remaining / 60)) if remaining > 0 else 0


def get_interview_focus(remaining_minutes: int, total_duration: int = 30) -> str:
    """
    Determine interview focus from time remaining (time-aware guidance).
    Scales boundaries proportionally with interview duration.
    No phase enums or rigid transitions — single function for hybrid flow.

    Args:
        remaining_minutes: Minutes remaining until interview end.
        total_duration: Total interview duration in minutes (default: 30).

    Returns one of: "intro", "technical", "coding", "final", "wrap_up", "conclude"
    """
    # END_INTERVIEW has been triggered - time is up
    if remaining_minutes <= 0:
        return "conclude"
    
    scale = total_duration / 30
    if remaining_minutes > 24 * scale:
        return "intro"
    elif remaining_minutes > 10 * scale:
        return "technical"
    elif remaining_minutes > 3 * scale:
        return "coding"
    elif remaining_minutes > 1 * scale:
        return "final"
    else:
        return "wrap_up"
