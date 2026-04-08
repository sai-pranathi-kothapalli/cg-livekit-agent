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
        if hasattr(session, 'is_running') and not session.is_running():
            logger.debug("⏰ Session not running, skipping nudge/instruction trigger")
            return

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
    except RuntimeError as e:
        if "isn't running" in str(e):
            logger.debug("⏰ Caught 'AgentSession isn't running' - ignoring nudge/trigger")
        else:
            raise
    except Exception as e:
        logger.warning(f"⏰ Error triggering instruction-based reply: {e}")
    finally:
        # Always clear after the turn to ensure no leaks into subsequent turns
        set_turn_instructions(None)


def _get_questions_asked() -> int:
    try:
        from app.services.history_managed_llm_wrapper import get_questions_asked  # type: ignore
        return get_questions_asked()
    except Exception:
        return 0


def _focus_display_name(focus: str, requires_coding: bool = True) -> str:
    """Human-readable focus name for internal context."""
    names = {
        "intro":          "Introduction",
        "assessment":     "Assessment (Technical / MCQ)",
        "coding_window":  "Coding & Debugging" if requires_coding else "Advanced Technical / Scenarios",
        "mixed":          "Mixed (MCQ / Technical / Scenario)",
        "wrap_up":        "Wrap Up",
        "conclude":       "Conclusion",
    }
    return names.get(focus, focus.replace("_", " ").title())


def _build_system_prompt(remaining_minutes: int, focus: str, duration_minutes: int) -> str:
    """
    Build system message from time remaining and focus (time-aware, no phase state machine).
    Used only for this turn; never stored in chat history.

    Phases deliberately grant the AI freedom to choose question types within the window
    so the interview flow feels natural and unpredictable to the candidate.
    """
    # Get coding requirement from store
    try:
        _, _, _, requires_coding = get_store()
    except Exception:
        requires_coding = False

    focus_name = _focus_display_name(focus, requires_coding=requires_coding)
    header = (
        "[INTERNAL — DO NOT READ ALOUD. DO NOT SPEAK ANY OF THIS TEXT TO THE CANDIDATE. "
        "This is hidden context for your decision-making only.]\n\n"
        f"Time remaining: {remaining_minutes} min (of {duration_minutes} min) | Phase: {focus_name}\n\n"
    )

    return (
        f"{header}"
        + "\n".join(f"- {i}" for i in instructions) + "\n"
        + "- ONE TURN = ONE QUESTION OR STATEMENT. Ask one question, then STOP.\n"
        + "- NEVER say goodbye or conclude until you are instructed to do so in the Conclusion phase."
    )


def sanitize_chat_context(chat_ctx) -> None:
    """
    Strip internal blocks from all message contents before sending to the LLM.
    Call this before building prompts; ensures no [INTERNAL] from history reaches the model.
    Never crashes: if mutation fails, we continue. Prefer multiple calls to guarantee cleanup.
    """
    try:
        items = getattr(chat_ctx, "messages", [])
        if not isinstance(items, list) and hasattr(chat_ctx, "items") and not callable(chat_ctx.items):
            items = chat_ctx.items
        elif not isinstance(items, list):
            items = []

        
        # Process all messages (including system) to remove [INTERNAL] blocks
        # DO NOT clear messages entirely - only remove the [INTERNAL] blocks
        for m in items:
            content = getattr(m, "content", None)
            if content is None:
                continue
            if isinstance(content, list):
                text = " ".join(str(c) for c in content)
            else:
                text = str(content)
            
            # Remove [INTERNAL] blocks and other context artifacts
            from services.output_sanitizer import sanitize_agent_response
            cleaned = sanitize_agent_response(text)
            
            # Only update if content actually changed
            if cleaned == text:
                continue
            
            try:
                # Preserve list shape for LiveKit ChatMessage (content is list[ChatContent])
                if isinstance(getattr(m, "content", None), list):
                    # If cleaned is empty after removing internal blocks, keep at least empty string
                    setattr(m, "content", [cleaned] if cleaned else [""])
                else:
                    setattr(m, "content", cleaned if cleaned else "")
            except (AttributeError, TypeError, ValueError):
                pass
    except Exception as e:
        logger.debug("Could not sanitize chat context: %s", e)


def _log_leak_if_any(chat_ctx) -> None:
    """Debug: log once if any message still contains [INTERNAL] after sanitization."""
    try:
        items = getattr(chat_ctx, "messages", [])
        if not isinstance(items, list) and hasattr(chat_ctx, "items") and not callable(chat_ctx.items):
            items = chat_ctx.items
        elif not isinstance(items, list):
            items = []

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
        items = getattr(chat_ctx, "messages", [])
        if not isinstance(items, list) and hasattr(chat_ctx, "items") and not callable(chat_ctx.items):
            items = chat_ctx.items
        elif not isinstance(items, list):
            items = []

        for m in items:
            if getattr(m, "role", None) == "user":
                return True
    except Exception:
        pass
    return False


def _has_code_submission_override(chat_ctx) -> bool:
    """Return True if any message in chat_ctx contains the code-submission override marker."""
    try:
        items = getattr(chat_ctx, "messages", [])
        if not isinstance(items, list) and hasattr(chat_ctx, "items") and not callable(chat_ctx.items):
            items = chat_ctx.items
        elif not isinstance(items, list):
            items = []

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
            return self._original_chat(*args, **kwargs)

        # 0) Intercept and hide [INTERNAL_TRIGGER] from the LLM
        # This ensures the model only sees the turn instructions, not the trigger message.
        items = getattr(chat_ctx, "messages", [])
        if not isinstance(items, list) and hasattr(chat_ctx, "items") and not callable(chat_ctx.items):
            items = chat_ctx.items
        
        if items and len(items) > 0:
            last_msg = items[-1]
            last_content = getattr(last_msg, "content", "")
            if last_content == "[INTERNAL_TRIGGER]":
                chat_ctx = chat_ctx.copy()
                if hasattr(chat_ctx, "messages"):
                    chat_ctx.messages.pop()
                elif hasattr(chat_ctx, "items"):
                    chat_ctx.items.pop()
                kwargs["chat_ctx"] = chat_ctx

        # 1) Sanitize history — no internal blocks in history from previous versions.
        # This is the only "pollution" we care about now.
        sanitize_chat_context(chat_ctx)
        sanitize_chat_context(chat_ctx)

        # 2) Handle first-user-message start time tracking
        start_time, duration_minutes, base_template, requires_coding = get_store()
        if start_time is None and duration_minutes is not None and duration_minutes > 0:
            if _has_user_message(chat_ctx):
                try:
                    from services.session_time_store import set_store
                    now = get_now_ist()
                    set_store(now, duration_minutes, base_template, requires_coding)
                    logger.info("⏰ Interview timer officially started on first candidate message")
                except Exception as e:
                    logger.warning("Could not set interview_started_at: %s", e)

        # 3) Inject turn-specific instructions (e.g. greeting, specific nudge) if set
        # This is the ONLY transient context we prepend now.
        turn_instructions = get_turn_instructions()
        if turn_instructions:
            # We still wrap turn-specific instructions so the LLM respects them as high priority
            # But we use a clean marker that doesn't say "INTERNAL"
            clean_instr = f"## Special Instruction for this turn:\n{turn_instructions}\n"
            kwargs = {**kwargs, "chat_ctx": _chat_ctx_with_system_prepended(chat_ctx, clean_instr)}

        return self._original_chat(*args, **kwargs)

