"""
Session time context for interview duration.

Allows the LLM chat wrapper to inject "current minute X of Y" into the
agent context so the model knows elapsed time and does not conclude early.
"""

from contextvars import ContextVar
from datetime import datetime
from typing import Optional, Tuple

# Set by entrypoint when session starts; read by time-context LLM wrapper
interview_start_time_ctx: ContextVar[Optional[datetime]] = ContextVar(
    "interview_start_time", default=None
)
interview_duration_minutes_ctx: ContextVar[Optional[int]] = ContextVar(
    "interview_duration_minutes", default=None
)


def set_session_time(start_time: datetime, duration_minutes: int) -> None:
    """Call from entrypoint when the interview session starts."""
    interview_start_time_ctx.set(start_time)
    interview_duration_minutes_ctx.set(duration_minutes)


def get_session_time() -> Tuple[Optional[datetime], Optional[int]]:
    """Return (start_time, duration_minutes) for the current context."""
    return (
        interview_start_time_ctx.get(),
        interview_duration_minutes_ctx.get(),
    )
