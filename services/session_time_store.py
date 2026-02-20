"""
Session time store - process-local mutable store for interview timing.

Used by TimeContextLLMWrapper to get start_time and duration on every LLM call.
Filled by entrypoint; read by wrapper. Works reliably across threads
(unlike ContextVars in LiveKit's multiprocessing/threading flows).
"""

from datetime import datetime
from typing import Optional, Tuple

_store: dict = {"start_time": None, "duration_minutes": None}


def set_store(start_time: datetime, duration_minutes: int) -> None:
    """Set interview timing. Call from entrypoint when session starts."""
    _store["start_time"] = start_time
    _store["duration_minutes"] = duration_minutes


def get_store() -> Tuple[Optional[datetime], Optional[int]]:
    """Get interview timing. Called by TimeContextLLMWrapper on every LLM turn."""
    return _store.get("start_time"), _store.get("duration_minutes")
