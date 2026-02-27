"""
Time Context LLM Wrapper

Injects time-aware focus guidance before each LLM call via a copy of chat context —
never adds INTERNAL text to the persistent chat_ctx. Sanitizes chat context first.
Timing is centralized in utils.interview_timer.
"""

import contextvars
from typing import Any, Callable, Optional

from livekit.agents import llm

from services.session_time_store import get_store  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist  # type: ignore
from utils.interview_timer import get_time_remaining, get_interview_focus  # type: ignore
from services.output_sanitizer import remove_internal_blocks  # type: ignore

logger = get_logger(__name__)

# Context variable for turn-specific instructions (to avoid polluting persistent chat history)
_turn_instructions_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("turn_instructions", default=None)


def set_turn_instructions(instructions: Optional[str]) -> None:
    """Set instructions for the next LLM turn only."""
    _turn_instructions_var.set(instructions)


def get_turn_instructions() -> Optional[str]:
    """Get instructions for the current LLM turn."""
    return _turn_instructions_var.get()


async def generate_reply_with_instructions(session, instructions: str) -> None:
    """
    Trigger an AI response with specific instructions without polluting
    the persistent chat context/history.
    """
    set_turn_instructions(instructions)
    try:
        # Use a distinctive trigger that the wrapper will hide from the LLM.
        # This ensures session.generate_reply() actually triggers a call.
        await session.generate_reply(instructions="[INTERNAL_TRIGGER]")
        
        # Cleanup: Remove the trigger from the session's persistent chat_ctx
        # so it never appears in the conversation array.
        try:
            if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                messages = session.chat_ctx.messages
                if messages and messages[-1].content == "[INTERNAL_TRIGGER]":
                    messages.pop()
        except (AttributeError, IndexError):
            pass
    finally:
        # Always clear after the turn to ensure no leaks into subsequent turns
        set_turn_instructions(None)


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
            "You are in the INTRODUCTION phase.",
            "Keep asking follow-up questions about the candidate's background, experience, and recent work.",
            "Do NOT move to technical questions yet.",
            "Do NOT wrap up or conclude anything.",
            "If you feel you have covered the intro well, ask ONE MORE follow-up about something specific they mentioned.",
            "NEVER leave this phase on your own — only TIME CONTEXT changing to technical means intro is over.",
            "The interview is NOT over until END_INTERVIEW arrives. Keep asking questions no matter what.",
        ]
    elif focus == "technical":
        instructions = [
            "You are in the TECHNICAL phase.",
            "After every candidate answer, immediately ask a follow-up or a brand new technical question.",
            "Never stop asking. If you run out of topics ask about system design, trade-offs, or past project decisions.",
            "Do NOT wrap up. Do NOT say goodbye. Do NOT move to closing under any circumstance.",
            "NEVER conclude this phase on your own.",
            "The interview is NOT over until END_INTERVIEW arrives. Keep asking questions no matter what.",
        ]
    elif focus == "coding":
        instructions = [
            "You are in the CODING and MCQ phase.",
            "If you have not asked a coding question yet — ask one now. Tell the candidate to open the code editor (</> in the bottom bar).",
            "After the coding question is submitted and probed, move to MCQ questions.",
            "Ask MCQ questions one at a time. After every answer give brief feedback then ask the next MCQ immediately.",
            "Do NOT do only MCQs if coding has not happened yet — coding comes first.",
            "Do NOT wrap up. Do NOT say goodbye.",
            "Keep asking coding or MCQ questions until TIME CONTEXT changes.",
            "The interview is NOT over until END_INTERVIEW arrives. Keep asking questions no matter what.",
        ]
    elif focus == "final":
        instructions = [
            "You are in the FINAL phase.",
            "Ask open-ended questions — strengths, challenges, learnings, what they would do differently.",
            "Do NOT say goodbye. Do NOT say that concludes.",
            "Do NOT deliver the closing statement.",
            "END_INTERVIEW has NOT arrived yet. Keep talking.",
            "The interview is NOT over until END_INTERVIEW arrives. Keep asking questions no matter what.",
        ]
    else:
        # wrap_up
        instructions = [
            "Stay fully engaged. Ask one last open-ended question.",
            "END_INTERVIEW is arriving very soon but has NOT arrived yet. Do NOT conclude yet.",
            "Never say goodbye until END_INTERVIEW is received.",
            "The interview is NOT over until END_INTERVIEW arrives.",
        ]

    return (
        f"{header}"
        + "\n".join(f"- {i}" for i in instructions) + "\n"
        "- ONE TURN = ONE QUESTION. Ask one question, then STOP and wait.\n"
        "- NEVER say goodbye or conclude until END_INTERVIEW.\n"
        "ABSOLUTE RULE: A natural feeling that the conversation is complete is NOT permission to close. "
        "Only END_INTERVIEW arriving in your instructions is permission to close. Until then, always ask another question.\n"
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

        # 0) Intercept and hide [INTERNAL_TRIGGER] from the LLM
        # This ensures the model only sees the turn instructions, not the trigger message.
        items = getattr(chat_ctx, "messages", None) or getattr(chat_ctx, "items", [])
        if items and len(items) > 0:
            last_msg = items[-1]
            last_content = getattr(last_msg, "content", "")
            if last_content == "[INTERNAL_TRIGGER]":
                logger.debug("⏰ Intercepted [INTERNAL_TRIGGER] - hiding from LLM")
                chat_ctx = chat_ctx.copy()
                if hasattr(chat_ctx, "messages"):
                    chat_ctx.messages.pop()
                    logger.debug("   [OK] Popped from chat_ctx.messages copy")
                elif hasattr(chat_ctx, "items"):
                    chat_ctx.items.pop()
                    logger.debug("   [OK] Popped from chat_ctx.items copy")
                kwargs["chat_ctx"] = chat_ctx

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
            
            # 2) Inject turn-specific instructions (e.g. greeting, evaluation) if set
            turn_instructions = get_turn_instructions()
            if turn_instructions:
                system_prompt = f"{system_prompt}\n\n[INTERNAL — TURN-SPECIFIC INSTRUCTIONS]\n{turn_instructions}\n[END INTERNAL CONTEXT]"
            
            kwargs = {**kwargs, "chat_ctx": _chat_ctx_with_system_prepended(chat_ctx, system_prompt)}
        except Exception as e:
            logger.warning("⏰ Could not inject time context: %s", e, exc_info=True)
        return self._original_chat(*args, **kwargs)
