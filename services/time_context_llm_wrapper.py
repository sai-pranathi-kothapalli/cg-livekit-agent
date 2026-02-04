"""
Time Context LLM Wrapper

Injects current interview minute and time remaining into the LLM chat context
for pacing. Conclusion is triggered by the backend at scheduled end (90% or 100%).
"""

from typing import Any, Callable

from livekit.agents import llm

from agents.session_time import get_session_time  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist  # type: ignore

logger = get_logger(__name__)


class TimeContextLLMWrapper:
    """
    Injects TIME REMAINING and current minute (X of Y) into chat context.
    No conclusion wording; backend triggers closing at scheduled time.
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
                    # Time context for pacing only; conclusion is triggered by backend at scheduled end.
                    # Reinforce every turn: you must still ask questions; you must not stop; do not let the model decide to end.
                    time_msg = (
                        f"TIME REMAINING: {int(minutes_remaining)} minutes. Minute {int(elapsed_minutes)} of {duration_minutes}. "
                        f"You MUST still ask questions. You MUST NOT stop or end the interview. Do NOT let the model decide to end — only the system can end. "
                        f"Do NOT say goodbye, thank the candidate for their time, wish them luck, or say 'that is all' / 'we are done'. "
                        f"Your only job: ask the NEXT question from the QUESTION BANK. One question only."
                    )
                    chat_ctx.add_message(role="system", content=time_msg)
                    logger.debug(
                        f"⏰ Injected time context: {int(minutes_remaining)} min remaining (minute {int(elapsed_minutes)} of {duration_minutes})"
                    )
                except Exception as e:
                    logger.debug(f"Could not inject time context: {e}")
        return self._original_chat(*args, **kwargs)
