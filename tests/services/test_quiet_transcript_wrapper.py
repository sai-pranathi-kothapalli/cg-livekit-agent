import pytest
from unittest.mock import MagicMock, AsyncMock
from services.quiet_transcript_wrapper import QuietTranscriptWrapper

@pytest.mark.asyncio
async def test_quiet_transcript_wrapper_logging():
    """Test that QuietTranscriptWrapper correctly identifies the first chunk and counts chunks."""
    mock_service = AsyncMock()
    wrapper = QuietTranscriptWrapper(mock_service)
    
    # Send multiple transcripts
    await wrapper.send_transcript("Chunk 1")
    await wrapper.send_transcript("Chunk 2")
    await wrapper.send_transcript("Chunk 3")
    
    assert wrapper._chunk_count == 3
    assert wrapper._logged_first is True
    assert mock_service.send_transcript.call_count == 3
    
    # Reset and verify
    wrapper.reset()
    assert wrapper._chunk_count == 0
    assert wrapper._logged_first is False

def test_quiet_transcript_wrapper_getattr():
    """Test that attributes are correctly forwarded to the original service."""
    mock_service = MagicMock()
    mock_service.some_attr = "value"
    wrapper = QuietTranscriptWrapper(mock_service)
    
    assert wrapper.some_attr == "value"
    assert wrapper.original_service is not None # Wait, original_service is not an attr of wrapper, but it forwards
