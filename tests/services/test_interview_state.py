import pytest
from services.interview_state import (
    set_current_question, get_current_question, 
    add_violation, add_code_submission, 
    add_probe_response, update_latest_ai_verdict,
    get_state, clear_state
)

def test_interview_state_basic():
    """Test basic question and state tracking."""
    clear_state()
    set_current_question("What is Python?")
    assert get_current_question() == "What is Python?"
    
    add_violation("eye_contact", "Look at the camera", "12:00:01")
    state = get_state()
    assert len(state["violations"]) == 1
    assert state["violations"][0]["alert_type"] == "eye_contact"

def test_interview_state_code_submission():
    """Test code submission and probing."""
    clear_state()
    add_code_submission(
        code="print('hi')",
        question="Print hi",
        ai_verdict="pending",
        execution_output="hi",
        timestamp="12:05:00",
        language="python"
    )
    
    state = get_state()
    assert len(state["code_submissions"]) == 1
    assert state["code_submissions"][0]["submitted_empty"] is False
    
    add_probe_response("Why use print?", "Because it works")
    assert len(state["code_submissions"][0]["probe_responses"]) == 1
    
    update_latest_ai_verdict("pass")
    assert state["code_submissions"][0]["ai_verdict"] == "pass"

def test_interview_state_clear():
    """Test clearing state."""
    set_current_question("Something")
    add_violation("test", "test", "test")
    clear_state()
    
    state = get_state()
    assert state["current_question"] == ""
    assert len(state["violations"]) == 0
    assert len(state["code_submissions"]) == 0
