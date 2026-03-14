import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from services.interview_loop import run_interview_time_loop
import app.services.booking_service

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    # Need enough loops: 1 (join), 2 (start), 3 (update), 4 (exit)
    ctx.room.isconnected.side_effect = [True, True, True, True, False]
    ctx.room.remote_participants = {"p1": MagicMock()}
    ctx.room.local_participant.publish_data = AsyncMock()
    ctx.room.disconnect = AsyncMock()
    return ctx

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.agent_state = "listening"
    return session

@pytest.mark.asyncio
async def test_run_interview_time_loop_basic(mock_ctx, mock_session):
    """Test the interview time loop executes and handles candidate joining."""
    start_time = datetime(2026, 3, 14, 12, 0)
    duration = 30
    config = MagicMock()
    
    # Sequence of times to simulate passing
    times = [
        start_time, # join
        start_time + timedelta(seconds=1), # start
        start_time + timedelta(seconds=12), # update
        start_time + timedelta(seconds=13), # loop continues
        start_time + timedelta(seconds=14), # exit (isconnected=False)
    ]
    
    # Mocking external calls
    with patch('services.interview_loop.get_now_ist', side_effect=times), \
         patch('services.interview_loop.get_time_remaining', return_value=25), \
         patch('services.interview_loop.get_interview_focus', return_value="assessment"), \
         patch('services.interview_loop.generate_reply_with_instructions', new_callable=AsyncMock) as mock_gen, \
         patch('services.interview_finalizer.finalize_interview', new_callable=AsyncMock) as mock_finalize, \
         patch('services.session_time_store.set_store_duration_only'), \
         patch('services.session_time_store.get_store', return_value=(start_time, 30, "30", False)), \
         patch('app.services.history_managed_llm_wrapper.reset_questions_asked'), \
         patch('asyncio.sleep', new_callable=AsyncMock):
        
        await run_interview_time_loop(
            ctx=mock_ctx,
            session=mock_session,
            interview_start_time=None, # Entrypoint usually passes None if not started
            interview_duration_minutes=duration,
            scheduled_end_time=None,
            booking_token="token123",
            room_name="room123",
            plugins={},
            config=config
        )
        
        # Verify candidate join was handled and time update was sent
        assert mock_ctx.room.local_participant.publish_data.called
        # Verify finalize was called
        mock_finalize.assert_called_once()

@pytest.mark.asyncio
async def test_run_interview_time_loop_end(mock_ctx, mock_session):
    """Test that the loop triggers closing when time limit is reached."""
    start_time = datetime(2026, 3, 14, 12, 0)
    end_time = start_time + timedelta(minutes=30)
    
    times = [
        start_time, # join
        start_time + timedelta(seconds=1), # start
        end_time + timedelta(seconds=1), # time reached!
        end_time + timedelta(seconds=2), # exit
        end_time + timedelta(seconds=2), # loop exit
    ]
    
    mock_ctx.room.isconnected.side_effect = [True, True, True, True, False]
    
    with patch('services.interview_loop.get_now_ist', side_effect=times), \
         patch('services.interview_loop.get_time_remaining', return_value=0), \
         patch('services.interview_loop.get_interview_focus', return_value="conclude"), \
         patch('services.interview_loop.generate_reply_with_instructions', new_callable=AsyncMock) as mock_gen, \
         patch('services.interview_finalizer.finalize_interview', new_callable=AsyncMock) as mock_finalize, \
         patch('services.session_time_store.get_store', return_value=(start_time, 30, "30", False)), \
         patch('app.services.booking_service.BookingService') as mock_booking_cls, \
         patch('asyncio.sleep', new_callable=AsyncMock):
        
        # Setup participant data to bypass wait
        mock_ctx.room.remote_participants = {"p1": MagicMock()}
        
        await run_interview_time_loop(
            ctx=mock_ctx,
            session=mock_session,
            interview_start_time=None,
            interview_duration_minutes=30,
            scheduled_end_time=None,
            booking_token="token123",
            room_name="room123",
            plugins={},
            config=MagicMock()
        )
        
        # Check if END_INTERVIEW was sent
        mock_gen.assert_any_call(mock_session, instructions="END_INTERVIEW")
        # Check if completion signal was sent
        assert mock_ctx.room.local_participant.publish_data.called
        # Verify finalize was called at the end
        assert mock_finalize.called
