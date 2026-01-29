"""
Grok (xAI) LLM Adapter for LiveKit Agents

Provides a LiveKit-compatible LLM interface for xAI's Grok models.
Uses HTTP requests directly (no SDK dependency) for Python 3.9 compatibility.
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, AsyncIterator, Any, List, Dict
from livekit.agents import llm

# Add backend to path for imports
backend_path = Path(__file__).parent.parent.parent / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not installed. Install with: pip install httpx")


class GrokLLM(llm.LLM):
    """
    LiveKit LLM adapter for xAI's Grok models.
    Uses HTTP API directly (no SDK dependency).
    """
    
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "grok-2-1212",
        **kwargs
    ):
        """
        Initialize Grok LLM.
        
        Args:
            api_key: xAI API key
            model: Grok model name (default: "grok-2-1212")
            **kwargs: Additional arguments (ignored for compatibility)
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is not installed. Install with: pip install httpx"
            )
        
        if not api_key:
            raise ValueError("XAI_API_KEY is required")
        
        # Initialize parent class (LLM base class provides event emitter functionality)
        super().__init__(**kwargs)
        
        self._api_key = api_key
        self._model = model
        self._base_url = "https://api.x.ai"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        
        logger.info(f"✅ GrokLLM initialized: model={model}")
    
    def chat(
        self,
        *,
        chat_ctx: Optional[llm.ChatContext] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> "GrokChat":
        """
        Create a chat context for Grok.
        
        Args:
            chat_ctx: Chat context with messages
            temperature: Temperature for generation
            **kwargs: Additional arguments (function calling not supported)
        
        Returns:
            GrokChat instance
        """
        return GrokChat(
            client=self._client,
            model=self._model,
            chat_ctx=chat_ctx,
            temperature=temperature,
        )
    
    async def aclose(self):
        """Close the HTTP client."""
        await self._client.aclose()


class GrokChat:
    """
    Chat context for Grok LLM.
    Uses HTTP API directly.
    Implements async context manager and async iterator protocols.
    """
    
    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        chat_ctx: Optional[llm.ChatContext] = None,
        temperature: Optional[float] = None,
    ):
        self._client = client
        self._model = model
        self._temperature = temperature or 0.7
        
        # Track if we've already returned the response
        self._response_returned = False
        self._cached_response: Optional[str] = None
        
        # Convert LiveKit messages to xAI API format
        self._messages: List[Dict[str, str]] = []
        
        if chat_ctx:
            try:
                # ChatContext should have a messages attribute (list of ChatMessage)
                # But check if it exists first to handle different versions
                messages_list = None
                
                # Try accessing messages attribute (most common)
                if hasattr(chat_ctx, 'messages'):
                    messages_list = getattr(chat_ctx, 'messages', None)
                # Fallback: try if chat_ctx itself is a list/iterable of messages
                elif isinstance(chat_ctx, (list, tuple)):
                    messages_list = chat_ctx
                # Fallback: try iterating directly
                elif hasattr(chat_ctx, '__iter__') and not isinstance(chat_ctx, (str, bytes)):
                    try:
                        messages_list = list(chat_ctx)
                    except (TypeError, AttributeError):
                        pass
                
                # Process messages if we found them
                if messages_list:
                    for msg in messages_list:
                        if isinstance(msg, llm.ChatMessage):
                            role = msg.role
                            content = msg.content
                            
                            # Map LiveKit roles to xAI API format
                            # xAI API uses: "system", "user", "assistant"
                            if role in ["system", "user", "assistant"]:
                                self._messages.append({
                                    "role": role,
                                    "content": content
                                })
                            else:
                                # Map other roles to "user"
                                self._messages.append({
                                    "role": "user",
                                    "content": content
                                })
                else:
                    # If we can't find messages, log debug info and continue with empty messages
                    logger.debug(f"[GrokLLM] ChatContext provided but no messages found. Type: {type(chat_ctx)}, Attributes: {[a for a in dir(chat_ctx) if not a.startswith('_')]}")
                    self._messages = []
            except Exception as e:
                # If we can't access messages, log and continue with empty messages
                logger.warning(f"[GrokLLM] Error extracting messages from ChatContext: {e}. Starting with empty message history.")
                self._messages = []
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def __aiter__(self) -> AsyncIterator[llm.ChatChunk]:
        return self
    
    async def __anext__(self) -> llm.ChatChunk:
        """
        Get the next chunk from Grok via HTTP API.
        
        Note: xAI API returns the full response in one call,
        so we yield it as a single chunk and then raise StopAsyncIteration.
        """
        # If we've already returned the response, stop iteration
        if self._response_returned:
            raise StopAsyncIteration
        
        try:
            # Get response from Grok API (only call once)
            if self._cached_response is None:
                # Prepare request payload
                payload = {
                    "model": self._model,
                    "messages": self._messages,
                    "temperature": self._temperature,
                }
                
                # Make API request to xAI chat completions endpoint
                # xAI API is OpenAI-compatible
                response = await self._client.post(
                    "/v1/chat/completions",
                    json=payload
                )
                response.raise_for_status()
                
                # Parse response
                data = response.json()
                
                # Extract content from response
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        self._cached_response = choice["message"]["content"]
                    else:
                        raise ValueError(f"Unexpected response format: {data}")
                else:
                    raise ValueError(f"No choices in response: {data}")
            
            # Mark as returned
            self._response_returned = True
            
            # LiveKit agents expect ChatChunk(id, delta=ChoiceDelta(role, content)), NOT choices/ChatDelta
            chunk = llm.ChatChunk(
                id="grok-chunk",
                delta=llm.ChoiceDelta(
                    role="assistant",
                    content=self._cached_response or "",
                ),
            )
            
            return chunk
            
        except StopAsyncIteration:
            raise
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error from Grok API: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            logger.error(f"Error getting Grok response: {e}", exc_info=True)
            raise
    
    def append(self, message: llm.ChatMessage):
        """
        Append a message to the chat context.
        """
        role = message.role
        content = message.content
        
        # Map LiveKit roles to xAI API format
        if role in ["system", "user", "assistant"]:
            self._messages.append({
                "role": role,
                "content": content
            })
        else:
            # Map other roles to "user"
            self._messages.append({
                "role": "user",
                "content": content
            })
    
    async def aclose(self):
        """Close the chat context."""
        pass
