import pytest
import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from handlers.data_handlers import setup_data_handlers, _extract_verdict_from_response

@pytest.fixture
def mock_room():
    room = MagicMock()
    room.on = MagicMock()
    # Mock event registry
    room._handlers = {}
    def on_deco(event_name):
        def decorator(func):
            room._handlers[event_name] = func
            return func
        return decorator
    room.on.side_effect = on_deco
    return room

def test_extract_verdict_from_response():
    """Test verdict extraction logic."""
    assert _extract_verdict_from_response("The solution is correct.") == "Correct"
    assert _extract_verdict_from_response("It fails on edge cases.") == "Wrong"
    assert _extract_verdict_from_response("Correct but misses some cases.") == "Partially Correct"
    assert _extract_verdict_from_response("Mostly correct") == "Partially Correct"
    assert _extract_verdict_from_response("I don't know.") == "Pending Evaluation"

@pytest.mark.asyncio
async def test_setup_data_handlers_code_submission(mock_room):
    """Test handling of code-submission data packet."""
    session = MagicMock()
    setup_data_handlers(mock_room, session)
    
    event = MagicMock()
    event.topic = "code-submission"
    event.data = json.dumps({
        "code": "print('hello')",
        "time_taken_seconds": 120,
        "observation_count": 2,
        "language": "python",
        "question": "Hello",
        "executionOutput": "hello"
    })
    
    with patch('handlers.data_handlers.generate_reply_with_instructions', new_callable=AsyncMock) as mock_reply, \
         patch('handlers.data_handlers.interview_state.add_code_submission') as mock_add:
        
        mock_room._handlers["data_received"](event)
        
        mock_add.assert_called_once()
        await asyncio.sleep(0.1)
        mock_reply.assert_called()

@pytest.mark.asyncio
async def test_handle_monitoring(mock_room):
    """Test handling of monitoring data packet."""
    session = MagicMock()
    setup_data_handlers(mock_room, session)
    
    event = MagicMock()
    event.topic = "monitoring"
    event.data = json.dumps({
        "alertType": "multiple_people_detected",
        "message": "Too many faces"
    })
    event.participant.identity = "participant1"
    
    with patch('handlers.data_handlers.generate_reply_with_instructions', new_callable=AsyncMock) as mock_reply, \
         patch('handlers.data_handlers.interview_state.add_violation') as mock_violation:
        
        mock_room._handlers["data_received"](event)
        
        mock_violation.assert_called_once()
        await asyncio.sleep(0.1)
        mock_reply.assert_called()

@pytest.mark.asyncio
async def test_handle_code_observation(mock_room):
    """Test handling of code-observation data packet."""
    session = MagicMock()
    setup_data_handlers(mock_room, session)
    
    event = MagicMock()
    event.topic = "code-observation"
    event.data = json.dumps({
        "current_code": "p",
        "question": "Q1",
        "language": "python"
    })
    
    with patch('handlers.data_handlers.generate_reply_with_instructions', new_callable=AsyncMock) as mock_reply:
        mock_room._handlers["data_received"](event)
        await asyncio.sleep(0.1)
        mock_reply.assert_called()

@pytest.mark.asyncio
async def test_handle_code_snapshot(mock_room):
    """Test handling of code-snapshot data packet."""
    session = MagicMock()
    
    # Pass a mock logger instance to setup_data_handlers
    mock_log = MagicMock()
    setup_data_handlers(mock_room, session, logger_instance=mock_log)
    
    event = MagicMock()
    event.topic = "code-snapshot"
    event.data = json.dumps({
        "code": "print('live')",
        "question": "Q",
        "language": "python"
    })
    
    mock_room._handlers["data_received"](event)
    mock_log.debug.assert_called()

@pytest.mark.asyncio
async def test_handle_code_idle(mock_room):
    """Test handling of code-idle data packet."""
    session = MagicMock()
    setup_data_handlers(mock_room, session)
    
    event = MagicMock()
    event.topic = "code-idle"
    event.data = json.dumps({
        "code": "print('idle')",
        "question": "Q"
    })
    event.participant.identity = "p1"
    
    with patch('handlers.data_handlers.generate_reply_with_instructions', new_callable=AsyncMock) as mock_reply:
        mock_room._handlers["data_received"](event)
        await asyncio.sleep(0.1)
        mock_reply.assert_called()
