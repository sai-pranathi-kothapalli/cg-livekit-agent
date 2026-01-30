"""
Timing LLM Wrapper

Wraps LLM chat to add performance timing logs without modifying backend code.
"""

import time
from typing import Any, Callable, AsyncContextManager
from agents.utils import PerformanceTimer, logger, log_turn_start, log_turn_end, log_tts_start


class TimingLLMWrapper:
    """
    Wraps LLM chat to add performance timing.
    
    This wrapper sits on top of the HistoryManagedLLMWrapper to add timing
    without modifying backend code.
    """
    
    def __init__(self, original_chat: Callable[..., AsyncContextManager]):
        """
        Initialize timing wrapper.
        
        Args:
            original_chat: Original LLM chat method (already wrapped by history manager)
        """
        self._original_chat = original_chat
        logger.info("TimingLLMWrapper initialized")
    
    def __call__(self, *args, **kwargs) -> "TimingContextWrapper":
        """
        Call wrapper - intercepts LLM chat calls and adds timing.
        """
        return TimingContextWrapper(
            self._original_chat(*args, **kwargs)
        )


class TimingContextWrapper:
    """Context manager wrapper that adds timing to LLM operations"""
    
    # Class variable to track turn start time
    _turn_start_time = None
    
    def __init__(self, original_cm: AsyncContextManager):
        self._cm = original_cm
        self._timer = None
        self._conversation_id = None
        self._first_chunk = False
        self._chunk_count = 0
        self._total_chars = 0
        self._tts_timer = None
    
    async def __aenter__(self):
        """Enter the original context manager and start timing"""
        self._conversation_id = id(self)
        self._first_chunk = False
        self._chunk_count = 0
        self._total_chars = 0
        
        # ✅ EXPLICIT: We are about to call the LLM (Gemini or fallback)
        logger.info("🔵 [LLM] Entering chat context - calling Gemini (or fallback)...")
        try:
            import sys
            print("🔵 [LLM] Entering chat context - calling Gemini (or fallback)...", flush=True)
        except Exception:
            pass
        
        # ✅ LOG TURN START (if this is the first LLM call for this turn)
        if TimingContextWrapper._turn_start_time is None:
            log_turn_start()
            TimingContextWrapper._turn_start_time = time.perf_counter()
        
        # ✅ START LLM TIMING
        self._timer = PerformanceTimer("LLM").start()
        
        result = await self._cm.__aenter__()
        
        # ✅ CHECKPOINT: Connected (LLM accepted the request)
        if self._timer:
            self._timer.checkpoint("Connected to LLM")
        logger.info("🔵 [LLM] Chat context entered - Gemini (or fallback) connected, waiting for first chunk...")
        try:
            print("🔵 [LLM] Chat context entered - Gemini connected, waiting for first chunk...", flush=True)
        except Exception:
            pass
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit and log total time"""
        try:
            # ✅ END LLM TIMING
            if self._timer:
                self._timer.end(f"{self._total_chars} chars generated")
                logger.info(f"    📊 Streamed {self._chunk_count} chunks")
            
            # ✅ LOG TTS START (text will be converted to audio next)
            if self._total_chars > 0:
                log_tts_start(self._total_chars)
                self._tts_timer = PerformanceTimer("TTS").start()
            
            result = await self._cm.__aexit__(exc_type, exc_val, exc_tb)
            
            # ✅ ESTIMATE TTS COMPLETION (actual TTS happens in LiveKit agents framework)
            # We can't directly time it, but we log the start
            if self._tts_timer:
                # Note: TTS actually happens after this, but we mark where it starts
                logger.info(f"⏱️  [TTS] ⚡ Audio generation started (LiveKit agents will process)")
            
            # ✅ LOG TURN END with total time
            if TimingContextWrapper._turn_start_time is not None:
                total_turn_time = time.perf_counter() - TimingContextWrapper._turn_start_time
                log_turn_end(total_turn_time)
                TimingContextWrapper._turn_start_time = None  # Reset for next turn
            
            return result
        except Exception as e:
            logger.error(f"⚠️  Error in timing wrapper __aexit__: {e}", exc_info=True)
            raise
    
    def __aiter__(self):
        """Return self as async iterator"""
        return self
    
    async def __anext__(self):
        """Iterate and track timing"""
        try:
            chunk = await self._cm.__anext__()
            
            # ✅ CHECKPOINT: First chunk (TTFB) - Gemini has responded
            if not self._first_chunk and self._timer:
                self._first_chunk = True
                self._timer.checkpoint("First chunk (TTFB)")
                logger.info("🔵 [LLM] Gemini first chunk received (TTFB) - stream started")
                try:
                    import sys
                    print("🔵 [LLM] Gemini first chunk received (TTFB) - stream started", flush=True)
                except Exception:
                    pass
            
            # Track chunk stats
            self._chunk_count += 1
            
            # Try to extract text length
            if hasattr(chunk, 'content'):
                self._total_chars += len(chunk.content or "")
            elif hasattr(chunk, 'text'):
                self._total_chars += len(chunk.text or "")
            elif isinstance(chunk, str):
                self._total_chars += len(chunk)
            
            return chunk
            
        except StopAsyncIteration:
            raise
        except Exception as e:
            logger.error(f"⚠️  Error in timing wrapper __anext__: {e}", exc_info=True)
            raise
