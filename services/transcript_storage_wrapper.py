"""
Transcript Storage Wrapper

Wraps transcript forwarding to also save transcripts to the database.
"""

import sys
from pathlib import Path
from typing import Optional, Callable, AsyncContextManager
from datetime import datetime

# Add backend to path for imports (same as agent.py / entrypoint.py)
_root = Path(__file__).parent.parent.parent
backend_path = _root / "Livekit-Backend-agent-backend"
if not backend_path.exists():
    backend_path = _root / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.utils.logger import get_logger  # type: ignore
from app.config import get_config  # type: ignore

logger = get_logger(__name__)

# Lazy import to avoid circular dependencies
_transcript_storage_service = None
_config = None

def get_transcript_storage_service():
    """Get or create transcript storage service instance."""
    global _transcript_storage_service, _config
    if _transcript_storage_service is None:
        try:
            from app.services.transcript_storage_service import TranscriptStorageService  # type: ignore
            _config = get_config()
            _transcript_storage_service = TranscriptStorageService(_config)
            logger.info("✅ TranscriptStorageService initialized")
        except Exception as e:
            logger.warning(f"⚠️  Failed to initialize TranscriptStorageService: {e}")
            _transcript_storage_service = None
    return _transcript_storage_service


class TranscriptStorageWrapper:
    """
    Wraps transcript forwarding service to also save transcripts to database.
    """
    
    # Class-level storage for message index per booking token (shared across instances)
    _message_indices: dict = {}
    
    def __init__(
        self,
        original_transcript_service,
        room_name: str,
        booking_token: Optional[str] = None,
    ):
        """
        Initialize transcript storage wrapper.
        
        Args:
            original_transcript_service: Original transcript forwarding service
            room_name: LiveKit room name
            booking_token: Booking token (extracted from room name or metadata)
        """
        self._original_service = original_transcript_service
        self._room_name = room_name
        self._booking_token = booking_token or self._extract_token_from_room(room_name)
        self._storage_service = get_transcript_storage_service()
        
        # Initialize or get shared message index for this booking
        if self._booking_token not in self._message_indices:
            # Get current max index from database
            current_index = 0
            if self._storage_service and self._booking_token:
                try:
                    existing_transcripts = self._storage_service.get_transcript(self._booking_token)
                    if existing_transcripts:
                        max_index = max([t.get('index', 0) for t in existing_transcripts], default=-1)
                        current_index = max_index + 1
                except Exception as e:
                    logger.warning(f"Could not get existing transcript count: {e}")
            self._message_indices[self._booking_token] = current_index
        
        logger.info(
            f"✅ TranscriptStorageWrapper initialized: "
            f"room={room_name}, booking_token={self._booking_token or 'unknown'}, "
            f"starting_index={self._message_indices.get(self._booking_token, 0) if self._booking_token else 0}"
        )
    
    def get_next_message_index(self) -> int:
        """Get next message index and increment."""
        if not self._booking_token:
            return 0
        index = self._message_indices.get(self._booking_token, 0)
        self._message_indices[self._booking_token] = index + 1
        return index
    
    def _extract_token_from_room(self, room_name: str) -> Optional[str]:
        """
        Extract booking token from room name.
        Room names are typically in format like: "interview_<token>" or just the token.
        """
        # Try to extract token from room name
        # Common patterns: "interview_<token>", "room_<token>", or just "<token>"
        if room_name.startswith("interview_"):
            return room_name.replace("interview_", "")
        elif room_name.startswith("room_"):
            return room_name.replace("room_", "")
        # If room name looks like a token (32 chars alphanumeric), use it directly
        elif len(room_name) == 32 and room_name.replace("_", "").replace("-", "").isalnum():
            return room_name
        return None
    
    async def send_transcript(
        self,
        text: str,
        transcript_type: str = "agentTranscript",
        max_retries: int = 2
    ) -> None:
        """
        Send transcript to frontend AND save to database.
        """
        # Forward to original service (for frontend)
        await self._original_service.send_transcript(text, transcript_type, max_retries)
        
        # Save to database if storage service is available
        if self._storage_service and self._booking_token:
            try:
                role = "assistant" if transcript_type == "agentTranscript" else "user"
                message_index = self.get_next_message_index()
                success = self._storage_service.save_transcript_message(
                    booking_token=self._booking_token,
                    room_name=self._room_name,
                    role=role,
                    content=text,
                    message_index=message_index,
                    timestamp=datetime.utcnow(),
                )
                if success:
                    logger.debug(f"✅ Saved {role} transcript message (index: {message_index}) to database")
            except Exception as e:
                logger.warning(f"⚠️  Failed to save transcript to database: {e}")
    
    def wrap_llm_chat(
        self,
        original_chat: Callable[..., AsyncContextManager]
    ) -> Callable[..., AsyncContextManager]:
        """
        Wrap LLM chat method (passes through to original service).
        """
        return self._original_service.wrap_llm_chat(original_chat)
