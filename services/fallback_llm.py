"""
Fallback LLM Wrapper

Provides fallback LLM service that automatically switches to Gemini
when the primary LLM service fails.
"""

import sys
from pathlib import Path
from typing import Optional, Any
from livekit.agents import llm

# Add backend to path for imports
backend_path = Path(__file__).parent.parent.parent / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class FallbackLLM:
    """
    LLM wrapper that falls back to Gemini when primary LLM fails.
    """
    
    def __init__(
        self,
        primary_llm: llm.LLM,
        fallback_llm: Optional[llm.LLM] = None,
        max_primary_failures: int = 3
    ):
        """
        Initialize fallback LLM wrapper.
        
        Args:
            primary_llm: Primary LLM service (self-hosted)
            fallback_llm: Fallback LLM service (Gemini, optional)
            max_primary_failures: Max failures before switching to fallback
        """
        self._primary_llm = primary_llm
        self._fallback_llm = fallback_llm
        self._max_primary_failures = max_primary_failures
        self._primary_failures = 0
        self._using_fallback = False
        
        logger.info(
            f"✅ FallbackLLM initialized: "
            f"primary={type(primary_llm).__name__}, "
            f"fallback={'Gemini' if fallback_llm else 'disabled'}"
        )
    
    def __getattr__(self, name: str):
        """Proxy all attributes to active LLM."""
        active_llm = self._fallback_llm if self._using_fallback else self._primary_llm
        return getattr(active_llm, name)
    
    def chat(self, *args, **kwargs):
        """
        Proxy chat method with fallback support.
        """
        # Return a FallbackLLMChat wrapper that handles the actual fallback logic
        return FallbackLLMChat(
            primary_llm=self._primary_llm,
            fallback_llm=self._fallback_llm,
            fallback_llm_wrapper=self,
            args=args,
            kwargs=kwargs
        )


class FallbackLLMChat:
    """Wrapper for LLM chat context with fallback."""
    
    def __init__(self, primary_llm, fallback_llm, fallback_llm_wrapper, args, kwargs):
        self._primary_llm = primary_llm
        self._fallback_llm = fallback_llm
        self._wrapper = fallback_llm_wrapper
        self._args = args
        self._kwargs = kwargs
        self._active_chat = None
        self._using_fallback = fallback_llm_wrapper._using_fallback
    
    async def __aenter__(self):
        # Start with the appropriate LLM based on wrapper state
        if self._using_fallback and self._fallback_llm:
            self._active_chat = self._fallback_llm.chat(*self._args, **self._kwargs)
        else:
            self._active_chat = self._primary_llm.chat(*self._args, **self._kwargs)
        
        return await self._active_chat.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._active_chat:
            return await self._active_chat.__aexit__(exc_type, exc_val, exc_tb)
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        try:
            if self._active_chat is None:
                raise RuntimeError("Chat context not entered")
            
            return await self._active_chat.__anext__()
            
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
                "502" in error_msg
            )
            
            # Only try fallback if we have one and haven't switched yet
            if is_recoverable and self._fallback_llm and not self._using_fallback:
                self._wrapper._primary_failures += 1
                logger.warning(
                    f"⚠️  Primary LLM failed ({self._wrapper._primary_failures}/{self._wrapper._max_primary_failures}): "
                    f"{type(e).__name__}: {error_msg}"
                )
                
                if self._wrapper._primary_failures >= self._wrapper._max_primary_failures:
                    logger.warning("🔄 Switching to Gemini fallback LLM")
                    self._wrapper._using_fallback = True
                    self._using_fallback = True
                    
                    # Close current chat and start new one with fallback
                    try:
                        await self._active_chat.__aexit__(None, None, None)
                    except:
                        pass  # Ignore cleanup errors
                    
                    # Start fallback chat
                    self._active_chat = self._fallback_llm.chat(*self._args, **self._kwargs)
                    await self._active_chat.__aenter__()
                    
                    # Try to get first response from fallback
                    try:
                        return await self._active_chat.__anext__()
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback LLM also failed: {fallback_error}", exc_info=True)
                        raise
            
            # Re-raise if not recoverable or no fallback available
            raise
