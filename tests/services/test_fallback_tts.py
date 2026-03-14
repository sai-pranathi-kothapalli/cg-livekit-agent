import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from services.fallback_tts import FallbackTTS

@pytest.fixture
def mock_tts():
    tts = MagicMock()
    # Mock synthesize returning an async context manager
    stream = AsyncMock()
    stream.__aenter__.return_value = stream
    stream.__aexit__ = AsyncMock()
    stream.__aiter__.return_value = stream
    stream.__anext__.side_effect = ["Chunk", StopAsyncIteration]
    tts.synthesize.return_value = stream
    tts.stream.return_value = stream
    return tts

@pytest.mark.asyncio
async def test_fallback_tts_primary_success(mock_tts):
    """Test primary TTS synthesis succeeds."""
    primary = mock_tts
    fallback = MagicMock()
    
    wrapper = FallbackTTS(primary, fallback, max_primary_failures=2)
    
    stream = wrapper.synthesize("hello")
    async with stream as s:
        chunks = []
        async for chunk in s:
            chunks.append(chunk)
            
    assert len(chunks) == 1
    assert chunks[0] == "Chunk"
    assert primary.synthesize.called
    assert not fallback.synthesize.called

@pytest.mark.asyncio
async def test_fallback_tts_triggers_fallback(mock_tts):
    """Test switch to fallback TTS after failures."""
    primary = MagicMock()
    # Mock failure stream
    fail_stream = AsyncMock()
    fail_stream.__aenter__.return_value = fail_stream
    fail_stream.__aexit__ = AsyncMock()
    fail_stream.__anext__.side_effect = Exception("500 Internal Server Error")
    primary.synthesize.return_value = fail_stream
    
    fallback = mock_tts
    
    wrapper = FallbackTTS(primary, fallback, max_primary_failures=1)
    
    stream = wrapper.synthesize("hello")
    
    async with stream as s:
        # The fallback logic happens in __anext__
        chunk = await s.__anext__()
        assert chunk == "Chunk"
        
    assert wrapper._using_fallback is True
    assert primary.synthesize.called
    assert fallback.synthesize.called
