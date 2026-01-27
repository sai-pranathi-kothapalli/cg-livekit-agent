"""
Conversation History Manager

Manages conversation history with intelligent truncation to prevent
context window overflow while maintaining conversation continuity.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


@dataclass
class Message:
    """Represents a single conversation message"""
    role: str  # "user" or "assistant"
    content: str
    tokens: int  # Estimated token count


class ConversationHistoryManager:
    """
    Manages conversation history with sliding window truncation.
    
    Keeps recent messages while removing old ones when approaching
    context window limits. Always preserves system instructions.
    """
    
    def __init__(
        self,
        max_conversation_tokens: int = 4000,
        max_messages: int = 20,
        min_messages_to_keep: int = 6,
        system_instructions_tokens: int = 3500
    ):
        """
        Initialize conversation history manager.
        
        Args:
            max_conversation_tokens: Maximum tokens for conversation messages (excluding system)
            max_messages: Maximum number of messages to keep
            min_messages_to_keep: Minimum messages to keep even if over token limit
            system_instructions_tokens: Estimated tokens for system instructions
        """
        self.max_conversation_tokens = max_conversation_tokens
        self.max_messages = max_messages
        self.min_messages_to_keep = min_messages_to_keep
        self.system_instructions_tokens = system_instructions_tokens
        
        # Track conversation history
        self.messages: List[Message] = []
        self.total_tokens = 0
        
        logger.info(
            f"✅ ConversationHistoryManager initialized: "
            f"max_tokens={max_conversation_tokens}, "
            f"max_messages={max_messages}, "
            f"min_keep={min_messages_to_keep}"
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        Conservative estimate: ~3.5 characters per token.
        """
        if not text:
            return 0
        return len(text) // 3
    
    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to conversation history.
        
        Args:
            role: Message role ("user" or "assistant")
            content: Message content
        """
        tokens = self._estimate_tokens(content)
        message = Message(role=role, content=content, tokens=tokens)
        
        self.messages.append(message)
        self.total_tokens += tokens
        
        logger.debug(
            f"Added {role} message: {tokens} tokens "
            f"(total: {len(self.messages)} messages, {self.total_tokens} tokens)"
        )
        
        # Truncate if needed
        self._truncate_if_needed()
    
    def _truncate_if_needed(self) -> None:
        """
        Truncate old messages if history exceeds limits.
        Uses sliding window approach: remove oldest messages first.
        """
        # Check if we need to truncate
        needs_truncation = (
            len(self.messages) > self.max_messages or
            self.total_tokens > self.max_conversation_tokens
        )
        
        if not needs_truncation:
            return
        
        # Calculate how many messages to remove
        # Always keep at least min_messages_to_keep
        messages_to_remove = max(
            0,
            len(self.messages) - max(self.max_messages, self.min_messages_to_keep)
        )
        
        # If still over token limit, remove more messages
        if self.total_tokens > self.max_conversation_tokens:
            # Remove messages until we're under the limit
            removed_tokens = 0
            while (
                messages_to_remove < len(self.messages) and
                self.total_tokens - removed_tokens > self.max_conversation_tokens and
                len(self.messages) - messages_to_remove > self.min_messages_to_keep
            ):
                removed_tokens += self.messages[messages_to_remove].tokens
                messages_to_remove += 1
        
        if messages_to_remove > 0:
            # Remove oldest messages
            removed = self.messages[:messages_to_remove]
            self.messages = self.messages[messages_to_remove:]
            
            removed_token_count = sum(msg.tokens for msg in removed)
            before_tokens = self.total_tokens
            self.total_tokens -= removed_token_count
            
            logger.warning(
                f"⚠️  TRUNCATION TRIGGERED: "
                f"Removed {messages_to_remove} old messages ({removed_token_count} tokens). "
                f"History: {before_tokens} → {self.total_tokens} tokens, "
                f"{len(self.messages) + messages_to_remove} → {len(self.messages)} messages. "
                f"Reason: {'message limit' if len(self.messages) + messages_to_remove > self.max_messages else 'token limit'}"
            )
    
    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """
        Get formatted messages for LLM API call.
        
        Returns:
            List of message dictionaries with "role" and "content" keys
        """
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]
    
    def get_total_tokens(self) -> int:
        """Get total estimated tokens in conversation history"""
        return self.total_tokens
    
    def get_message_count(self) -> int:
        """Get current number of messages"""
        return len(self.messages)
    
    def clear(self) -> None:
        """Clear all conversation history"""
        self.messages.clear()
        self.total_tokens = 0
        logger.info("Cleared conversation history")

