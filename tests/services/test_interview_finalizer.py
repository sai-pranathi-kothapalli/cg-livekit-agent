import pytest
import sys
import json
from unittest.mock import MagicMock
from services.interview_finalizer import finalize_interview

@pytest.mark.asyncio
async def test_finalize_interview_success():
    """Test full finalizing flow with evaluation creation."""
    mock_config = MagicMock()
    mock_plugins = {"llm": MagicMock()}
    
    # Mock LLM usage
    llm = mock_plugins["llm"]
    llm.chat = MagicMock()
    llm.chat.get_total_usage.return_value = {"prompt_tokens": 100, "completion_tokens": 50}
    
    # Use sys.modules mocks
    mock_booking_mod = sys.modules['app.services.booking_service']
    mock_eval_mod = sys.modules['app.services.evaluation_service']
    mock_transcript_mod = sys.modules['app.services.transcript_storage_service']
    
    mock_transcript_mod.TranscriptStorageService.return_value.get_transcript.return_value = "Sample Transcript"
    mock_eval_mod.EvaluationService.return_value.calculate_evaluation_from_transcript.return_value = "eval_123"
    
    await finalize_interview(
        booking_token="token123",
        room_name="room123",
        interview_start_time=None,
        plugins=mock_plugins,
        config=mock_config
    )
    
    # Verify calls
    mock_booking_mod.BookingService.return_value.update_booking_status.assert_called_with("token123", "completed")
    mock_eval_mod.EvaluationService.return_value.calculate_evaluation_from_transcript.assert_called()
        
@pytest.mark.asyncio
async def test_finalize_interview_no_token():
    """Verify skips if no token."""
    await finalize_interview(None, "room", None, {}, MagicMock())
    # Should complete without error
