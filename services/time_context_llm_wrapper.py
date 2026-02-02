"""
Time Context LLM Wrapper

Injects current interview minute into the LLM chat context so the model
knows elapsed time and does not conclude early (e.g. before 25 min in a 30 min interview).
"""

from typing import Any, Callable

from livekit.agents import llm

from agents.session_time import get_session_time  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist  # type: ignore

logger = get_logger(__name__)


class TimeContextLLMWrapper:
    """
    Wraps LLM chat to inject a system message with current minute (X of Y)
    so the LLM knows elapsed time and does not conclude before the last 2 minutes.
    """

    def __init__(self, original_chat: Callable[..., Any]):
        self._original_chat = original_chat

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        chat_ctx = kwargs.get("chat_ctx")
        if chat_ctx is not None and isinstance(chat_ctx, llm.ChatContext):
            start_time, duration_minutes = get_session_time()
            if start_time is not None and duration_minutes is not None:
                try:
                    now = get_now_ist()
                    elapsed_minutes = (now - start_time).total_seconds() / 60
                    minutes_remaining = max(0, duration_minutes - elapsed_minutes)
                    # Same "time remaining" as the timer on top left of the interview screen — we feed this to the LLM every turn
                    # Instruct LLM: conclude ONLY when TIME REMAINING is 2 minutes or less (same as the timer on top left)
                    time_msg = (
                        f"TIME REMAINING: {int(minutes_remaining)} minutes (same as the timer on top left in the interview). "
                        f"Current: minute {int(elapsed_minutes)} of {duration_minutes}. "
                        f"RULE: Only when TIME REMAINING is 2 minutes or less may you conclude, say goodbye, thank the candidate, or say the interview is complete. "
                        f"If TIME REMAINING is more than 2 minutes, you MUST NOT conclude or say goodbye—even if the candidate says they have no questions or says goodbye. Instead, say we still have time and ask another question from the QUESTION BANK. "
                        f"When TIME REMAINING is 2 or less, the system may send END_INTERVIEW; then you may conclude. Until then, keep asking questions."
                    )
                    chat_ctx.add_message(role="system", content=time_msg)
                    logger.debug(
                        f"⏰ Injected time context: {int(minutes_remaining)} min remaining (minute {int(elapsed_minutes)} of {duration_minutes})"
                    )
                except Exception as e:
                    logger.debug(f"Could not inject time context: {e}")
        return self._original_chat(*args, **kwargs)
