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

# Optional cloud service imports
try:
    from livekit.plugins import deepgram  # type: ignore
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    deepgram = None  # type: ignore

try:
    from livekit.plugins import elevenlabs  # type: ignore
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    elevenlabs = None  # type: ignore

try:
    from livekit.plugins import google  # type: ignore (for Gemini)
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    google = None  # type: ignore

try:
    from services.grok_llm import GrokLLM  # type: ignore
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False
    GrokLLM = None  # type: ignore

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
        booking_token: Optional[str] = None,
        candidate_name: Optional[str] = None,
        candidate_role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initialize all required plugins for the agent session.
        
        Args:
            room: LiveKit room instance (for transcript forwarding)
            booking_token: Booking token (for orchestrator session_id)
            candidate_name: Candidate name (for orchestrator context)
            candidate_role: Candidate role (for orchestrator context)
            
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
            llm_plugin = self._initialize_llm(room, booking_token, candidate_name, candidate_role)
            
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
        Initialize STT plugin with optional cloud fallback.
        Supports enable/disable flags for both self-hosted and cloud services.
        
        Returns:
            Configured STT plugin (with fallback if enabled)
        """
        logger.info("[DEBUG] STT CONFIGURATION:")
        
        primary_stt = None
        fallback_stt = None
        
        # Initialize self-hosted STT if enabled
        if self.config.openai.stt_enabled:
            logger.info(f"   Self-hosted STT: ENABLED")
            logger.info(f"   Base URL: {self.config.openai.stt_base_url}")
            logger.info(f"   Model: {self.config.openai.stt_model}")
            try:
                # Use a higher timeout for self-hosted STT
                primary_stt = openai.STT(
                    base_url=f"{self.config.openai.stt_base_url}/stt/v1",
                    model=self.config.openai.stt_model,
                )
                logger.info("   [OK] Self-hosted STT initialized")
            except Exception as e:
                logger.error(f"   [ERR] Failed to initialize self-hosted STT: {e}", exc_info=True)
                if not self.config.elevenlabs_stt.enabled:
                    raise  # No fallback available, must fail
        else:
            logger.warning("   [WARN]  Self-hosted STT: DISABLED (via SELF_HOSTED_STT_ENABLED=false)")
        
        # Initialize cloud STT (Deepgram primary, ElevenLabs fallback)
        logger.info(f"   [DEBUG] Debug: deepgram_stt.enabled={self.config.deepgram_stt.enabled}")
        logger.info(f"   [DEBUG] Debug: DEEPGRAM_AVAILABLE={DEEPGRAM_AVAILABLE}")
        logger.info(f"   [DEBUG] Debug: deepgram api_key exists={bool(self.config.deepgram_stt.api_key)}")
        
        # Try Deepgram first
        if self.config.deepgram_stt.enabled and DEEPGRAM_AVAILABLE:
            if self.config.deepgram_stt.api_key:
                try:
                    fallback_stt = deepgram.STT(api_key=self.config.deepgram_stt.api_key)
                    logger.info("   [OK] Cloud STT (Deepgram) initialized")
                except Exception as e:
                    logger.warning(f"   [WARN]  Failed to initialize Deepgram STT: {e}")
        elif self.config.deepgram_stt.enabled and not DEEPGRAM_AVAILABLE:
            logger.warning("   [WARN]  Deepgram STT enabled but plugin not installed")
            logger.warning("   Install with: pip install livekit-plugins-deepgram")
        
        # Try ElevenLabs if Deepgram not available
        if not fallback_stt and self.config.elevenlabs_stt.enabled and ELEVENLABS_AVAILABLE:
            if self.config.elevenlabs_stt.api_key:
                try:
                    fallback_stt = elevenlabs.STT(api_key=self.config.elevenlabs_stt.api_key)
                    logger.info("   [OK] Cloud fallback STT (ElevenLabs) initialized")
                except Exception as e:
                    logger.warning(f"   [WARN]  Failed to initialize ElevenLabs STT: {e}")
        
        # Determine final STT configuration
        if primary_stt and fallback_stt:
            # Both enabled: use fallback wrapper
            from services.fallback_stt import FallbackSTT
            stt_plugin = FallbackSTT(
                primary_stt=primary_stt,
                fallback_stt=fallback_stt,
                max_primary_failures=3
            )
            logger.info("   [OK] STT with cloud fallback enabled (activates after 3 failures)")
        elif primary_stt:
            # Only self-hosted
            stt_plugin = primary_stt
            logger.warning("   [WARN]  Cloud fallback disabled - session will close on STT failures")
        elif fallback_stt:
            # Only cloud (self-hosted disabled)
            stt_plugin = fallback_stt
            logger.info("   [OK] Using cloud STT only (self-hosted disabled)")
        else:
            raise ConfigurationError("No STT service configured! Enable at least one STT service.")
        
        return stt_plugin
    
    def _initialize_llm(self, room: rtc.Room, booking_token: Optional[str] = None, candidate_name: Optional[str] = None, candidate_role: Optional[str] = None):
        """
        Initialize LLM plugin with optional cloud fallback.
        If orchestrator is enabled, use it as primary LLM (replaces all other LLMs).
        Otherwise: Self-hosted (primary) -> Gemini (first fallback) -> Grok (fallback of Gemini).
        
        Args:
            room: LiveKit room instance
            booking_token: Booking token (for session_id)
            candidate_name: Candidate name (for orchestrator context)
            candidate_role: Candidate role (for orchestrator context)
            
        Returns:
            Configured LLM plugin (with fallback if enabled)
        """
        # Check if orchestrator is enabled - if so, use it exclusively
        if self.config.orchestrator_llm.enabled:
            logger.info("[DEBUG] LLM CONFIGURATION: Using Orchestrator (replaces all other LLMs)")
            try:
                from services.orchestrator_llm import OrchestratorLLM
                
                # Use room name or booking token as session_id
                session_id = booking_token or room.name
                
                orchestrator_llm = OrchestratorLLM(
                    base_url=self.config.orchestrator_llm.base_url,
                    session_id=session_id,
                    candidate_name=candidate_name,
                    candidate_role=candidate_role,
                )
                logger.info(f"   [OK] Orchestrator LLM initialized: session_id={session_id}")
                logger.info(f"   [OK] Candidate context: name={candidate_name or 'not set'}, role={candidate_role or 'not set'}")
                
                # Orchestrator handles history internally, so we don't need history wrapper
                # But we still wrap for transcript forwarding and timing
                if hasattr(orchestrator_llm, 'chat'):
                    from app.services.transcript_service import TranscriptForwardingService  # type: ignore
                    from services.timing_llm_wrapper import TimingLLMWrapper
                    from services.quiet_transcript_wrapper import QuietTranscriptWrapper
                    from services.transcript_storage_wrapper import TranscriptStorageWrapper
                    
                    # Create transcript service and wrap it to reduce spam
                    original_transcript_service = TranscriptForwardingService(room)
                    quiet_transcript_service = QuietTranscriptWrapper(original_transcript_service)
                    
                    # Wrap with storage to save transcripts to database
                    transcript_service = TranscriptStorageWrapper(
                        original_transcript_service=quiet_transcript_service,
                        room_name=room.name,
                    )
                    
                    original_chat = orchestrator_llm.chat
                    
                    # Wrap with timing (orchestrator handles history, so no history wrapper needed)
                    timing_wrapper = TimingLLMWrapper(original_chat)
                    
                    orchestrator_llm.chat = timing_wrapper
                    logger.info("   [OK] Orchestrator LLM wrapped for transcript forwarding and timing")
                
                return orchestrator_llm
            except Exception as e:
                logger.error(f"   [ERR] Failed to initialize Orchestrator LLM: {e}", exc_info=True)
                raise
        
        # Fallback to traditional LLM chain if orchestrator is disabled
        logger.info("[DEBUG] LLM CONFIGURATION: Self-hosted -> Gemini -> Grok")
        
        primary_llm = None
        fallback_llm = None
        
        # Initialize self-hosted LLM if enabled
        if self.config.openai.llm_enabled:
            logger.info(f"   Self-hosted LLM: ENABLED")
            logger.info(f"   Base URL: {self.config.openai.llm_base_url}")
            logger.info(f"   Model: {self.config.openai.llm_model}")
            try:
                primary_llm = openai.LLM(
                    base_url=f"{self.config.openai.llm_base_url}/llm/v1",
                    model=self.config.openai.llm_model,
                    api_key=self.config.openai.api_key,
                )
                logger.info("   [OK] Self-hosted LLM initialized")
            except Exception as e:
                logger.error(f"   [ERR] Failed to initialize self-hosted LLM: {e}", exc_info=True)
                if not (self.config.gemini_llm.enabled or self.config.grok_llm.enabled):
                    raise  # No fallback available, must fail
        else:
            logger.warning("   [WARN]  Self-hosted LLM: DISABLED (via SELF_HOSTED_LLM_ENABLED=false)")
        
        # Cloud fallback order: Gemini (first fallback), then Grok (fallback of Gemini)
        # 1. Initialize Gemini if enabled (first fallback after self-hosted)
        gemini_llm = None
        if self.config.gemini_llm.enabled and GOOGLE_AVAILABLE:
            if self.config.gemini_llm.api_key:
                try:
                    gemini_llm = google.LLM(
                        model=self.config.gemini_llm.model,
                        api_key=self.config.gemini_llm.api_key,
                    )
                    logger.info(f"   [OK] Cloud fallback LLM (Gemini {self.config.gemini_llm.model}) initialized")
                except Exception as e:
                    logger.warning(f"   [WARN]  Failed to initialize Gemini LLM: {e}")
            else:
                logger.warning("   [WARN]  Gemini LLM enabled but API key not provided")
        elif self.config.gemini_llm.enabled and not GOOGLE_AVAILABLE:
            logger.warning("   [WARN]  Gemini LLM enabled but plugin not installed")
            logger.warning("   Install with: pip install livekit-plugins-google")
        
        # 2. Initialize Grok if enabled (fallback of Gemini, or sole cloud fallback)
        grok_llm = None
        if self.config.grok_llm.enabled and GROK_AVAILABLE:
            if self.config.grok_llm.api_key:
                try:
                    grok_llm = GrokLLM(
                        model=self.config.grok_llm.model,
                        api_key=self.config.grok_llm.api_key,
                    )
                    logger.info(f"   [OK] Cloud fallback LLM (Grok {self.config.grok_llm.model}) initialized")
                except Exception as e:
                    logger.warning(f"   [WARN]  Failed to initialize Grok LLM: {e}")
            else:
                logger.warning("   [WARN]  Grok LLM enabled but API key not provided")
        elif self.config.grok_llm.enabled and not GROK_AVAILABLE:
            logger.warning("   [WARN]  Grok LLM enabled but xai_sdk not installed")
            logger.warning("   Install with: pip install xai-sdk")
        
        # 3. Build fallback chain: Gemini (first) -> Grok (second). If both available, wrap as FallbackLLM(Gemini, Grok).
        if gemini_llm and grok_llm:
            from services.fallback_llm import FallbackLLM
            fallback_llm = FallbackLLM(
                primary_llm=gemini_llm,
                fallback_llm=grok_llm,
                max_primary_failures=3
            )
            logger.info("   [OK] Cloud fallback chain: Gemini (first) -> Grok (second)")
        elif gemini_llm:
            fallback_llm = gemini_llm
        elif grok_llm:
            fallback_llm = grok_llm
        else:
            fallback_llm = None
        
        # Determine final LLM configuration
        if primary_llm and fallback_llm:
            # Both enabled: use fallback wrapper
            from services.fallback_llm import FallbackLLM
            llm_plugin = FallbackLLM(
                primary_llm=primary_llm,
                fallback_llm=fallback_llm,
                max_primary_failures=3
            )
            logger.info("   [OK] LLM with cloud fallback enabled (activates after 3 failures)")
        elif primary_llm:
            # Only self-hosted
            llm_plugin = primary_llm
            logger.warning("   [WARN]  Cloud fallback disabled - session will close on LLM failures")
        elif fallback_llm:
            # Only cloud (self-hosted disabled)
            llm_plugin = fallback_llm
            logger.info("   [OK] Using cloud LLM only (self-hosted disabled)")
        else:
            raise ConfigurationError("No LLM service configured! Enable at least one LLM service.")
        
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
            
            # Wrap with storage to save transcripts to database
            transcript_service = TranscriptStorageWrapper(
                original_transcript_service=quiet_transcript_service,
                room_name=room.name,
            )
            
            original_chat = llm_plugin.chat
            
            # Wrap with history management
            history_wrapper = HistoryManagedLLMWrapper(
                original_chat=original_chat,
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
                f"   [OK] LLM chat wrapped for transcript forwarding (quiet mode), history management, and performance timing "
                f"(max_tokens={self.config.MAX_CONVERSATION_TOKENS}, "
                f"max_messages={self.config.MAX_CONVERSATION_MESSAGES})"
            )
        
        return llm_plugin
    
    def _initialize_tts(self):
        """
        Initialize TTS plugin with optional cloud fallback.
        Supports enable/disable flags for both self-hosted and cloud services.
        
        Returns:
            Configured TTS plugin (with fallback if enabled)
        """
        logger.info("[DEBUG] TTS CONFIGURATION:")
        
        primary_tts = None
        fallback_tts = None
        
        # Initialize self-hosted TTS if enabled
        if self.config.openai.tts_enabled:
            logger.info(f"   Self-hosted TTS: ENABLED")
            logger.info(f"   Base URL: {self.config.openai.tts_base_url}")
            logger.info(f"   Model: {self.config.openai.tts_model}")
            logger.info(f"   Voice: {self.config.openai.tts_voice}")
            try:
                primary_tts = openai.TTS(
                    base_url=f"{self.config.openai.tts_base_url}/tts/v1",
                    model=self.config.openai.tts_model,
                    voice=self.config.openai.tts_voice,
                    api_key=self.config.openai.api_key,
                )
                logger.info("   [OK] Self-hosted TTS initialized")
            except Exception as e:
                logger.error(f"   [ERR] Failed to initialize self-hosted TTS: {e}", exc_info=True)
                if not self.config.elevenlabs_tts.enabled:
                    raise  # No fallback available, must fail
        else:
            logger.warning("   [WARN]  Self-hosted TTS: DISABLED (via SELF_HOSTED_TTS_ENABLED=false)")
        
        # Initialize cloud fallback TTS (ElevenLabs)
        if self.config.elevenlabs_tts.enabled and ELEVENLABS_AVAILABLE:
            if self.config.elevenlabs_tts.api_key:
                try:
                    fallback_tts = elevenlabs.TTS(
                        api_key=self.config.elevenlabs_tts.api_key,
                        voice_id=self.config.elevenlabs_tts.voice_id,
                    )
                    logger.info(f"   [OK] Cloud fallback TTS (ElevenLabs voice {self.config.elevenlabs_tts.voice_id}) initialized")
                except Exception as e:
                    logger.warning(f"   [WARN]  Failed to initialize ElevenLabs TTS: {e}")
        elif self.config.elevenlabs_tts.enabled and not ELEVENLABS_AVAILABLE:
            logger.warning("   [WARN]  ElevenLabs TTS enabled but plugin not installed")
            logger.warning("   Install with: pip install livekit-plugins-elevenlabs")
        
        # Determine final TTS configuration
        if primary_tts and fallback_tts:
            # Both enabled: use fallback wrapper
            from services.fallback_tts import FallbackTTS
            tts_plugin = FallbackTTS(
                primary_tts=primary_tts,
                fallback_tts=fallback_tts,
                max_primary_failures=3
            )
            logger.info("   [OK] TTS with cloud fallback enabled (activates after 3 failures)")
        elif primary_tts:
            # Only self-hosted
            tts_plugin = primary_tts
            logger.warning("   [WARN]  Cloud fallback disabled - session will close on TTS failures")
        elif fallback_tts:
            # Only cloud (self-hosted disabled)
            tts_plugin = fallback_tts
            logger.info("   [OK] Using cloud TTS only (self-hosted disabled)")
        else:
            raise ConfigurationError("No TTS service configured! Enable at least one TTS service.")
        
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

