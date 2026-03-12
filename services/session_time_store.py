"""
Session time store - process-local mutable store for interview timing.

Used by TimeContextLLMWrapper to get start_time, duration, and base_template
on every LLM call. Phase is computed from elapsed time before each question.
Filled when candidate joins (interview_loop); read by wrapper.
"""

from datetime import datetime
from typing import Optional, Tuple

_store: dict = {
    "start_time": None,
    "duration_minutes": None,
    "base_template": "30",
    "requires_coding": False,
}


def set_store(
    start_time: datetime,
    duration_minutes: int,
    base_template: str = "30",
    requires_coding: bool = False,
) -> None:
    """Set interview timing and requirements."""
    _store["start_time"] = start_time
    _store["duration_minutes"] = max(1, int(duration_minutes))
    _store["base_template"] = base_template if base_template in ("30", "45") else "30"
    _store["requires_coding"] = requires_coding


def set_store_duration_only(
    duration_minutes: int,
    base_template: str = "30",
    requires_coding: bool = False,
) -> None:
    """Set duration, template and requirements without start_time."""
    _store["duration_minutes"] = max(1, int(duration_minutes))
    _store["base_template"] = base_template if base_template in ("30", "45") else "30"
    _store["requires_coding"] = requires_coding


def get_store() -> Tuple[Optional[datetime], Optional[int], str, bool]:
    """Get interview timing and requirements. Returns (start_time, duration_minutes, base_template, requires_coding)."""
    dur = _store.get("duration_minutes")
    if dur is not None:
        dur = int(dur)
    return (
        _store.get("start_time"),
        dur,
        _store.get("base_template") or "30",
        _store.get("requires_coding") or False,
    )
