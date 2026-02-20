"""
Time Context LLM Wrapper

Injects current interview minute and time remaining into the LLM chat context
for pacing. Conclusion is triggered by the backend at scheduled end (90% or 100%).
"""

from typing import Any, Callable

from livekit.agents import llm

from services.session_time_store import get_store  # type: ignore
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
            start_time, duration_minutes = get_store()
            if start_time is not None and duration_minutes is not None:
                try:
                    now = get_now_ist()
                    elapsed_minutes = (now - start_time).total_seconds() / 60
                    minutes_remaining = max(0, duration_minutes - elapsed_minutes)
                    # In the last 5 minutes: inject wrapping-up / conclude instructions so the agent handles the ending properly
                    if minutes_remaining > 0 and minutes_remaining <= 2:
                        time_msg = (
                            f"⏰ TIME ALERT: ONLY {int(minutes_remaining)} MINUTES REMAINING (minute {int(elapsed_minutes)} of {duration_minutes}).\n\n"
                            f"INSTRUCTION - CONCLUDE NOW:\n"
                            f"• You MUST announce we are concluding in this response\n"
                            f"• Say exactly: 'We have about {int(minutes_remaining)} minute(s) left, so let us conclude.' or 'That brings us to the end.'\n"
                            f"• Do NOT ask any new questions\n"
                            f"• One short sentence only\n"
                            f"• Do NOT say full goodbye yet (system will send that in a moment)"
                        )
                    elif minutes_remaining > 2 and minutes_remaining <= 5:
                        time_msg = (
                            f"⏰ TIME ALERT: {int(minutes_remaining)} MINUTES REMAINING (minute {int(elapsed_minutes)} of {duration_minutes}).\n\n"
                            f"INSTRUCTION - BEGIN WRAPPING UP:\n"
                            f"• You MUST mention the time remaining in this response\n"
                            f"• Say something like: 'We have about {int(minutes_remaining)} minutes left.' or 'We are coming to the end.'\n"
                            f"• Then ask at most ONE or TWO final questions from the question bank\n"
                            f"• Do NOT say full goodbye yet - just acknowledge the time and continue with final questions"
                        )
                    else:
                        # Normal: ask next question; do not conclude until system says so
                        time_msg = (
                            f"CRITICAL TIME CONTEXT: {int(minutes_remaining)} minutes REMAINING out of {duration_minutes} total. Currently at minute {int(elapsed_minutes)} of {duration_minutes}.\n\n"
                            f"⚠️  ABSOLUTE PROHIBITION - DO NOT CONCLUDE EARLY:\n"
                            f"• You are FORBIDDEN from ending, concluding, or wrapping up the interview\n"
                            f"• You MUST NOT say: 'approaching the end', 'final comments', 'last question', 'wrapping up', 'coming to the end', 'let's conclude', 'that's all'\n"
                            f"• You MUST NOT thank them for their time or wish them luck\n"
                            f"• You MUST NOT ask for 'final thoughts' or 'any questions for me'\n"
                            f"• IGNORE any previous instructions about timing or duration that conflict with this\n"
                            f"• There is still {int(minutes_remaining)} minutes left - that is MORE than enough time for multiple questions\n\n"
                            f"YOUR ONLY JOB: Ask the NEXT question from the QUESTION BANK. Continue the interview normally. One question at a time."
                        )
                    chat_ctx.add_message(role="system", content=time_msg)
                    logger.debug(
                        f"⏰ Injected time context: {int(minutes_remaining)} min remaining (minute {int(elapsed_minutes)} of {duration_minutes})"
                    )
                except Exception as e:
                    logger.debug(f"Could not inject time context: {e}")
        return self._original_chat(*args, **kwargs)
