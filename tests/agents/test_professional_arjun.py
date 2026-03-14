import pytest
from unittest.mock import MagicMock, patch
from agents.professional_arjun import ProfessionalArjun

def test_professional_arjun_build_instructions_success():
    """Test successful instruction building with placeholders."""
    candidate_profile = {
        "full_name": "John Doe",
        "skills": "Python, Java"
    }
    base_instructions = "Hello {full_name}, test skills: {skills}. Start in 30 minutes. [INJECT_AT_RUNTIME]"
    
    # Initialize agent
    agent = ProfessionalArjun(
        candidate_profile=candidate_profile,
        base_instructions=base_instructions,
        duration_minutes=45
    )
    
    instructions = agent.instructions
    
    # Check placeholder replacement
    assert "John Doe" in instructions
    assert "Python, Java" in instructions
    # Check duration adaptation
    assert "45 minutes" in instructions
    assert "30 minutes" not in instructions
    # Check date injection (not checking exact date but ensuring the tag is gone)
    assert "[INJECT_AT_RUNTIME]" not in instructions

def test_professional_arjun_missing_instructions():
    """Test that ValueError is raised if no instructions are provided."""
    with pytest.raises(ValueError, match="No system instructions provided"):
        ProfessionalArjun(base_instructions=None)

def test_professional_arjun_estimate_tokens():
    """Test token estimation logic (~3 chars per token)."""
    agent = ProfessionalArjun(base_instructions="123456789")
    assert agent._estimate_tokens("123456") == 2
    assert agent._estimate_tokens("") == 0
    assert agent._estimate_tokens(None) == 0

def test_professional_arjun_on_error_stt():
    """Test on_error logic for STT errors."""
    agent = ProfessionalArjun(base_instructions="Test")
    
    # Mock logger to verify it was called
    with patch('agents.professional_arjun.logger') as mock_logger:
        stt_error = Exception("STT failure occurred")
        agent.on_error(stt_error)
        
        # Verify STT specific log was called
        mock_logger.error.assert_any_call("⚠️  STT Error detected: Exception: STT failure occurred", exc_info=True)

def test_professional_arjun_on_error_generic():
    """Test on_error logic for generic errors."""
    agent = ProfessionalArjun(base_instructions="Test")
    
    with patch('agents.professional_arjun.logger') as mock_logger:
        generic_error = ValueError("Something went wrong")
        agent.on_error(generic_error)
        
        # Verify generic error log was called
        mock_logger.error.assert_any_call("⚠️  Agent error caught: ValueError: Something went wrong", exc_info=True)
