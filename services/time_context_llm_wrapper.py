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
                    # In the last 2 minutes: inject wrapping-up / conclude so the agent actually says it every turn
                    if minutes_remaining > 0 and minutes_remaining <= 1:
                        time_msg = (
                            f"TIME REMAINING: {int(minutes_remaining)} minute. Minute {int(elapsed_minutes)} of {duration_minutes}. "
                            f"LAST MINUTE: You MUST say we are concluding in this response. "
                            f"Say exactly something like: 'We have a minute left, so let us conclude.' or 'That brings us to the end.' "
                            f"Do NOT ask any new question. One short sentence only. Do NOT say full goodbye yet (system will send that in a moment)."
                        )
                    elif minutes_remaining > 1 and minutes_remaining <= 2:
                        time_msg = (
                            f"TIME REMAINING: {int(minutes_remaining)} minutes. Minute {int(elapsed_minutes)} of {duration_minutes}. "
                            f"LAST 2 MINUTES: You MUST say we are wrapping up in this response. "
                            f"Say something like: 'We have a couple of minutes left.' or 'We are coming to the end.' "
                            f"Then you may ask at most ONE final question from the bank. Do NOT say full goodbye yet."
                        )
                    else:
                        # Normal: ask next question; do not conclude until system says so
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
