"""
Time Context LLM Wrapper

Injects time context BEFORE each LLM call (before generating the next question):
- elapsed_minutes, remaining_minutes, current_phase (from elapsed time)
- Guard: force_continue when questions_asked < MIN_REQUIRED_QUESTIONS or time_remaining > 0
- Always injects: "Time remaining: X minutes. Do NOT conclude the interview. Ask the next interview question."
Backend timer loop remains the hard safety cutoff to end the interview.
"""

from typing import Any, Callable

from livekit.agents import llm

from services.session_time_store import get_store  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist  # type: ignore
from utils.phase_timing import get_current_phase  # type: ignore

logger = get_logger(__name__)

# Guard: minimum questions before allowing any conclusion hint (used with backend get_questions_asked)
MIN_REQUIRED_QUESTIONS = 8


def _get_questions_asked() -> int:
    try:
        from app.services.history_managed_llm_wrapper import get_questions_asked  # type: ignore
        return get_questions_asked()
    except Exception:
        return 0


def _injection_one_liner(minutes_remaining: float) -> str:
    """Always-injected line: time remaining + do not conclude + ask next question."""
    return (
        f"Time remaining: {int(minutes_remaining)} minutes. "
        "Do NOT conclude the interview. Ask the next interview question."
    )


def _build_time_context_message(
    elapsed_minutes: float,
    minutes_remaining: float,
    duration_minutes: int,
    current_phase: str,
    force_continue: bool = False,
) -> str:
    """Build system message with time context and phase-aware instruction."""
    one_liner = _injection_one_liner(minutes_remaining)
    # Time context block (passed to LLM before each question)
    time_context_block = (
        f"TIME CONTEXT (determined before this response):\n"
        f"- elapsed_minutes: {int(elapsed_minutes)}\n"
        f"- remaining_minutes: {int(minutes_remaining)}\n"
        f"- current_phase: {current_phase}\n"
        f"- total_duration_minutes: {duration_minutes}\n\n"
        f"You MUST decide the next question or response based on current_phase. "
        f"Do NOT ask introduction/background questions in technical or mcq phase. "
        f"Do NOT ask technical/coding questions in introduction or conclusion phase. "
        f"In conclusion phase do NOT ask any new questions; only conclude."
    )

    # Guard: if we have not asked enough questions or time remains, do not allow conclusion
    if force_continue:
        return (
            f"{one_liner}\n\n"
            f"REMAINING_MINUTES={int(minutes_remaining)}. DO NOT CONCLUDE. ASK NEXT QUESTION.\n\n"
            f"CRITICAL TIME CONTEXT:\n"
            f"- elapsed_minutes: {int(elapsed_minutes)}, remaining_minutes: {int(minutes_remaining)}, "
            f"current_phase: {current_phase}\n\n"
            f"You are FORBIDDEN from ending, concluding, or wrapping up. "
            f"Do NOT say 'approaching the end', 'do you have any questions for me', 'thank you for your time', or similar. "
            f"Ask the NEXT interview question appropriate for current_phase.\n\n"
            f"{time_context_block}"
        )

    if minutes_remaining > 0 and minutes_remaining <= 2:
        return (
            f"{one_liner}\n\n"
            f"⏰ TIME ALERT: ONLY {int(minutes_remaining)} MINUTES REMAINING "
            f"(minute {int(elapsed_minutes)} of {duration_minutes}). current_phase={current_phase}\n\n"
            f"INSTRUCTION - CONCLUDE NOW:\n"
            f"• You MUST announce we are concluding in this response\n"
            f"• Say exactly: 'We have about {int(minutes_remaining)} minute(s) left, so let us conclude.' or 'That brings us to the end.'\n"
            f"• Do NOT ask any new questions\n"
            f"• One short sentence only\n"
            f"• Do NOT say full goodbye yet (system will send that in a moment)\n\n"
            f"{time_context_block}"
        )
    if minutes_remaining > 2 and minutes_remaining <= 5:
        return (
            f"{one_liner}\n\n"
            f"⏰ TIME ALERT: {int(minutes_remaining)} MINUTES REMAINING "
            f"(minute {int(elapsed_minutes)} of {duration_minutes}). current_phase={current_phase}\n\n"
            f"INSTRUCTION - BEGIN WRAPPING UP:\n"
            f"• You MUST mention the time remaining in this response\n"
            f"• Say something like: 'We have about {int(minutes_remaining)} minutes left.' or 'We are coming to the end.'\n"
            f"• Then ask at most ONE or TWO final questions from the question bank\n"
            f"• Do NOT say full goodbye yet - just acknowledge the time and continue with final questions\n\n"
            f"{time_context_block}"
        )
    # Normal: phase-aware next question
    if current_phase == "conclusion":
        return (
            f"{one_liner}\n\n"
            f"⏰ current_phase=conclusion. Minute {int(elapsed_minutes)} of {duration_minutes}. "
            f"Do NOT ask any new questions. Deliver closing only when the system sends END_INTERVIEW.\n\n"
            f"{time_context_block}"
        )
    # Strong prohibition: with 5+ min left the model must NOT conclude or offer "any questions for me"
    return (
        f"{one_liner}\n\n"
        f"REMAINING_MINUTES={int(minutes_remaining)}. DO NOT CONCLUDE. ASK NEXT QUESTION.\n\n"
        f"CRITICAL TIME CONTEXT (computed before this question):\n"
        f"- elapsed_minutes: {int(elapsed_minutes)}, remaining_minutes: {int(minutes_remaining)}, "
        f"current_phase: {current_phase}\n\n"
        f"⚠️  ABSOLUTE PROHIBITION - DO NOT CONCLUDE EARLY:\n"
        f"• You are FORBIDDEN from ending, concluding, or wrapping up the interview\n"
        f"• You MUST NOT say: 'approaching the end', 'almost at the end', 'final comments', 'last question', "
        f"'wrapping up', 'let's conclude', 'that's all', 'do you have any questions for me', 'thank you for your time'\n"
        f"• You MUST NOT thank them for their time or wish them luck until the system tells you to conclude\n"
        f"• There is still {int(minutes_remaining)} minutes left - you MUST ask the NEXT question appropriate for current_phase\n\n"
        f"YOUR ONLY JOB: Ask the NEXT question appropriate for current_phase={current_phase} "
        f"(introduction = intro/background; technical = technical/coding/domain; mcq = MCQ/logical). "
        f"One question at a time.\n\n"
        f"{time_context_block}"
    )


class TimeContextLLMWrapper:
    """
    Injects time context BEFORE each LLM call. Elapsed time is calculated here;
    current_phase is determined from elapsed time; both are passed to the LLM
    so it decides the next question based on phase (not only background timer).
    """

    def __init__(self, original_chat: Callable[..., Any]):
        self._original_chat = original_chat

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        chat_ctx = kwargs.get("chat_ctx")
        if chat_ctx is None or not isinstance(chat_ctx, llm.ChatContext):
            logger.warning(
                "⏰ Time context NOT injected: chat_ctx missing or not ChatContext (kwargs keys: %s)",
                list(kwargs.keys()),
            )
            return self._original_chat(*args, **kwargs)
        start_time, duration_minutes, base_template = get_store()
        if start_time is None or duration_minutes is None:
            logger.warning(
                "⏰ Time context NOT injected: session store not set (start_time=%s, duration=%s). "
                "Candidate may not have joined yet or interview_loop not running.",
                "set" if start_time else "None",
                duration_minutes,
            )
            return self._original_chat(*args, **kwargs)
        try:
            now = get_now_ist()
            # 1) Elapsed time calculated BEFORE generating next question
            elapsed_minutes = (now - start_time).total_seconds() / 60
            minutes_remaining = max(0.0, duration_minutes - elapsed_minutes)
            # 2) Phase determination from elapsed time (same rules as 30/45 min, scaled if late join)
            current_phase = get_current_phase(
                elapsed_minutes, duration_minutes, base_template
            )
            questions_asked = _get_questions_asked()
            # Do not allow conclusion until enough questions asked or time has really run out
            force_continue = (
                questions_asked < MIN_REQUIRED_QUESTIONS
                or minutes_remaining > 2
            )
            time_msg = _build_time_context_message(
                elapsed_minutes,
                minutes_remaining,
                duration_minutes,
                current_phase,
                force_continue=force_continue,
            )
            chat_ctx.add_message(role="system", content=time_msg)
            logger.info(
                "⏰ Time context injected: elapsed=%.1f min, remaining=%.1f min, phase=%s, questions_asked=%s, force_continue=%s",
                elapsed_minutes,
                minutes_remaining,
                current_phase,
                questions_asked,
                force_continue,
            )
        except Exception as e:
            logger.warning("⏰ Could not inject time context: %s", e, exc_info=True)
        return self._original_chat(*args, **kwargs)
