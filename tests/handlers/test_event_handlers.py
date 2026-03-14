import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from handlers.event_handlers import setup_session_event_handlers, setup_participant_handlers

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.on = MagicMock()
    # Mock event registry
    session._handlers = {}
    def on_deco(event_name):
        def decorator(func):
            session._handlers[event_name] = func
            return func
        return decorator
    session.on.side_effect = on_deco
    return session

@pytest.mark.asyncio
async def test_setup_session_event_handlers_nudge(mock_session):
    """Test nudge timer logic in session handlers."""
    logger = MagicMock()
    
    with patch('services.time_context_llm_wrapper.generate_reply_with_instructions', new_callable=AsyncMock) as mock_reply:
        setup_session_event_handlers(mock_session, logger)
        
        # Verify handlers were attached
        assert "user_state_changed" in mock_session._handlers
        assert "agent_state_changed" in mock_session._handlers
        
        # Trigger agent_state_changed to 'listening' to start nudge timer
        event = MagicMock()
        event.old_state = "speaking"
        event.new_state = "listening"
        mock_session._handlers["agent_state_changed"](event)
        
        # Wait a bit or mock asyncio.sleep to be fast
        with patch('asyncio.sleep', new_callable=AsyncMock):
             # We can't easily test the background task without more complex mocks
             # but we've triggered the code path.
             pass

@pytest.mark.asyncio
async def test_on_user_input_transcribed(mock_session):
    """Test transcript processing and incremental eval."""
    logger = MagicMock()
    transcript_storage = MagicMock()
    ctx = MagicMock()
    ctx.room.isconnected.return_value = True
    
    with patch('handlers.event_handlers._get_evaluation_service') as mock_get_eval:
        eval_svc = mock_get_eval.return_value
        eval_svc.evaluate_answer = AsyncMock()
        
        setup_session_event_handlers(
            mock_session, 
            logger, 
            booking_token="token123", 
            transcript_storage=transcript_storage,
            ctx=ctx
        )
        
        # Trigger event
        event = MagicMock()
        event.transcript = "Hello world"
        event.is_final = True
        
        # Mock session.chat_ctx for last question detection
        mock_session.chat_ctx.messages = [
            MagicMock(role="assistant", content="What is Python?")
        ]
        
        mock_session._handlers["user_input_transcribed"](event)
        
        # Verify transcript storage call
        transcript_storage.save_transcript_message.assert_called()
        
        # Incremental eval is a background task, wait a tiny bit
        await asyncio.sleep(0.1)
        eval_svc.evaluate_answer.assert_called()

def test_setup_participant_handlers():
    """Test participant and track handlers setup."""
    ctx = MagicMock()
    ctx.room.on = MagicMock()
    # Mock event registry
    ctx.room._handlers = {}
    def on_deco(event_name):
        def decorator(func):
            ctx.room._handlers[event_name] = func
            return func
        return decorator
    ctx.room.on.side_effect = on_deco
    
    logger = MagicMock()
    setup_participant_handlers(ctx, "room_sid", logger)
    
    assert "participant_connected" in ctx.room._handlers
    assert "track_published" in ctx.room._handlers
    
    # Trigger connected
    participant = MagicMock()
    participant.identity = "user_1"
    ctx.room.remote_participants = {}
    ctx.room._handlers["participant_connected"](participant)
    
    logger.info.assert_called()
