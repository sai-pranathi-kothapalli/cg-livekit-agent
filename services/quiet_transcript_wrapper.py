"""
Quiet Transcript Wrapper

Wraps TranscriptForwardingService to reduce logging spam during streaming.
Instead of logging every chunk, only logs first and last.
"""

from typing import Any
from agents.utils import logger


class QuietTranscriptWrapper:
    """
    Wraps transcript service to reduce streaming spam.
    
    Only logs first chunk and final chunk, not every intermediate chunk.
    """
    
    def __init__(self, original_service: Any):
        """
        Initialize wrapper.
        
        Args:
            original_service: Original TranscriptForwardingService
        """
        self._service = original_service
        self._chunk_count = 0
        self._logged_first = False
        logger.info("QuietTranscriptWrapper initialized - reducing streaming log spam")
    
    async def send_transcript(self, text: str, transcript_type: str = "agentTranscript", max_retries: int = 2):
        """
        Send transcript with reduced logging.
        
        Args:
            text: Transcript text
            transcript_type: Type of transcript
            max_retries: Max retry attempts
        """
        self._chunk_count += 1
        
        # Only log first chunk
        if not self._logged_first:
            self._logged_first = True
            logger.debug(f"📤 Streaming response to frontend (chunk 1, {len(text)} chars)...")
        
        # Call original service (it will do its own logging at DEBUG level)
        await self._service.send_transcript(text, transcript_type, max_retries)
    
    def reset(self):
        """Reset state for next response"""
        if self._chunk_count > 0:
            logger.debug(f"📤 Streamed {self._chunk_count} chunks total")
        self._chunk_count = 0
        self._logged_first = False
    
    def __getattr__(self, name):
        """Forward all other attributes to original service"""
        return getattr(self._service, name)
