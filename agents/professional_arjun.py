"""
Professional Arjun Agent

LiveKit agent for structured technical interviews with optional
candidate context and dashboard-driven instructions.
Uses phase-based prompt (Phase 1: Intro, Phase 2: Technical/Coding/Scenario, Phase 3: MCQ & Closing)
when no dashboard instructions exist; otherwise uses provided base_instructions.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone

from livekit.agents import Agent

from app.utils.logger import get_logger  # type: ignore


logger = get_logger(__name__)


class ProfessionalArjun(Agent):
    """
    Professional Arjun - technical interview agent.

    All instructions are centrally managed in the dashboard (system_instructions table).
    This class handles the logic for building the final instruction set from those base instructions.
    """
    
    def __init__(
        self, 
        candidate_profile: Optional[Dict[str, Any]] = None, 
        base_instructions: Optional[str] = None,
        duration_minutes: int = 30
    ) -> None:
        """
        Initialize Professional Arjun agent.
        
        Args:
            candidate_profile: Optional structured dictionary of candidate application data
            base_instructions: Optional override for base system instructions
            duration_minutes: Interview duration in minutes (default 30). Agent adapts behavior based on this.
        """
        self.duration_minutes = duration_minutes
        self.latest_code_version = 0
        instructions = self._build_instructions(candidate_profile, base_instructions)
        
        super().__init__(
            instructions=instructions,
            min_endpointing_delay=0.0,
        )
        
        logger.info(
            f"ProfessionalArjun agent initialized "
            f"(profile_context={'yes' if candidate_profile else 'no'}, "
            f"dynamic_prompt={'yes' if base_instructions else 'no'}, "
            f"duration={duration_minutes} minutes)"
        )
    
    def on_error(self, error: Exception) -> None:
        """
        Handle errors gracefully to prevent session termination.
        
        Args:
            error: The error that occurred
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        # Check if it's an STT error
        is_stt_error = (
            "stt" in error_msg.lower() or
            "STT" in error_type or
            "speech" in error_msg.lower() or
            "transcription" in error_msg.lower() or
            "recognize" in error_msg.lower()
        )
        
        if is_stt_error:
            logger.error(
                f"⚠️  STT Error detected: {error_type}: {error_msg}",
                exc_info=True
            )
            logger.warning(
                "   ⚠️  STT errors can cause session closure. "
                "Check STT API server health at: " + 
                (getattr(self, '_stt_url', 'N/A') if hasattr(self, '_stt_url') else 'N/A')
            )
        else:
            logger.error(
                f"⚠️  Agent error caught: {error_type}: {error_msg}",
                exc_info=True
            )
        
        # Log context for debugging
        logger.error(
            f"   Error context: Agent session active, attempting to continue..."
        )
        
        # Don't re-raise - let the session continue
        # The error is logged but doesn't stop the interview
        logger.warning("🔄 Continuing session despite error - interview will continue")
    
    def _adapt_instructions_for_duration(self, instructions: str, duration_minutes: int) -> str:
        """Replace duration placeholders (30 minutes / 30-minute) with configured duration."""
        adapted = instructions.replace("30 minutes", f"{duration_minutes} minutes")
        adapted = adapted.replace("30-minute", f"{duration_minutes}-minute")
        return adapted
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~3 chars per token."""
        return 0 if not text else len(text) // 3
    
    def update_code_version(self, version: int):
        """Update the latest code version received from the frontend."""
        if version > self.latest_code_version:
            self.latest_code_version = version
            logger.debug(f"Code version updated to {version}")    

    def _build_instructions(
        self,
        candidate_profile: Optional[Dict[str, Any]],
        base_instructions: Optional[str] = None
    ) -> str:
        """
        Build agent instructions with optional candidate profile context.
        Automatically truncates if instructions exceed context window.
        When no base_instructions provided: raise ValueError.
        When base_instructions provided: use it as-is (with duration adaptation and date injection).
        """
        if not base_instructions:
            raise ValueError(
                "No system instructions provided. "
                "Configure system instructions in the dashboard before starting an interview."
            )
        base_instructions_text = base_instructions
        # Safety: Replace any remaining placeholders in dashboard instructions with empty string
        # (entrypoint.py should have already substituted, but this ensures no {full_name} leaks through)
        common_placeholders = ["full_name", "email", "graduation_degree", "skills", "name"]
        prof = candidate_profile or {}
        for placeholder in common_placeholders:
            if "{" + placeholder + "}" in base_instructions_text:
                val = prof.get(placeholder)
                replacement = str(val).strip() if val is not None else ""
                base_instructions_text = base_instructions_text.replace("{" + placeholder + "}", replacement)
        
        core_instructions = self._adapt_instructions_for_duration(base_instructions_text, self.duration_minutes)

        # Inject current date so the LLM does not assume 2024 (e.g. candidate says "2025 graduate" – do not contradict)
        try:
            from app.utils.datetime_utils import get_now_ist  # type: ignore
            now = get_now_ist()
        except Exception:
            now = datetime.now(timezone.utc)
        current_date_str = now.strftime("%Y-%m-%d (current year %Y)")
        core_instructions = core_instructions.replace("[INJECT_AT_RUNTIME]", current_date_str)

        final_tokens = self._estimate_tokens(core_instructions)
        if final_tokens > 3500:
            logger.warning(
                f"Instructions exceed 3500 tokens ({final_tokens}). Consider reducing dashboard instructions."
            )
        else:
            logger.info(f"Instructions built: {final_tokens} tokens")
        return core_instructions

