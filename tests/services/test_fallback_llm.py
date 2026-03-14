import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from services.fallback_llm import FallbackLLM

@pytest.fixture
def mock_chat():
    chat = AsyncMock()
    chat.__aenter__ = AsyncMock(return_value=chat)
    chat.__aexit__ = AsyncMock()
    chat.__anext__ = AsyncMock(return_value="Response")
    return chat

@pytest.mark.asyncio
async def test_fallback_llm_primary_success(mock_chat):
    """Test primary LLM succeeds immediately."""
    primary = MagicMock()
    primary.chat.return_value = mock_chat
    
    fallback = MagicMock()
    
    llm = FallbackLLM(primary, fallback, max_primary_failures=2)
    
    # Wrap a mock chat session
    wrapped_chat = llm.chat(prompt="hello")
    
    async with wrapped_chat as stream:
        res = await stream.__anext__()
    
    assert res == "Response"
    primary.chat.assert_called()
    assert not fallback.chat.called

@pytest.mark.asyncio
async def test_fallback_llm_triggers_fallback(mock_chat):
    """Test fallback LLM takes over after primary failures."""
    primary = MagicMock()
    fail_chat = AsyncMock()
    fail_chat.__aenter__ = AsyncMock(return_value=fail_chat)
    fail_chat.__anext__.side_effect = Exception("500 Internal Server Error")
    primary.chat.return_value = fail_chat
    
    fallback = MagicMock()
    success_chat = AsyncMock()
    success_chat.__aenter__ = AsyncMock(return_value=success_chat)
    success_chat.__anext__.return_value = "Fallback Response"
    fallback.chat.return_value = success_chat
    
    llm = FallbackLLM(primary, fallback, max_primary_failures=1)
    
    wrapped_chat = llm.chat(prompt="hello")
    
    async with wrapped_chat as stream:
        res = await stream.__anext__()
    
    assert res == "Fallback Response"
    assert llm._primary_failures == 1
    assert llm._using_fallback is True
    
    # Second call - should use fallback directly
    wrapped_chat2 = llm.chat(prompt="hi")
    async with wrapped_chat2 as stream2:
        res2 = await stream2.__anext__()
    assert res2 == "Fallback Response"
    assert primary.chat.call_count == 1 # Only called once for first fail
