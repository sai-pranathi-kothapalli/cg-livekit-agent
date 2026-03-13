"""
Timing LLM Wrapper

Wraps LLM chat to add performance timing logs and to sanitize agent output
(strip internal context like MINUTE. / Phase: so it is never spoken or shown).
"""

import time
from typing import Any, Callable, AsyncContextManager
from agents.utils import PerformanceTimer, logger, log_turn_start, log_turn_end, log_tts_start
from services.output_sanitizer import OutputSanitizerState, _make_chunk_with_content


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
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        logger.info("TimingLLMWrapper initialized")
    
    def __call__(self, *args, **kwargs) -> "TimingContextWrapper":
        """
        Call wrapper - intercepts LLM chat calls and adds timing.
        """
        return TimingContextWrapper(
            self._original_chat(*args, **kwargs),
            self
        )

    def aggregate_usage(self, input_tokens: int, output_tokens: int):
        """Aggregate usage from a single LLM call"""
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        logger.debug(f"📊 [AGGREGATE TOKENS] session_total: input={self._total_input_tokens} output={self._total_output_tokens}")

    def get_total_usage(self):
        """Get total usage for the session"""
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens
        }


class TimingContextWrapper:
    """Context manager wrapper that adds timing to LLM operations"""
    
    # Class variable to track turn start time
    _turn_start_time = None
    
    def __init__(self, original_cm: AsyncContextManager, parent: TimingLLMWrapper = None):
        self._cm = original_cm
        self._parent = parent
        self._timer = None
        self._conversation_id = None
        self._first_chunk = False
        self._chunk_count = 0
        self._total_chars = 0
        self._tts_timer = None
        self._token_logged = False  # avoid double log when both __anext__(StopAsyncIteration) and __aexit__ run
        self._sanitizer_state = None  # set in __aenter__
    
    async def __aenter__(self):
        """Enter the original context manager and start timing"""
        self._conversation_id = id(self)
        self._first_chunk = False
        self._chunk_count = 0
        self._total_chars = 0
        self._sanitizer_state = OutputSanitizerState()
        
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
        """Exit and log total time and token usage"""
        try:
            # ✅ Token usage (only if not already logged in __anext__ when stream ended)
            if not self._token_logged:
                self._log_token_usage()
                self._token_logged = True
            
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
    
    def _log_token_usage(self):
        """Log token usage (called when stream ends so we never miss it)."""
        output_tokens_estimate = self._total_chars // 3
        try:
            from app.services.history_managed_llm_wrapper import get_last_llm_input_tokens_estimate
            input_estimate = get_last_llm_input_tokens_estimate()
            total_estimate = input_estimate + output_tokens_estimate
            msg = (
                f"📊 [TOKENS] input_estimate={input_estimate} output_estimate={output_tokens_estimate} "
                f"output_chars={self._total_chars} total_estimate={total_estimate}"
            )
        except Exception:
            msg = f"📊 [TOKENS] output_estimate={output_tokens_estimate} output_chars={self._total_chars}"
        
        logger.info(msg)
        
        # Aggregate usage back to the parent TimingLLMWrapper
        if self._parent:
            try:
                # We use estimates for now as Gemini stream chunks don't always contain usageMetadata
                # If we had real usageMetadata from chunk.usage_metadata, we'd use it here.
                input_count = input_estimate if 'input_estimate' in locals() else 0
                output_count = output_tokens_estimate
                self._parent.aggregate_usage(input_count, output_count)
            except Exception as e:
                logger.warning(f"Failed to aggregate token usage: {e}")

        try:
            print(msg, flush=True)
        except Exception:
            pass

    async def __anext__(self):
        """Iterate and track timing; sanitize output to strip internal context.

        Uses an outer while-True loop so that when the sanitizer is buffering an
        [INTERNAL] block, empty intermediate chunks are never forwarded to TTS.
        Returning an empty chunk to TTS can cause it to treat the silence as
        end-of-utterance and prematurely cut off the interviewer's question.
        """
        # Outer loop: keeps fetching until we have real content (or stream ends).
        while True:
            try:
                chunk = await self._cm.__anext__()

                if not self._first_chunk and self._timer:
                    self._first_chunk = True
                    self._timer.checkpoint("First chunk (TTFB)")
                    logger.info("🔵 [LLM] Gemini first chunk received (TTFB) - stream started")
                    try:
                        import sys
                        print("🔵 [LLM] Gemini first chunk received (TTFB) - stream started", flush=True)
                    except Exception:
                        pass

                self._chunk_count += 1

                chunk_text = ""
                delta = getattr(chunk, "delta", None)
                if delta is not None and getattr(delta, "content", None):
                    c = delta.content
                    chunk_text = c if isinstance(c, str) else ""
                elif hasattr(chunk, "content") and isinstance(getattr(chunk, "content"), str):
                    chunk_text = chunk.content or ""
                elif hasattr(chunk, "text"):
                    chunk_text = chunk.text if isinstance(chunk.text, str) else ""
                elif isinstance(chunk, str):
                    chunk_text = chunk
                elif getattr(chunk, "choices", None):
                    choices = chunk.choices
                    if choices and len(choices) > 0:
                        d = getattr(choices[0], "delta", None)
                        if d and hasattr(d, "content") and d.content:
                            chunk_text = d.content if isinstance(d.content, str) else ""
                elif getattr(chunk, "parts", None):
                    for part in chunk.parts:
                        if hasattr(part, "text") and part.text:
                            chunk_text += part.text if isinstance(part.text, str) else ""
                elif getattr(chunk, "candidates", None):
                    cands = chunk.candidates
                    if cands and len(cands) > 0:
                        content = getattr(cands[0], "content", None)
                        if content and getattr(content, "parts", None):
                            for part in content.parts:
                                if hasattr(part, "text") and part.text:
                                    chunk_text += part.text if isinstance(part.text, str) else ""

                # If we are in passthrough mode, just pass the chunk through (already found and stripped the marker)
                if self._sanitizer_state.should_passthrough():
                    if chunk_text:
                        self._total_chars += len(chunk_text)
                    return chunk

                # Always add to buffer and check for the [END INTERNAL CONTEXT] marker.
                # The sanitizer handles skipping content until the marker is found.
                self._sanitizer_state.add(chunk_text)
                after = self._sanitizer_state.take_after_marker()
                
                if self._sanitizer_state.should_passthrough():
                    # Marker was found in this chunk or buffer reached max size.
                    # 'after' contains the sanitized content to emit.
                    if after:
                        self._total_chars += len(after)
                        return _make_chunk_with_content(after, chunk)
                    # If marker was found but 'after' is empty, continue to next chunk
                    continue

                # We haven't found the marker yet. 
                # Check if we should even be buffering (does it start with [INTERNAL, [THOUGHT, or [RESPONSE?)
                strip_markers = ("[INTERNAL", "[THOUGHT", "[RESPONSE")
                if not any(self._sanitizer_state.buffer.strip().startswith(m) for m in strip_markers):
                    # This doesn't look like it starts with an internal block.
                    # We'll allow passthrough for this chunk but keep checking subsequent ones
                    # just in case an [INTERNAL] block appears later (though unlikely in current architecture).
                    # Actually, for safety, let's just emit the chunk but NOT set passthrough=True.
                    if chunk_text:
                        self._total_chars += len(chunk_text)
                        
                    # We clear the buffer so we don't re-emit the same text next time
                    self._sanitizer_state.buffer = ""
                    return chunk
                
                # We are definitely buffering an [INTERNAL] block. Continue to next chunk.
                continue

            except StopAsyncIteration:
                # Flush any remaining buffered content (sanitizer may still hold chunks)
                if self._sanitizer_state and not self._sanitizer_state.should_passthrough():
                    remaining = self._sanitizer_state.flush_remaining()
                    if remaining:
                        # Stream ended while still buffering — discard to prevent leakage.
                        # (take_after_marker already handles the discard; flush_remaining
                        #  is the last safety net and its output is intentionally dropped here.)
                        logger.warning(
                            f"⚠️  Stream ended with {len(remaining)} chars still buffered "
                            f"(no [END INTERNAL CONTEXT] marker) — discarding to prevent leakage."
                        )
                        self._total_chars += len(remaining)

                # Log tokens when stream ends (LiveKit may not call __aexit__, so we log here too)
                self._log_token_usage()
                self._token_logged = True
                if self._timer:
                    self._timer.end(f"{self._total_chars} chars generated")
                    logger.info(f"    📊 Streamed {self._chunk_count} chunks")
                raise
            except Exception as e:
                logger.error(f"⚠️  Error in timing wrapper __anext__: {e}", exc_info=True)
                raise
