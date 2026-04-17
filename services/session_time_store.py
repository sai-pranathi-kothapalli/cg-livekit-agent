"""
Session time store - process-local mutable store for interview timing.

Used by TimeContextLLMWrapper to get start_time, duration, and base_template
on every LLM call. Phase is computed from elapsed time before each question.
Filled when candidate joins (interview_loop); read by wrapper.
"""

from datetime import datetime
from typing import Optional, Tuple

from contextvars import ContextVar

_store_var: ContextVar[dict] = ContextVar(
    "session_time_store",
    default={
        "start_time": None,
        "duration_minutes": None,
        "base_template": "30",
        "requires_coding": False,
    }
)


def set_store(
    start_time: datetime,
    duration_minutes: int,
    base_template: str = "30",
    requires_coding: bool = False,
) -> None:
    """Set interview timing and requirements."""
    store = _store_var.get().copy()
    store["start_time"] = start_time
    store["duration_minutes"] = max(1, int(duration_minutes))
    store["base_template"] = base_template if base_template in ("30", "45") else "30"
    store["requires_coding"] = requires_coding
    _store_var.set(store)


def set_store_duration_only(
    duration_minutes: int,
    base_template: str = "30",
    requires_coding: bool = False,
) -> None:
    """Set duration, template and requirements without start_time."""
    store = _store_var.get().copy()
    store["duration_minutes"] = max(1, int(duration_minutes))
    store["base_template"] = base_template if base_template in ("30", "45") else "30"
    store["requires_coding"] = requires_coding
    _store_var.set(store)


def get_store() -> Tuple[Optional[datetime], Optional[int], str, bool]:
    """Get interview timing and requirements. Returns (start_time, duration_minutes, base_template, requires_coding)."""
    store = _store_var.get()
    dur = store.get("duration_minutes")
    if dur is not None:
        dur = int(dur)
    return (
        store.get("start_time"),
        dur,
        store.get("base_template") or "30",
        store.get("requires_coding") or False,
    )


def clear_store() -> None:
    """Clear session time store to prevent state leaks across interviews."""
    _store_var.set({
        "start_time": None,
        "duration_minutes": None,
        "base_template": "30",
        "requires_coding": False,
    })
