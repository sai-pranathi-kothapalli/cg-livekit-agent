import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from services.transcript_storage_wrapper import TranscriptStorageWrapper

@pytest.fixture
def mock_storage_svc():
    with patch('services.transcript_storage_wrapper.get_transcript_storage_service') as mock:
        svc = MagicMock()
        mock.return_value = svc
        yield svc

@pytest.mark.asyncio
async def test_transcript_storage_wrapper_init(mock_storage_svc):
    """Test initialization and index recovery."""
    mock_storage_svc.get_transcript.return_value = [{"index": 5}]
    
    original_svc = AsyncMock()
    wrapper = TranscriptStorageWrapper(original_svc, "room_123", "token_123")
    
    assert wrapper._booking_token == "token_123"
    assert wrapper.get_next_message_index() == 6

@pytest.mark.asyncio
async def test_transcript_storage_wrapper_send(mock_storage_svc):
    """Test forwarding and saving transcripts."""
    original_svc = AsyncMock()
    wrapper = TranscriptStorageWrapper(original_svc, "room_123", "token_123")
    
    await wrapper.send_transcript("Hello", transcript_type="userTranscript")
    
    original_svc.send_transcript.assert_called_with("Hello", "userTranscript", 2)
    mock_storage_svc.save_transcript_message.assert_called()

def test_extract_token_from_room():
    original_svc = AsyncMock()
    wrapper = TranscriptStorageWrapper(original_svc, "room_xyz")
    
    assert wrapper._extract_token_from_room("interview_token123") == "token123"
    assert wrapper._extract_token_from_room("room_abc") == "abc"
    assert wrapper._extract_token_from_room("a" * 32) == "a" * 32
    assert wrapper._extract_token_from_room("too_short") is None
