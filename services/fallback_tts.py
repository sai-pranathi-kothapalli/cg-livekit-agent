"""
Fallback TTS Wrapper

Provides fallback TTS service that automatically switches to ElevenLabs
when the primary TTS service fails.
"""

import sys
from pathlib import Path
from typing import Optional, Any
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
        
        fallback_name = type(fallback_tts).__name__ if fallback_tts else 'disabled'
        logger.info(
            f"✅ FallbackTTS initialized: "
            f"primary={type(primary_tts).__name__}, "
            f"fallback={fallback_name}"
        )
    
    def __getattr__(self, name: str):
        """Proxy all attributes to active TTS."""
        active_tts = self._fallback_tts if self._using_fallback else self._primary_tts
        return getattr(active_tts, name)
    
    def synthesize(self, text: str, *, conn_options=None):
        """
        Synthesize text to speech with fallback support.
        
        Args:
            text: Text to synthesize
            conn_options: Connection options
            
        Returns:
            ChunkedStream with fallback support
        """
        if conn_options is None:
            from livekit.agents import api
            conn_options = api.APIConnectOptions()
        
        # Return a FallbackChunkedStream wrapper that handles the actual fallback logic
        return FallbackChunkedStream(
            primary_tts=self._primary_tts,
            fallback_tts=self._fallback_tts,
            fallback_tts_wrapper=self,
            text=text,
            conn_options=conn_options
        )
    
    def stream(self, *, conn_options=None):
        """
        Create streaming TTS with fallback support.
        
        Args:
            conn_options: Connection options
            
        Returns:
            SynthesizeStream with fallback support
        """
        if conn_options is None:
            from livekit.agents import api
            conn_options = api.APIConnectOptions()
        
        # Return a FallbackSynthesizeStream wrapper that handles the actual fallback logic
        return FallbackSynthesizeStream(
            primary_tts=self._primary_tts,
            fallback_tts=self._fallback_tts,
            fallback_tts_wrapper=self,
            conn_options=conn_options
        )


class FallbackChunkedStream:
    """Wrapper for TTS ChunkedStream with fallback."""
    
    def __init__(self, primary_tts, fallback_tts, fallback_tts_wrapper, text, conn_options):
        self._primary_tts = primary_tts
        self._fallback_tts = fallback_tts
        self._wrapper = fallback_tts_wrapper
        self._text = text
        self._conn_options = conn_options
        self._active_stream = None
        self._using_fallback = fallback_tts_wrapper._using_fallback
    
    async def __aenter__(self):
        # Start with the appropriate TTS based on wrapper state
        if self._using_fallback and self._fallback_tts:
            logger.info("🔊 [TTS] Using FALLBACK TTS (ElevenLabs) for this synthesis")
            self._active_stream = self._fallback_tts.synthesize(self._text, conn_options=self._conn_options)
        else:
            logger.info("🔊 [TTS] Using PRIMARY TTS (self-hosted) for this synthesis")
            self._active_stream = self._primary_tts.synthesize(self._text, conn_options=self._conn_options)
        
        return await self._active_stream.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._active_stream:
            return await self._active_stream.__aexit__(exc_type, exc_val, exc_tb)
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        try:
            if self._active_stream is None:
                raise RuntimeError("Stream context not entered")
            
            return await self._active_stream.__anext__()
            
        except StopAsyncIteration:
            # Normal end of stream
            raise
            
        except Exception as e:
            error_msg = str(e)
            is_recoverable = (
                "500" in error_msg or
                "Internal Server Error" in error_msg or
                "timeout" in error_msg.lower() or
                "connection" in error_msg.lower() or
                "503" in error_msg or
                "502" in error_msg or
                "504" in error_msg
            )
            
            # Only try fallback if we have one and haven't switched yet
            if is_recoverable and self._fallback_tts and not self._using_fallback:
                self._wrapper._primary_failures += 1
                logger.warning(
                    f"⚠️  Primary TTS failed ({self._wrapper._primary_failures}/{self._wrapper._max_primary_failures}): "
                    f"{type(e).__name__}: {error_msg}"
                )
                
                if self._wrapper._primary_failures >= self._wrapper._max_primary_failures:
                    fallback_name = type(self._fallback_tts).__name__ if self._fallback_tts else "fallback"
                    logger.warning(f"🔄 Switching to {fallback_name} fallback TTS after {self._wrapper._max_primary_failures} failures")
                    self._wrapper._using_fallback = True
                    self._using_fallback = True
                    
                    # Close current stream and start new one with fallback
                    try:
                        await self._active_stream.__aexit__(None, None, None)
                    except Exception as cleanup_err:
                        logger.debug(f"Ignoring stream cleanup error during fallback switch: {cleanup_err}")
                    
                    # Start fallback stream
                    self._active_stream = self._fallback_tts.synthesize(self._text, conn_options=self._conn_options)
                    await self._active_stream.__aenter__()
                    
                    # Try to get first chunk from fallback
                    try:
                        return await self._active_stream.__anext__()
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback TTS also failed: {fallback_error}", exc_info=True)
                        raise
            
            # Re-raise if not recoverable or no fallback available
            raise


class FallbackSynthesizeStream:
    """Wrapper for TTS SynthesizeStream with fallback."""
    
    def __init__(self, primary_tts, fallback_tts, fallback_tts_wrapper, conn_options):
        self._primary_tts = primary_tts
        self._fallback_tts = fallback_tts
        self._wrapper = fallback_tts_wrapper
        self._conn_options = conn_options
        self._active_stream = None
        self._using_fallback = fallback_tts_wrapper._using_fallback
        self._initialized = False
    
    async def __aenter__(self):
        # Start with the appropriate TTS based on wrapper state
        if self._using_fallback and self._fallback_tts:
            logger.info("🔊 [TTS] Using FALLBACK TTS (ElevenLabs) for streaming")
            self._active_stream = self._fallback_tts.stream(conn_options=self._conn_options)
        else:
            logger.info("🔊 [TTS] Using PRIMARY TTS (self-hosted) for streaming")
            self._active_stream = self._primary_tts.stream(conn_options=self._conn_options)
        
        result = await self._active_stream.__aenter__()
        self._initialized = True
        return result
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._active_stream:
            return await self._active_stream.__aexit__(exc_type, exc_val, exc_tb)
    
    def __aiter__(self):
        if not self._initialized:
            raise RuntimeError("Stream context not entered. Use 'async with' statement.")
        return self
    
    async def __anext__(self):
        try:
            if self._active_stream is None or not self._initialized:
                raise RuntimeError("Stream context not entered")
            
            return await self._active_stream.__anext__()
            
        except StopAsyncIteration:
            # Normal end of stream
            raise
            
        except Exception as e:
            error_msg = str(e)
            is_recoverable = (
                "500" in error_msg or
                "Internal Server Error" in error_msg or
                "timeout" in error_msg.lower() or
                "connection" in error_msg.lower() or
                "503" in error_msg or
                "502" in error_msg or
                "504" in error_msg
            )
            
            # Only try fallback if we have one and haven't switched yet
            if is_recoverable and self._fallback_tts and not self._using_fallback:
                self._wrapper._primary_failures += 1
                logger.warning(
                    f"⚠️  Primary TTS failed ({self._wrapper._primary_failures}/{self._wrapper._max_primary_failures}): "
                    f"{type(e).__name__}: {error_msg}"
                )
                
                if self._wrapper._primary_failures >= self._wrapper._max_primary_failures:
                    fallback_name = type(self._fallback_tts).__name__ if self._fallback_tts else "fallback"
                    logger.warning(f"🔄 Switching to {fallback_name} fallback TTS after {self._wrapper._max_primary_failures} failures")
                    self._wrapper._using_fallback = True
                    self._using_fallback = True
                    
                    # Close current stream and start new one with fallback
                    try:
                        await self._active_stream.__aexit__(None, None, None)
                    except Exception as cleanup_err:
                        logger.debug(f"Ignoring stream cleanup error during fallback switch: {cleanup_err}")
                    
                    # Start fallback stream
                    self._active_stream = self._fallback_tts.stream(conn_options=self._conn_options)
                    await self._active_stream.__aenter__()
                    
                    # Try to get first event from fallback
                    try:
                        return await self._active_stream.__anext__()
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback TTS also failed: {fallback_error}", exc_info=True)
                        raise
            
            # Re-raise if not recoverable or no fallback available
            raise
    
    def push_text(self, text: str):
        """Push text to the active stream."""
        if self._active_stream is None or not self._initialized:
            raise RuntimeError("Stream context not entered")
        return self._active_stream.push_text(text)
    
    def flush(self):
        """Flush the active stream."""
        if self._active_stream is None or not self._initialized:
            raise RuntimeError("Stream context not entered")
        return self._active_stream.flush()
    
    async def aclose(self):
        """Close the active stream."""
        if self._active_stream:
            await self._active_stream.aclose()
