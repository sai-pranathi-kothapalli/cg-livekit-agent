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
    Determine interview focus from time remaining.

    Phases are deliberately broad so the AI freely mixes question types
    within each window — preventing candidates from predicting what comes next.

    Scales proportionally with total_duration (calibrated for 30 min).

    Returns one of: "intro", "assessment", "coding_window", "mixed", "wrap_up", "conclude"

    Phase map (30 min baseline):
      intro          > 24 min  — candidate intro, background, self-introduction
      assessment     15–24 min — technical questions and/or MCQs (AI chooses mix)
      coding_window   7–15 min — coding problems and/or debugging challenges
      mixed           2–7 min  — MCQ / scenario / additional technical (AI chooses)
      wrap_up          0–1 min — closing, candidate questions
      conclude           0 min — END_INTERVIEW triggered
    """
    if remaining_minutes <= 0:
        return "conclude"

    scale = total_duration / 30
    if remaining_minutes > 24 * scale:
        return "intro"
    elif remaining_minutes > 15 * scale:
        return "assessment"
    elif remaining_minutes > 7 * scale:
        return "coding_window"
    elif remaining_minutes > 1 * scale:
        return "mixed"
    else:
        return "wrap_up"
