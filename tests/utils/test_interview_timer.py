import pytest
import math
from datetime import datetime, timedelta, timezone
from utils.interview_timer import get_time_remaining, get_interview_focus

def test_get_time_remaining_basic():
    """Test time remaining calculation."""
    start = datetime(2026, 3, 14, 12, 0, 0)
    duration = 30
    
    # 10 minutes in
    now = start + timedelta(minutes=10)
    assert get_time_remaining(start, duration, now=now) == 20
    
    # 29.5 minutes in (should return 1 due to math.ceil)
    now = start + timedelta(minutes=29, seconds=30)
    assert get_time_remaining(start, duration, now=now) == 1
    
    # 30 minutes in
    now = start + timedelta(minutes=30)
    assert get_time_remaining(start, duration, now=now) == 0
    
    # Over time
    now = start + timedelta(minutes=35)
    assert get_time_remaining(start, duration, now=now) == 0

def test_get_interview_focus_scaling():
    """Test focus determination with standard and scaled durations."""
    # 30 min duration (default)
    assert get_interview_focus(25, 30) == "intro"
    assert get_interview_focus(20, 30) == "assessment"
    assert get_interview_focus(10, 30) == "coding_window"
    assert get_interview_focus(5, 30) == "mixed"
    assert get_interview_focus(1, 30) == "wrap_up"
    assert get_interview_focus(0, 30) == "conclude"
    
    # 60 min duration (everything should be x2)
    assert get_interview_focus(50, 60) == "intro" # 50/2 = 25 > 24
    assert get_interview_focus(35, 60) == "assessment" # 35/2 = 17.5 in (15-24)
    assert get_interview_focus(15, 60) == "coding_window" # 15/2 = 7.5 in (7-15)
    assert get_interview_focus(3, 60) == "mixed" # 3/2 = 1.5 in (1-7)

def test_get_time_remaining_no_now():
    """Test that get_time_remaining uses current time if now is not provided."""
    from unittest.mock import patch
    from datetime import datetime
    fixed_now = datetime(2026, 3, 14, 12, 10)
    with patch('utils.interview_timer.get_now_ist', return_value=fixed_now):
        start = fixed_now - timedelta(minutes=5)
        # 30min duration - 5min elapsed = 25min remaining
        res = get_time_remaining(start, 30)
        assert res == 25
