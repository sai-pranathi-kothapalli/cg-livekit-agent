import pytest
from datetime import datetime
from services.session_time_store import set_store, set_store_duration_only, get_store

def test_session_time_store_set_get():
    """Test setting and getting full store state."""
    start = datetime(2026, 3, 14, 12, 0)
    set_store(start, 45, base_template="45", requires_coding=True)
    
    s_start, s_dur, s_temp, s_coding = get_store()
    assert s_start == start
    assert s_dur == 45
    assert s_temp == "45"
    assert s_coding is True

def test_session_time_store_duration_only():
    """Test setting only duration and template."""
    # Reset or verify overwrite
    set_store_duration_only(20, base_template="30", requires_coding=False)
    
    s_start, s_dur, s_temp, s_coding = get_store()
    # s_start remains what it was from previous test if process is same, 
    # but let's just check the ones we set.
    assert s_dur == 20
    assert s_temp == "30"
    assert s_coding is False

def test_session_time_store_invalid_template():
    """Verify invalid template defaults to 30."""
    set_store_duration_only(30, base_template="invalid")
    _, _, s_temp, _ = get_store()
    assert s_temp == "30"

def test_session_time_store_min_duration():
    """Verify duration is at least 1."""
    set_store_duration_only(0)
    _, s_dur, _, _ = get_store()
    assert s_dur == 1
