import pytest
import logging
import json
from unittest.mock import MagicMock, patch
from services.log_interceptor import STTLogInterceptor, install_stt_interceptor

def test_stt_log_interceptor_emit():
    """Test that STTLogInterceptor correctly extracts timing info from logs."""
    interceptor = STTLogInterceptor()
    
    # Mock log_stt_complete
    with patch('services.log_interceptor.log_stt_complete') as mock_log_complete:
        # Create a mock record
        record = MagicMock()
        data = {
            "user_transcript": "Hello world",
            "transcript_delay": 0.5
        }
        record.getMessage.return_value = f"Received user transcript: {json.dumps(data)}"
        
        interceptor.emit(record)
        
        mock_log_complete.assert_called_once_with("Hello world", 0.5)

def test_install_stt_interceptor():
    """Test that the interceptor is correctly installed on the logger."""
    with patch('logging.getLogger') as mock_get_logger:
        mock_lk_logger = MagicMock()
        mock_get_logger.return_value = mock_lk_logger
        
        install_stt_interceptor()
        
        mock_get_logger.assert_called_with('livekit.agents')
        mock_lk_logger.addHandler.assert_called()
