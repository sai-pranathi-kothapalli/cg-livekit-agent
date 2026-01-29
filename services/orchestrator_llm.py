"""
Orchestrator LLM Adapter for LiveKit Agents

Provides a LiveKit-compatible LLM interface that uses the Skillifire orchestrator API.
The orchestrator handles conversation history, context management, and LLM calls.
"""

import sys
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


class OrchestratorLLM(llm.LLM):
    """
    LiveKit LLM adapter for Skillifire orchestrator API.
    Uses orchestrator for all LLM calls - handles history, context, and LLM internally.
    """
    
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        session_id: str,
        candidate_name: Optional[str] = None,
        candidate_role: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Orchestrator LLM.
        
        Args:
            base_url: Orchestrator API base URL (from env ORCHESTRATOR_BASE_URL)
            session_id: Session ID (room name or booking token) - same ID = same conversation
            candidate_name: Candidate name (optional, for context memory)
            candidate_role: Candidate role (optional, for context memory)
            **kwargs: Additional arguments (ignored for compatibility)
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is not installed. Install with: pip install httpx"
            )
        
        if not session_id:
            raise ValueError("session_id is required")
        
        if not base_url:
            raise ValueError("base_url is required (set ORCHESTRATOR_BASE_URL in .env)")
        
        # Initialize parent class
        super().__init__(**kwargs)
        
        self._base_url = base_url.rstrip('/')
        self._session_id = session_id
        self._candidate_name = candidate_name
        self._candidate_role = candidate_role
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        
        logger.info(
            f"✅ OrchestratorLLM initialized: "
            f"session_id={session_id}, "
            f"candidate_name={candidate_name or 'not set'}, "
            f"candidate_role={candidate_role or 'not set'}"
        )
    
    @property
    def model(self) -> str:
        """Return orchestrator identifier."""
        return "orchestrator"
    
    @property
    def provider(self) -> str:
        """Return orchestrator provider name."""
        return "skillifire-orchestrator"
    
    def chat(
        self,
        *,
        chat_ctx: Optional[llm.ChatContext] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> "OrchestratorChat":
        """
        Create a chat context for orchestrator.
        
        Args:
            chat_ctx: Chat context with messages and system prompt
            temperature: Temperature for generation (ignored - orchestrator handles it)
            **kwargs: Additional arguments (ignored)
        
        Returns:
            OrchestratorChat instance
        """
        return OrchestratorChat(
            client=self._client,
            session_id=self._session_id,
            candidate_name=self._candidate_name,
            candidate_role=self._candidate_role,
            chat_ctx=chat_ctx,
        )
    
    async def aclose(self):
        """Close the HTTP client."""
        await self._client.aclose()


class OrchestratorChat:
    """
    Chat context for Orchestrator LLM.
    Implements async context manager and async iterator protocols.
    """
    
    def __init__(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        candidate_name: Optional[str],
        candidate_role: Optional[str],
        chat_ctx: Optional[llm.ChatContext] = None,
    ):
        self._client = client
        self._session_id = session_id
        self._candidate_name = candidate_name
        self._candidate_role = candidate_role
        
        # Track if we've already returned the response
        self._response_returned = False
        self._cached_response: Optional[str] = None
        
        # Extract system prompt and user message from chat context
        self._system_prompt = ""
        self._user_text = ""
        
        if chat_ctx:
            try:
                # Extract messages from chat context
                messages_list = None
                
                # Try different ways to access messages
                if hasattr(chat_ctx, 'messages'):
                    messages_list = getattr(chat_ctx, 'messages', None)
                elif hasattr(chat_ctx, '_items'):
                    # ChatContext has _items list
                    items = getattr(chat_ctx, '_items', [])
                    messages_list = []
                    for item in items:
                        if hasattr(item, 'role') and hasattr(item, 'content'):
                            # Create a simple message-like object
                            class SimpleMessage:
                                def __init__(self, role, content):
                                    self.role = role
                                    self.content = content
                            messages_list.append(SimpleMessage(item.role, item.content))
                elif isinstance(chat_ctx, (list, tuple)):
                    messages_list = chat_ctx
                elif hasattr(chat_ctx, '__iter__') and not isinstance(chat_ctx, (str, bytes)):
                    try:
                        messages_list = list(chat_ctx)
                    except (TypeError, AttributeError):
                        pass
                
                if messages_list:
                    for msg in messages_list:
                        # Handle both ChatMessage objects and simple objects with role/content
                        role = getattr(msg, 'role', None)
                        content = getattr(msg, 'content', None) or getattr(msg, 'text', None)
                        
                        if role and content:
                            if role == "system" or role == "developer":
                                # Accumulate system prompts (in case there are multiple)
                                if self._system_prompt:
                                    self._system_prompt += "\n\n" + str(content)
                                else:
                                    self._system_prompt = str(content)
                            elif role == "user":
                                # Use the last user message as the current turn
                                self._user_text = str(content)
                            # Ignore assistant messages - orchestrator has history
                else:
                    logger.debug(f"[OrchestratorLLM] ChatContext provided but no messages found. Type: {type(chat_ctx)}")
            except Exception as e:
                logger.warning(f"[OrchestratorLLM] Error extracting messages from ChatContext: {e}", exc_info=True)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def __aiter__(self) -> AsyncIterator[llm.ChatChunk]:
        return self
    
    async def __anext__(self) -> llm.ChatChunk:
        """
        Get the next chunk from orchestrator API.
        
        Note: Orchestrator returns the full response in one call,
        so we yield it as a single chunk and then raise StopAsyncIteration.
        """
        # If we've already returned the response, stop iteration
        if self._response_returned:
            raise StopAsyncIteration
        
        try:
            # Get response from orchestrator API (only call once)
            if self._cached_response is None:
                # Prepare request payload
                payload = {
                    "session_id": self._session_id,
                    "speaker": "user",
                    "text": self._user_text,
                    "system_prompt": self._system_prompt,
                }
                
                # Add candidate context if available
                if self._candidate_name:
                    payload["candidate_name"] = self._candidate_name
                if self._candidate_role:
                    payload["candidate_role"] = self._candidate_role
                
                # Make API request to orchestrator
                response = await self._client.post(
                    "/chat/turn",
                    json=payload
                )
                response.raise_for_status()
                
                # Parse response
                data = response.json()
                
                # Extract response text
                if "response" in data:
                    self._cached_response = data["response"]
                else:
                    raise ValueError(f"Unexpected response format: {data}")
            
            # Mark as returned
            self._response_returned = True
            
            # Create a ChatChunk with the response content
            chunk = llm.ChatChunk(
                id="orchestrator-chunk",
                delta=llm.ChoiceDelta(
                    role="assistant",
                    content=self._cached_response or "",
                ),
            )
            
            return chunk
            
        except StopAsyncIteration:
            raise
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error from Orchestrator API: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            logger.error(f"Error getting Orchestrator response: {e}", exc_info=True)
            raise
    
    def append(self, message: llm.ChatMessage):
        """
        Append a message to the chat context.
        Note: Orchestrator manages history, so we just track the latest user message.
        """
        if message.role == "user":
            self._user_text = message.content
        elif message.role == "system":
            self._system_prompt = message.content
    
    async def aclose(self):
        """Close the chat context."""
        pass
