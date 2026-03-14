import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from services.time_context_llm_wrapper import TimeContextLLMWrapper, sanitize_chat_context, _build_system_prompt
from livekit.agents.llm import ChatContext

@pytest.fixture
def mock_chat_ctx():
    return ChatContext()

def test_sanitize_chat_context():
    """Test removal of [INTERNAL] blocks from history."""
    msg = MagicMock()
    msg.content = "Hello [INTERNAL] secret [END INTERNAL CONTEXT] World"
    ctx = MagicMock()
    ctx.messages = [msg]
    
    sanitize_chat_context(ctx)
    
    # Strip whitespace to avoid issues with double spaces
    content = str(msg.content).strip()
    assert "secret" not in content
    assert "Hello World" in content.replace("  ", " ")

def test_build_system_prompt():
    """Test prompt construction for different phases."""
    prompt = _build_system_prompt(10, "intro", 30)
    assert "INTRODUCTION" in prompt
    assert "10 min" in prompt
    
    prompt_wrap = _build_system_prompt(2, "wrap_up", 30)
    assert "WRAP UP" in prompt_wrap

@pytest.mark.asyncio
async def test_time_context_llm_wrapper_injection(mock_chat_ctx):
    """Test that system prompt is injected into chat_ctx copy."""
    original_chat = AsyncMock()
    wrapper = TimeContextLLMWrapper(original_chat)
    
    # Setup store mocks
    with patch('services.time_context_llm_wrapper.get_store', return_value=(0, 30, "template", True)), \
         patch('services.time_context_llm_wrapper.get_time_remaining', return_value=15), \
         patch('services.time_context_llm_wrapper.get_interview_focus', return_value="assessment"):
        
        await wrapper(chat_ctx=mock_chat_ctx)
        
        # Verify original chat was called with a copy of chat_ctx containing system message
        args, kwargs = original_chat.call_args
        injected_ctx = kwargs["chat_ctx"]
        
        assert any("ASSESSMENT" in m.content for m in injected_ctx.messages if m.role == "system")
