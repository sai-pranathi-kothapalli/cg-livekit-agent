"""
Plugin Service

Manages initialization and configuration of LiveKit plugins
(STT, LLM, TTS, VAD, Avatar) with proper error handling.
"""

import json
import os
from typing import Dict, Any, Optional

from livekit import rtc
from livekit.agents import AgentSession
from livekit.plugins import (  # type: ignore
    openai,
    silero,
)

# Google Gemini (primary LLM)
try:
    from livekit.plugins import google  # type: ignore (for Gemini)
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    google = None  # type: ignore

from app.config import Config  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from app.utils.exceptions import ConfigurationError, ServiceError  # type: ignore

logger = get_logger(__name__)


class PluginService:
    """
    Service for managing LiveKit agent plugins.
    
    Handles initialization, configuration, and error handling
    for all plugin types used by the interview agent.
    """
    
    # Domain-specific keywords for STT accuracy
    STT_KEYWORDS = [
        ("Regional Rural Bank", 10), ("RRB", 10), ("Probationary Officer", 10), ("PO", 10),
        ("NABARD", 10), ("RBI", 10), ("Banking", 10), ("Financial Inclusion", 10),
        ("Savings Account", 10), ("Current Account", 10), ("Fixed Deposit", 10), ("KYC", 10),
        ("Loan", 10), ("Interest Rate", 10), ("Repo Rate", 10), ("Base Rate", 10),
        ("NPA", 10), ("Non-Performing Asset", 10), ("PMJDY", 10), ("Mudra", 10),
        ("Digital Banking", 10), ("Customer Service", 10), ("Balance Sheet", 10), ("Account Opening", 10),
        ("Commercial Bank", 10), ("Cooperative Bank", 10), ("Rural Banking", 10), ("Banking Operations", 10),
        ("Recurring Deposit", 10), ("Overdraft", 10), ("Credit", 10), ("Debit", 10)
    ]
    
    def __init__(self, config: Config):
        """
        Initialize plugin service.
        
        Args:
            config: Application configuration instance
        """
        self.config = config
        logger.debug("PluginService initialized")
    
    async def initialize_plugins(
        self, 
        room: rtc.Room,
        booking_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initialize all required plugins for the agent session.
        
        Args:
            room: LiveKit room instance (for transcript forwarding)
            booking_token: Booking token (for session identification)
            
        Returns:
            Dictionary containing initialized plugins:
            {
                "stt": STT plugin,
                "llm": LLM plugin (with transcript forwarding),
                "tts": TTS plugin,
                "vad": VAD plugin
            }
            
        Raises:
            ConfigurationError: If required API keys are missing
            ServiceError: If plugin initialization fails
        """
        try:
            # Initialize STT plugin
            stt_plugin = self._initialize_stt()
            
            # Initialize LLM plugin with transcript forwarding
            llm_plugin = self._initialize_llm(room, booking_token)
            
            # Initialize TTS plugin
            tts_plugin = self._initialize_tts()
            
            # Initialize VAD plugin
            vad_plugin = self._initialize_vad()
            
            logger.info("[OK] All plugins initialized successfully")
            
            return {
                "stt": stt_plugin,
                "llm": llm_plugin,
                "tts": tts_plugin,
                "vad": vad_plugin,
            }
            
        except Exception as e:
            logger.error(f"Failed to initialize plugins: {e}", exc_info=True)
            raise ServiceError(f"Plugin initialization failed: {str(e)}", "PluginService")
    
    def _initialize_stt(self):
        """
        Initialize STT plugin (self-hosted only).
        
        Returns:
            Configured STT plugin
        """
        logger.info("[DEBUG] STT CONFIGURATION: Self-hosted only")
        if not self.config.openai.stt_enabled:
            raise ConfigurationError("Self-hosted STT is required. Set SELF_HOSTED_STT_ENABLED=true.")
        logger.info(f"   Base URL: {self.config.openai.stt_base_url}")
        logger.info(f"   Model: {self.config.openai.stt_model}")
        stt_plugin = openai.STT(
            base_url=f"{self.config.openai.stt_base_url}/stt/v1",
            model=self.config.openai.stt_model,
        )
        logger.info("   [OK] Self-hosted STT initialized")
        return stt_plugin
    
    def _initialize_llm(self, room: rtc.Room, booking_token: Optional[str] = None):
        """
        Initialize LLM plugin: Gemini (primary) -> self-hosted Qwen (fallback).
        
        Args:
            room: LiveKit room instance
            booking_token: Booking token (for session identification)
            
        Returns:
            Configured LLM plugin
        """
        logger.info("[DEBUG] LLM CONFIGURATION: Gemini (primary) -> Qwen (fallback)")
        
        # Primary: Google Gemini
        if not GOOGLE_AVAILABLE:
            raise ConfigurationError("Gemini plugin required. Install with: pip install livekit-plugins-google")
        primary_llm = google.LLM(
            model=self.config.gemini_llm.model,
            api_key=self.config.gemini_llm.api_key,
        )
        has_key = bool(self.config.gemini_llm.api_key and self.config.gemini_llm.api_key.strip())
        logger.info(f"   [OK] Primary LLM (Gemini {self.config.gemini_llm.model}) initialized, API key set={has_key}")
        if not has_key:
            logger.warning("   [WARN] GEMINI_API_KEY is missing or empty - Gemini will fail at runtime!")
        
        # Fallback: self-hosted Qwen
        fallback_llm = None
        if self.config.openai.llm_enabled:
            try:
                fallback_llm = openai.LLM(
                    base_url=f"{self.config.openai.llm_base_url}/llm/v1",
                    model=self.config.openai.llm_model,
                    api_key=self.config.openai.api_key,
                )
                logger.info(f"   [OK] Fallback LLM (Qwen {self.config.openai.llm_model}) initialized")
            except Exception as e:
                logger.warning(f"   [WARN]  Fallback Qwen LLM failed: {e}")
        
        if fallback_llm:
            from services.fallback_llm import FallbackLLM
            llm_plugin = FallbackLLM(
                primary_llm=primary_llm,
                fallback_llm=fallback_llm,
                max_primary_failures=3
            )
            logger.info("   [OK] LLM: Gemini (primary) -> Qwen (fallback after 3 failures)")
        else:
            llm_plugin = primary_llm
            logger.warning("   [WARN]  No LLM fallback - session will close on Gemini failures")
        
        # Wrap LLM chat for transcript forwarding and history management
        if hasattr(llm_plugin, 'chat'):
            from app.services.transcript_service import TranscriptForwardingService  # type: ignore
            from app.services.history_managed_llm_wrapper import HistoryManagedLLMWrapper  # type: ignore
            from services.timing_llm_wrapper import TimingLLMWrapper
            from services.quiet_transcript_wrapper import QuietTranscriptWrapper
            from services.transcript_storage_wrapper import TranscriptStorageWrapper
            
            # Create transcript service and wrap it to reduce spam
            original_transcript_service = TranscriptForwardingService(room)
            quiet_transcript_service = QuietTranscriptWrapper(original_transcript_service)
            
            # Wrap with storage to save transcripts to database (pass booking_token so MongoDB has correct key)
            transcript_service = TranscriptStorageWrapper(
                original_transcript_service=quiet_transcript_service,
                room_name=room.name,
                booking_token=booking_token,
            )
            
            original_chat = llm_plugin.chat
            
            # [OK] Inject current minute into chat context for pacing; conclusion triggered by backend at 90%
            from services.time_context_llm_wrapper import TimeContextLLMWrapper
            time_context_wrapper = TimeContextLLMWrapper(original_chat)
            # Wrap with history management
            history_wrapper = HistoryManagedLLMWrapper(
                original_chat=time_context_wrapper,
                transcript_service=transcript_service,
                session_id=room.name,  # [OK] Pass room name as session_id
                max_conversation_tokens=self.config.MAX_CONVERSATION_TOKENS,
                max_messages=self.config.MAX_CONVERSATION_MESSAGES,
                min_messages_to_keep=self.config.MIN_CONVERSATION_MESSAGES
            )
            
            # [OK] Add timing wrapper on top of history wrapper
            timing_wrapper = TimingLLMWrapper(history_wrapper)
            
            llm_plugin.chat = timing_wrapper
            logger.info(
                f"   [OK] LLM chat wrapped: time context, transcript, history, timing "
                f"(max_tokens={self.config.MAX_CONVERSATION_TOKENS}, "
                f"max_messages={self.config.MAX_CONVERSATION_MESSAGES})"
            )
        
        return llm_plugin
    
    def _initialize_tts(self):
        """
        Initialize TTS plugin (self-hosted only).
        
        Returns:
            Configured TTS plugin
        """
        logger.info("[DEBUG] TTS CONFIGURATION: Self-hosted only")
        if not self.config.openai.tts_enabled:
            raise ConfigurationError("Self-hosted TTS is required. Set SELF_HOSTED_TTS_ENABLED=true.")
        logger.info(f"   Base URL: {self.config.openai.tts_base_url}")
        logger.info(f"   Model: {self.config.openai.tts_model}, Voice: {self.config.openai.tts_voice}")
        tts_plugin = openai.TTS(
            base_url=f"{self.config.openai.tts_base_url}/tts/v1",
            model=self.config.openai.tts_model,
            voice=self.config.openai.tts_voice,
            api_key=self.config.openai.api_key,
        )
        logger.info("   [OK] Self-hosted TTS initialized")
        return tts_plugin
    
    def _initialize_vad(self) -> silero.VAD:
        """
        Initialize Silero VAD plugin.
        
        Returns:
            Configured Silero VAD plugin
        """
        logger.info("[DEBUG] SILERO VAD CONFIGURATION:")
        logger.info(f"   Min Speech Duration: {self.config.silero_vad.min_speech_duration}s")
        logger.info(f"   Min Silence Duration: {self.config.silero_vad.min_silence_duration}s")
        logger.info(f"   Activation Threshold: {self.config.silero_vad.activation_threshold}")
        
        vad_plugin = silero.VAD.load(
            min_speech_duration=self.config.silero_vad.min_speech_duration,
            min_silence_duration=self.config.silero_vad.min_silence_duration,
            activation_threshold=self.config.silero_vad.activation_threshold,
        )
        
        logger.info("   [OK] Silero VAD plugin initialized (optimized for background noise filtering)")
        
        return vad_plugin

