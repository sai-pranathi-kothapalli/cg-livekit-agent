import pytest
from unittest.mock import MagicMock
from services.output_sanitizer import sanitize_agent_response, remove_internal_blocks, OutputSanitizerState

def test_remove_internal_blocks():
    """Test removing internal blocks from text."""
    text = "Hello [INTERNAL notes] there [END INTERNAL CONTEXT]. How are you?"
    result = remove_internal_blocks(text)
    assert result == "Hello . How are you?"

def test_sanitize_agent_response_start_marker():
    """Test stripping from start until END INTERNAL CONTEXT."""
    text = "Some intro [END INTERNAL CONTEXT] Actual message"
    result = sanitize_agent_response(text)
    assert result == "Actual message"

def test_sanitize_agent_response_patterns():
    """Test stripping lines with specific internal patterns."""
    text = "Line 1\nMINUTE. 10/30\nLine 2\nPhase: technical\nLine 3"
    result = sanitize_agent_response(text)
    assert result == "Line 1\nLine 2\nLine 3"

def test_output_sanitizer_state_passthrough():
    """Test state machine for streaming output."""
    state = OutputSanitizerState()
    state.add("Header [INTERNAL] ")
    assert state.take_after_marker() == ""
    
    state.add("notes [END INTERNAL CONTEXT] Real message")
    after = state.take_after_marker()
    assert after == "Real message"
    assert state.should_passthrough() is True

def test_output_sanitizer_state_max_buffer():
    """Test buffer overflow protection."""
    state = OutputSanitizerState()
    # Add 801 chars without marker
    state.add("A" * 801)
    after = state.take_after_marker()
    assert after == ""
    assert state.buffer == ""
    assert state.should_passthrough() is True

def test_output_sanitizer_state_flush():
    """Test flushing remaining buffer at end of stream."""
    state = OutputSanitizerState()
    state.add("Hello")
    assert state.flush_remaining() == "Hello"
    assert state.buffer == ""
