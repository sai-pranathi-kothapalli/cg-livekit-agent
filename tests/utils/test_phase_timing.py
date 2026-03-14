import pytest
from utils.phase_timing import get_phase_durations, get_phase_boundaries, get_phase_end_minutes, get_phase_start_minutes, get_current_phase

def test_get_phase_durations_30():
    """Test 30-min phase distribution."""
    # (6, 10, 10, 3, 1) -> 30
    durations = get_phase_durations(30, base_template="30")
    assert durations == {
        "intro": 6,
        "technical": 10,
        "mcq": 10,
        "general": 3,
        "conclusion": 1,
    }

def test_get_phase_durations_45():
    """Test 45-min phase distribution."""
    # (9, 15, 15, 4, 2) -> 45
    durations = get_phase_durations(45, base_template="45")
    assert durations == {
        "intro": 9,
        "technical": 15,
        "mcq": 15,
        "general": 4,
        "conclusion": 2,
    }

def test_get_phase_durations_scaled():
    """Test scaling to unusual duration (e.g. 15 min)."""
    durations = get_phase_durations(15, base_template="30")
    # Base: 6, 10, 10, 3, 1 (Total 30)
    # Scale: 0.5 -> 3, 5, 5, 1.5(2), 1
    # Total assigned: 3+5+5+2+1 = 16. Rebalance might happen.
    assert sum(durations.values()) == 15

def test_get_phase_durations_zero():
    """Test edge case of zero duration."""
    durations = get_phase_durations(0)
    assert durations["conclusion"] == 1
    assert durations["intro"] == 0

def test_get_phase_boundaries():
    """Test boundary calculation."""
    durations = {"intro": 5, "technical": 10, "mcq": 10, "general": 4, "conclusion": 1}
    boundaries = get_phase_boundaries(durations)
    assert boundaries == (5, 15, 25, 29)

def test_get_phase_end_minutes():
    """Test end boundary map."""
    ends = get_phase_end_minutes(30)
    assert ends["introduction"] == 6
    assert ends["general"] == 29
    assert ends["conclusion"] == 30.0

def test_get_phase_start_minutes():
    """Test start boundary map."""
    starts = get_phase_start_minutes(30)
    assert starts["introduction"] == 0.0
    assert starts["technical"] == 6
    assert starts["conclusion"] == 29

def test_get_current_phase():
    """Test phase detection based on elapsed time."""
    # 30min: 0-6 intro, 6-16 tech, 16-26 mcq, 26-29 general, 29-30 conc
    assert get_current_phase(3, 30) == "introduction"
    assert get_current_phase(10, 30) == "technical"
    assert get_current_phase(20, 30) == "mcq"
    assert get_current_phase(27, 30) == "general"
    assert get_current_phase(29.5, 30) == "conclusion"
    assert get_current_phase(35, 30) == "conclusion"
    assert get_current_phase(-1, 30) == "introduction"
    assert get_current_phase(5, 0) == "conclusion"
