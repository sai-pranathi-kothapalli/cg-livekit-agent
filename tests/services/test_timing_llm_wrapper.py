import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from services.timing_llm_wrapper import TimingLLMWrapper

@pytest.mark.asyncio
async def test_timing_llm_wrapper():
    """Test token aggregation in LLM wrapper."""
    mock_chat = AsyncMock()
    # TimingLLMWrapper expects a callable that returns an AsyncContextManager
    original_chat = MagicMock(return_value=mock_chat)
    mock_chat.__aenter__ = AsyncMock(return_value=mock_chat)
    mock_chat.__aexit__ = AsyncMock()
    
    wrapper = TimingLLMWrapper(original_chat)
    
    # Test aggregation
    wrapper.aggregate_usage(10, 20)
    usage = wrapper.get_total_usage()
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 20
    assert usage["total_tokens"] == 30

def test_timing_llm_aggregation():
    mock_chat = MagicMock()
    wrapper = TimingLLMWrapper(mock_chat)
    
    wrapper.aggregate_usage(100, 50)
    wrapper.aggregate_usage(200, 100)
    usage = wrapper.get_total_usage()
    assert usage["input_tokens"] == 300
    assert usage["output_tokens"] == 150
