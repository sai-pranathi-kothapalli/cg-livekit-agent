"""
Fallback TTS Wrapper

Provides fallback TTS service that automatically switches to ElevenLabs
when the primary TTS service fails.
"""

import sys
from pathlib import Path
from typing import Optional, AsyncIterator, Any
from livekit.agents import tts

# Add backend to path for imports
backend_path = Path(__file__).parent.parent.parent / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class FallbackTTS:
    """
    TTS wrapper that falls back to ElevenLabs when primary TTS fails.
    """
    
    def __init__(
        self,
        primary_tts: tts.TTS,
        fallback_tts: Optional[tts.TTS] = None,
        max_primary_failures: int = 3
    ):
        """
        Initialize fallback TTS wrapper.
        
        Args:
            primary_tts: Primary TTS service (self-hosted)
            fallback_tts: Fallback TTS service (ElevenLabs, optional)
            max_primary_failures: Max failures before switching to fallback
        """
        self._primary_tts = primary_tts
        self._fallback_tts = fallback_tts
        self._max_primary_failures = max_primary_failures
        self._primary_failures = 0
        self._using_fallback = False
        
        logger.info(
            f"✅ FallbackTTS initialized: "
            f"primary={type(primary_tts).__name__}, "
            f"fallback={'ElevenLabs' if fallback_tts else 'disabled'}"
        )
    
    def __getattr__(self, name: str):
        """Proxy all attributes to active TTS."""
        active_tts = self._fallback_tts if self._using_fallback else self._primary_tts
        return getattr(active_tts, name)
    
    async def synthesize(
        self,
        text: str,
        *,
        conn_options: Optional[Any] = None
    ) -> "ChunkedStream":
        """
        Synthesize speech with automatic fallback.
        """
        # If already using fallback, use it directly
        if self._using_fallback and self._fallback_tts:
            try:
                if conn_options:
                    return await self._fallback_tts.synthesize(text, conn_options=conn_options)
                else:
                    return await self._fallback_tts.synthesize(text)
            except Exception as e:
                logger.error(f"❌ Fallback TTS failed: {e}", exc_info=True)
                logger.warning("🔄 Attempting primary TTS as last resort")
                self._using_fallback = False
                self._primary_failures = 0
        
        # Try primary TTS first
        try:
            if conn_options:
                result = await self._primary_tts.synthesize(text, conn_options=conn_options)
            else:
                result = await self._primary_tts.synthesize(text)
            
            # Reset failure count on success
            if self._primary_failures > 0:
                logger.info(f"✅ Primary TTS recovered after {self._primary_failures} failures")
                self._primary_failures = 0
                self._using_fallback = False
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            is_recoverable = (
                "500" in error_msg or
                "Internal Server Error" in error_msg or
                "timeout" in error_msg.lower() or
                "connection" in error_msg.lower() or
                "503" in error_msg or
                "502" in error_msg
            )
            
            if is_recoverable and self._fallback_tts:
                self._primary_failures += 1
                logger.warning(
                    f"⚠️  Primary TTS failed ({self._primary_failures}/{self._max_primary_failures}): "
                    f"{type(e).__name__}: {error_msg}"
                )
                
                # Switch to fallback if threshold reached
                if self._primary_failures >= self._max_primary_failures:
                    logger.warning("🔄 Switching to ElevenLabs fallback TTS")
                    self._using_fallback = True
                    
                    # Retry with fallback
                    try:
                        if conn_options:
                            result = await self._fallback_tts.synthesize(text, conn_options=conn_options)
                        else:
                            result = await self._fallback_tts.synthesize(text)
                        logger.info("✅ Fallback TTS succeeded")
                        return result
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback TTS also failed: {fallback_error}", exc_info=True)
                        raise
                else:
                    raise
            else:
                raise
    
    def stream(self) -> "FallbackTTSStream":
        """Create a streaming TTS session with fallback support."""
        primary_stream = self._primary_tts.stream()
        fallback_stream = self._fallback_tts.stream() if self._fallback_tts else None
        
        return FallbackTTSStream(
            primary_stream=primary_stream,
            fallback_stream=fallback_stream,
            max_primary_failures=self._max_primary_failures,
            fallback_tts_wrapper=self
        )


class FallbackTTSStream(tts.SynthesizeStream):
    """Streaming TTS session with fallback support."""
    
    def __init__(
        self,
        primary_stream: tts.SynthesizeStream,
        fallback_stream: Optional[tts.SynthesizeStream] = None,
        max_primary_failures: int = 3,
        fallback_tts_wrapper: Optional["FallbackTTS"] = None
    ):
        super().__init__()
        self._primary_stream = primary_stream
        self._fallback_stream = fallback_stream
        self._max_primary_failures = max_primary_failures
        self._primary_failures = 0
        self._using_fallback = False
        self._fallback_tts_wrapper = fallback_tts_wrapper
    
    async def push_text(self, text: str) -> None:
        """Push text to active stream"""
        # Check parent wrapper state
        if self._fallback_tts_wrapper and self._fallback_tts_wrapper._using_fallback:
            self._using_fallback = True
        
        if not self._using_fallback:
            try:
                await self._primary_stream.push_text(text)
                if self._primary_failures > 0:
                    logger.debug("✅ Primary TTS stream recovered")
                    self._primary_failures = 0
            except Exception as e:
                error_msg = str(e)
                is_recoverable = (
                    "500" in error_msg or
                    "Internal Server Error" in error_msg or
                    "timeout" in error_msg.lower() or
                    "connection" in error_msg.lower()
                )
                
                if is_recoverable:
                    self._primary_failures += 1
                    if self._fallback_tts_wrapper:
                        self._fallback_tts_wrapper._primary_failures = self._primary_failures
                    
                    if self._primary_failures >= self._max_primary_failures and self._fallback_stream:
                        logger.warning("🔄 Switching TTS stream to fallback")
                        self._using_fallback = True
                        if self._fallback_tts_wrapper:
                            self._fallback_tts_wrapper._using_fallback = True
                        await self._fallback_stream.push_text(text)
                    else:
                        raise
                else:
                    raise
        else:
            if self._fallback_stream:
                await self._fallback_stream.push_text(text)
            else:
                raise RuntimeError("Fallback TTS stream not available")
    
    async def aclose(self, *, wait: bool = True) -> None:
        """Close active stream"""
        if self._using_fallback and self._fallback_stream:
            await self._fallback_stream.aclose(wait=wait)
        else:
            await self._primary_stream.aclose(wait=wait)
    
    async def __aiter__(self) -> AsyncIterator[tts.SynthesizedAudio]:
        """Iterate over TTS events from active stream"""
        if self._using_fallback and self._fallback_stream:
            async for event in self._fallback_stream:
                yield event
        else:
            async for event in self._primary_stream:
                yield event
