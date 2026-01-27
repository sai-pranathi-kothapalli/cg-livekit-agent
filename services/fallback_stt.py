"""
Fallback STT Wrapper

Provides fallback STT service that automatically switches to ElevenLabs
when the primary STT service fails. This prevents session closure due to STT errors.
"""

import sys
from pathlib import Path
from typing import Optional, AsyncIterator, Any
from livekit import rtc
from livekit.agents import stt

# Add backend to path for imports
backend_path = Path(__file__).parent.parent.parent / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class FallbackSTT:
    """
    STT wrapper that falls back to ElevenLabs when primary STT fails.
    
    This wrapper intercepts STT calls and provides automatic fallback
    to prevent session closure on STT failures.
    """
    
    def __init__(
        self,
        primary_stt: stt.STT,
        fallback_stt: Optional[stt.STT] = None,
        max_primary_failures: int = 3
    ):
        """
        Initialize fallback STT wrapper.
        
        Args:
            primary_stt: Primary STT service (self-hosted)
            fallback_stt: Fallback STT service (ElevenLabs, optional)
            max_primary_failures: Max failures before switching to fallback
        """
        self._primary_stt = primary_stt
        self._fallback_stt = fallback_stt
        self._max_primary_failures = max_primary_failures
        self._primary_failures = 0
        self._using_fallback = False
        
        logger.info(
            f"✅ FallbackSTT initialized: "
            f"primary={type(primary_stt).__name__}, "
            f"fallback={'ElevenLabs' if fallback_stt else 'disabled'}"
        )
    
    def __getattr__(self, name: str):
        """
        Proxy all attributes to active STT.
        This allows the wrapper to be used as a drop-in replacement.
        """
        # Use fallback if switched, otherwise primary
        active_stt = self._fallback_stt if self._using_fallback else self._primary_stt
        return getattr(active_stt, name)
    
    async def recognize(
        self,
        *,
        buffer: rtc.AudioFrame,
        user_id: Optional[str] = None,
        language: Optional[str] = None,
        conn_options: Optional[Any] = None,
    ) -> Optional[stt.SpeechEvent]:
        """
        Recognize speech with automatic fallback.
        
        Tries primary STT first, falls back to ElevenLabs on failure.
        This prevents session closure when primary STT fails.
        """
        # If already using fallback, use it directly
        if self._using_fallback and self._fallback_stt:
            try:
                return await self._fallback_stt.recognize(
                    buffer=buffer,
                    user_id=user_id,
                    language=language,
                    conn_options=conn_options
                )
            except Exception as e:
                logger.error(
                    f"❌ Fallback STT failed: {type(e).__name__}: {e}",
                    exc_info=True
                )
                # Try primary again as last resort
                logger.warning("🔄 Attempting primary STT as last resort")
                self._using_fallback = False
                self._primary_failures = 0
        
        # Try primary STT first
        try:
            result = await self._primary_stt.recognize(
                buffer=buffer,
                user_id=user_id,
                language=language,
                conn_options=conn_options
            )
            
            # Reset failure count on success
            if self._primary_failures > 0:
                logger.info(f"✅ Primary STT recovered after {self._primary_failures} failures")
                self._primary_failures = 0
                self._using_fallback = False
            
            return result
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            
            # Check if it's a recoverable STT error
            is_recoverable_stt_error = (
                "500" in error_msg or
                "Internal Server Error" in error_msg or
                "APIStatusError" in error_type or
                "timeout" in error_msg.lower() or
                "connection" in error_msg.lower() or
                "503" in error_msg or
                "502" in error_msg
            )
            
            if is_recoverable_stt_error and self._fallback_stt:
                self._primary_failures += 1
                logger.warning(
                    f"⚠️  Primary STT failed ({self._primary_failures}/{self._max_primary_failures}): "
                    f"{error_type}: {error_msg}"
                )
                
                # Switch to fallback if threshold reached
                if self._primary_failures >= self._max_primary_failures:
                    logger.warning(
                        f"🔄 Switching to ElevenLabs fallback STT after {self._primary_failures} failures"
                    )
                    self._using_fallback = True
                    
                    # Retry with fallback
                    try:
                        result = await self._fallback_stt.recognize(
                            buffer=buffer,
                            user_id=user_id,
                            language=language,
                            conn_options=conn_options
                        )
                        logger.info("✅ Fallback STT succeeded")
                        return result
                    except Exception as fallback_error:
                        logger.error(
                            f"❌ Fallback STT also failed: {type(fallback_error).__name__}: {fallback_error}",
                            exc_info=True
                        )
                        # Re-raise to let LiveKit handle it
                        raise
                else:
                    # Not enough failures yet - re-raise to let LiveKit retry
                    # LiveKit will retry 3 times, then we'll switch to fallback
                    raise
            else:
                # Non-recoverable error or no fallback - re-raise
                raise
    
    def stream(
        self,
        *,
        user_id: Optional[str] = None,
        language: Optional[str] = None,
    ) -> "FallbackSTTStream":
        """
        Create a streaming STT session with fallback support.
        """
        primary_stream = self._primary_stt.stream(user_id=user_id, language=language)
        fallback_stream = self._fallback_stt.stream(user_id=user_id, language=language) if self._fallback_stt else None
        
        return FallbackSTTStream(
            primary_stream=primary_stream,
            fallback_stream=fallback_stream,
            max_primary_failures=self._max_primary_failures,
            fallback_stt_wrapper=self  # Reference to parent for state management
        )


class FallbackSTTStream(stt.SpeechStream):
    """
    Streaming STT session with fallback support.
    """
    
    def __init__(
        self,
        primary_stream: stt.SpeechStream,
        fallback_stream: Optional[stt.SpeechStream] = None,
        max_primary_failures: int = 3,
        fallback_stt_wrapper: Optional["FallbackSTT"] = None
    ):
        super().__init__()
        self._primary_stream = primary_stream
        self._fallback_stream = fallback_stream
        self._max_primary_failures = max_primary_failures
        self._primary_failures = 0
        self._using_fallback = False
        self._fallback_stt_wrapper = fallback_stt_wrapper
    
    async def push_frame(self, frame: rtc.AudioFrame) -> None:
        """Push audio frame to active stream"""
        # Check parent wrapper state
        if self._fallback_stt_wrapper and self._fallback_stt_wrapper._using_fallback:
            self._using_fallback = True
        
        if not self._using_fallback:
            try:
                await self._primary_stream.push_frame(frame)
                if self._primary_failures > 0:
                    logger.debug("✅ Primary STT stream recovered")
                    self._primary_failures = 0
            except Exception as e:
                error_msg = str(e)
                is_recoverable = (
                    "500" in error_msg or
                    "Internal Server Error" in error_msg or
                    "APIStatusError" in error_msg or
                    "timeout" in error_msg.lower()
                )
                
                if is_recoverable:
                    self._primary_failures += 1
                    if self._fallback_stt_wrapper:
                        self._fallback_stt_wrapper._primary_failures = self._primary_failures
                    
                    if self._primary_failures >= self._max_primary_failures and self._fallback_stream:
                        logger.warning("🔄 Switching STT stream to fallback")
                        self._using_fallback = True
                        if self._fallback_stt_wrapper:
                            self._fallback_stt_wrapper._using_fallback = True
                    else:
                        raise
                else:
                    raise
        else:
            if self._fallback_stream:
                await self._fallback_stream.push_frame(frame)
            else:
                raise RuntimeError("Fallback STT stream not available")
    
    async def aclose(self, *, wait: bool = True) -> None:
        """Close active stream"""
        if self._using_fallback and self._fallback_stream:
            await self._fallback_stream.aclose(wait=wait)
        else:
            await self._primary_stream.aclose(wait=wait)
    
    async def __aiter__(self) -> AsyncIterator[stt.SpeechEvent]:
        """Iterate over speech events from active stream"""
        if self._using_fallback and self._fallback_stream:
            async for event in self._fallback_stream:
                yield event
        else:
            async for event in self._primary_stream:
                yield event
