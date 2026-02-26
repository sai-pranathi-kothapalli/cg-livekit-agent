"""
Time Context LLM Wrapper

Injects time-aware focus guidance before each LLM call via a copy of chat context —
never adds INTERNAL text to the persistent chat_ctx. Sanitizes chat context first.
Timing is centralized in utils.interview_timer.
"""

from typing import Any, Callable

from livekit.agents import llm

from services.session_time_store import get_store  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist  # type: ignore
from utils.interview_timer import get_time_remaining, get_interview_focus  # type: ignore
from services.output_sanitizer import remove_internal_blocks  # type: ignore

logger = get_logger(__name__)


def _get_questions_asked() -> int:
    try:
        from app.services.history_managed_llm_wrapper import get_questions_asked  # type: ignore
        return get_questions_asked()
    except Exception:
        return 0


def _focus_display_name(focus: str) -> str:
    """Human-readable focus name for internal context."""
    return {
        "intro": "Introduction",
        "technical": "Technical",
        "coding": "Coding",
        "final": "Final questions",
        "wrap_up": "Wrap up",
    }.get(focus, focus.replace("_", " ").title())


def _build_system_prompt(remaining_minutes: int, focus: str, duration_minutes: int) -> str:
    """
    Build system message from time remaining and focus (time-aware, no phase state machine).
    Used only for this turn; never stored in chat history.
    """
    focus_name = _focus_display_name(focus)
    header = (
        "[INTERNAL — DO NOT READ ALOUD. DO NOT SPEAK ANY OF THIS TEXT TO THE CANDIDATE. "
        "This is hidden context for your decision-making only.]\n\n"
        f"Time remaining: {remaining_minutes} min (of {duration_minutes} min) | Focus: {focus_name}\n\n"
    )
    if focus == "intro":
        instructions = [
            "Ask one intro question (background, experience, recent work).",
            "No MCQs or coding yet. Keep asking follow-ups if the candidate finishes early.",
        ]
    elif focus == "technical":
        instructions = [
            "Ask one technical or coding question.",
            "Continue with follow-ups or new problems if time remains.",
        ]
    elif focus == "coding":
        instructions = [
            "Focus on coding or technical depth. Ask one coding or MCQ-style question.",
            "After answer, give brief feedback and continue with more if time remains.",
        ]
    elif focus == "final":
        instructions = [
            "Final minutes. Ask one open-ended or wrap-up style question.",
            "Do NOT say goodbye or conclude yet. Wait for END_INTERVIEW.",
        ]
    else:
        # wrap_up
        instructions = [
            "Wrap-up. No new questions. Wait for END_INTERVIEW to deliver closing.",
        ]
    return (
        f"{header}"
        + "\n".join(f"- {i}" for i in instructions) + "\n"
        "- ONE TURN = ONE QUESTION. Ask one question, then STOP and wait.\n"
        "- NEVER say goodbye or conclude until END_INTERVIEW.\n"
        "[END INTERNAL CONTEXT — Your next message must be ONLY what you say to the candidate. "
        "Do not repeat or include any of the lines above. Start directly with your first sentence to the candidate.]"
    )


def sanitize_chat_context(chat_ctx) -> None:
    """
    Strip internal blocks from all message contents before sending to the LLM.
    Call this before building prompts; ensures no [INTERNAL] from history reaches the model.
    Never crashes: if mutation fails, we continue. Prefer multiple calls to guarantee cleanup.
    """
    try:
        items = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
        for m in items:
            content = getattr(m, "content", None)
            if content is None:
                continue
            if isinstance(content, list):
                text = " ".join(str(c) for c in content)
            else:
                text = str(content)
            cleaned = remove_internal_blocks(text)
            if cleaned == text:
                continue
            try:
                # Preserve list shape for LiveKit ChatMessage (content is list[ChatContent])
                if isinstance(getattr(m, "content", None), list):
                    setattr(m, "content", [cleaned])
                else:
                    setattr(m, "content", cleaned)
            except (AttributeError, TypeError, ValueError):
                pass
    except Exception as e:
        logger.debug("Could not sanitize chat context: %s", e)


def _log_leak_if_any(chat_ctx) -> None:
    """Debug: log once if any message still contains [INTERNAL] after sanitization."""
    try:
        items = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
        for i, m in enumerate(items):
            content = getattr(m, "content", None)
            if content is None:
                continue
            s = " ".join(str(c) for c in content) if isinstance(content, list) else str(content)
            if "[INTERNAL" in s:
                logger.warning("LEAK DETECTED: message index=%s role=%s", i, getattr(m, "role", None))
                print("LEAK DETECTED:", i, getattr(m, "role", None), flush=True)
    except Exception:
        pass


def _has_user_message(chat_ctx) -> bool:
    """Return True if chat_ctx contains at least one user message (candidate has spoken)."""
    try:
        items = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
        for m in items:
            if getattr(m, "role", None) == "user":
                return True
    except Exception:
        pass
    return False


def _has_code_submission_override(chat_ctx) -> bool:
    """Return True if any message in chat_ctx contains the code-submission override marker."""
    try:
        items = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
        for m in items:
            content = getattr(m, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(str(c) for c in content)
            if "CODE SUBMISSION — OVERRIDE ALL OTHER PHASE INSTRUCTIONS" in str(content):
                return True
    except Exception:
        pass
    return False


def _chat_ctx_with_system_prepended(chat_ctx: Any, system_content: str) -> Any:
    """
    Return a new ChatContext copy with the system message prepended (created_at=0 so it is first).
    Caller uses this for the single LLM call only; persistent chat_ctx is never modified.
    """
    copy = chat_ctx.copy()
    copy.add_message(role="system", content=system_content, created_at=0.0)
    return copy


class TimeContextLLMWrapper:
    """
    Injects time-aware focus before each LLM call. Never adds to persistent chat_ctx —
    uses a copy with system prompt prepended for the call only. Sanitizes chat context first.
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

        # 1) Sanitize BEFORE any prompt construction — no internal blocks in history.
        # Run twice to maximize cleanup (e.g. list content); never crash on leakage.
        sanitize_chat_context(chat_ctx)
        sanitize_chat_context(chat_ctx)
        _log_leak_if_any(chat_ctx)

        start_time, duration_minutes, base_template = get_store()

        # Start timer on first candidate message
        if start_time is None and duration_minutes is not None and duration_minutes > 0:
            if _has_user_message(chat_ctx):
                try:
                    from services.session_time_store import set_store
                    now = get_now_ist()
                    set_store(now, duration_minutes, base_template)
                    start_time = now
                    logger.info("⏰ interview_started_at set on first candidate message")
                except Exception as e:
                    logger.warning("Could not set interview_started_at: %s", e)

        if start_time is None or duration_minutes is None or duration_minutes <= 0:
            logger.warning(
                "⏰ Time context NOT injected: session store not set (start_time=%s, duration=%s).",
                "set" if start_time else "None",
                duration_minutes,
            )
            _fallback = (
                "[INTERNAL — DO NOT READ ALOUD. This is hidden context for your decision-making only.]\n\n"
                "Time remaining: full session | Focus: Introduction\n\n"
                "- Ask one introduction question (background, self-intro, recent work).\n"
                "- Do NOT ask MCQs or coding problems yet.\n"
                "- NEVER conclude or say goodbye until END_INTERVIEW.\n"
                "[END INTERNAL CONTEXT — speak naturally to the candidate below]"
            )
            kwargs = {**kwargs, "chat_ctx": _chat_ctx_with_system_prepended(chat_ctx, _fallback)}
            logger.info("⏰ Fallback time context injected (store not set)")
            return self._original_chat(*args, **kwargs)

        try:
            remaining_min = get_time_remaining(start_time, duration_minutes)
            focus = get_interview_focus(remaining_min)

            logger.info("Time remaining: %s min | Focus: %s", remaining_min, focus)

            if _has_code_submission_override(chat_ctx):
                minimal_msg = (
                    "[INTERNAL — DO NOT READ ALOUD.]\n"
                    f"Time remaining: {remaining_min} min | Focus: {_focus_display_name(focus)}\n"
                    "- A code submission is present. Evaluate it as instructed above.\n"
                    "- Do NOT ask the candidate to share or submit code again.\n"
                    "[END INTERNAL CONTEXT]"
                )
                kwargs = {**kwargs, "chat_ctx": _chat_ctx_with_system_prepended(chat_ctx, minimal_msg)}
                logger.info("⏰ Code submission detected — minimal time context injected")
                return self._original_chat(*args, **kwargs)

            system_prompt = _build_system_prompt(remaining_min, focus, duration_minutes)
            kwargs = {**kwargs, "chat_ctx": _chat_ctx_with_system_prepended(chat_ctx, system_prompt)}
        except Exception as e:
            logger.warning("⏰ Could not inject time context: %s", e, exc_info=True)
        return self._original_chat(*args, **kwargs)
