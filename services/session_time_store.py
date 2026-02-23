"""
Session time store - process-local mutable store for interview timing.

Used by TimeContextLLMWrapper to get start_time, duration, and base_template
on every LLM call. Phase is computed from elapsed time before each question.
Filled when candidate joins (interview_loop); read by wrapper.
"""

from datetime import datetime
from typing import Optional, Tuple

_store: dict = {"start_time": None, "duration_minutes": None, "base_template": "30"}


def set_store(
    start_time: datetime,
    duration_minutes: int,
    base_template: str = "30",
) -> None:
    """Set interview timing. Call when candidate joins (interview_loop)."""
    _store["start_time"] = start_time
    _store["duration_minutes"] = duration_minutes
    _store["base_template"] = base_template if base_template in ("30", "45") else "30"


def get_store() -> Tuple[Optional[datetime], Optional[int], str]:
    """Get interview timing. Returns (start_time, duration_minutes, base_template)."""
    return (
        _store.get("start_time"),
        _store.get("duration_minutes"),
        _store.get("base_template") or "30",
    )
