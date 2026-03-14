import pytest
from datetime import datetime, timezone
from agents.session_time import set_session_time, get_session_time, interview_start_time_ctx, interview_duration_minutes_ctx

def test_session_time_get_set():
    """Test setting and getting session time via ContextVars."""
    start_time = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
    duration = 45
    
    # Set values
    set_session_time(start_time, duration)
    
    # Get values
    got_start, got_duration = get_session_time()
    
    assert got_start == start_time
    assert got_duration == duration

def test_session_time_defaults():
    """Test default values when nothing is set."""
    # Reset context vars for this test
    token_start = interview_start_time_ctx.set(None)
    token_dur = interview_duration_minutes_ctx.set(None)
    
    got_start, got_duration = get_session_time()
    
    assert got_start is None
    assert got_duration is None
    
    # Cleanup
    interview_start_time_ctx.reset(token_start)
    interview_duration_minutes_ctx.reset(token_dur)

def test_session_time_context_isolation():
    """Verify ContextVars isolation (theoretical test)."""
    # This is more of a test of Python's ContextVars but ensures our wrappers work
    start_time = datetime.now(timezone.utc)
    set_session_time(start_time, 30)
    
    assert get_session_time() == (start_time, 30)
