import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from services.plugin_service import PluginService
from app.utils.exceptions import ServiceError, ConfigurationError
import services.plugin_service

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.openai.stt_enabled = True
    config.openai.stt_base_url = "http://stt"
    config.openai.stt_model = "whisper"
    
    config.gemini_llm.model = "gemini-1.5-flash"
    config.gemini_llm.api_key = "fake_key"
    
    config.openai.llm_enabled = True
    config.openai.llm_base_url = "http://llm"
    config.openai.llm_model = "qwen"
    config.openai.api_key = "fake_key"
    
    config.openai.tts_enabled = True
    config.openai.tts_base_url = "http://tts"
    config.openai.tts_model = "tts-1"
    config.openai.tts_voice = "alloy"
    
    config.elevenlabs.tts_enabled = False
    
    config.silero_vad.min_speech_duration = 0.1
    config.silero_vad.min_silence_duration = 0.1
    config.silero_vad.activation_threshold = 0.5
    
    config.MAX_CONVERSATION_TOKENS = 1000
    config.MAX_CONVERSATION_MESSAGES = 10
    config.MIN_CONVERSATION_MESSAGES = 2
    
    config.liveavatar.avatar_enabled = False
    
    return config

@pytest.mark.asyncio
async def test_plugin_service_initialize_success(mock_config):
    """Test successful initialization of all plugins."""
    service = PluginService(mock_config)
    mock_room = MagicMock()
    mock_room.name = "room123"
    
    # Mock the plugins submodules
    with patch('livekit.plugins.openai.STT'), \
         patch('livekit.plugins.google.LLM'), \
         patch('livekit.plugins.openai.LLM'), \
         patch('livekit.plugins.openai.TTS'), \
         patch('livekit.plugins.silero.VAD.load'):
        
        plugins = await service.initialize_plugins(mock_room)
        
        assert "stt" in plugins
        assert "llm" in plugins
        assert "tts" in plugins
        assert "vad" in plugins

def test_plugin_service_initialize_stt_disabled(mock_config):
    """Verify error if STT is disabled."""
    mock_config.openai.stt_enabled = False
    service = PluginService(mock_config)
    
    with pytest.raises(ConfigurationError, match="No STT configured"):
        service._initialize_stt()

def test_plugin_service_initialize_tts_elevenlabs(mock_config):
    """Test ElevenLabs TTS initialization."""
    mock_config.openai.tts_enabled = False
    mock_config.elevenlabs.tts_enabled = True
    mock_config.elevenlabs.api_key = "el_key"
    mock_config.elevenlabs.voice_id = "voice1"
    mock_config.elevenlabs.model = "eleven_monolingual_v1"
    
    service = PluginService(mock_config)
    
    # Patch where it is imported in the module under test
    with patch('services.plugin_service.elevenlabs.TTS') as MockTTS:
        # Force the module-level constant
        original_avail = services.plugin_service.ELEVENLABS_AVAILABLE
        services.plugin_service.ELEVENLABS_AVAILABLE = True
        try:
            service._initialize_tts()
            MockTTS.assert_called_once()
        finally:
            services.plugin_service.ELEVENLABS_AVAILABLE = original_avail

@pytest.mark.asyncio
async def test_plugin_service_start_avatar(mock_config):
    """Test LiveAvatar starting logic."""
    mock_config.liveavatar.avatar_enabled = True
    mock_config.liveavatar.api_key = "avatar_key"
    mock_config.liveavatar.avatar_id = "id1"
    
    service = PluginService(mock_config)
    mock_session = MagicMock()
    mock_room = MagicMock()
    
    with patch('services.plugin_service.liveavatar.AvatarSession') as MockSession:
        original_avail = services.plugin_service.LIVEAVATAR_AVAILABLE
        services.plugin_service.LIVEAVATAR_AVAILABLE = True
        try:
            avatar_mock = MockSession.return_value
            avatar_mock.start = AsyncMock()
            
            res = await service.start_live_avatar(mock_session, mock_room)
            assert res == avatar_mock
            avatar_mock.start.assert_called_once()
        finally:
            services.plugin_service.LIVEAVATAR_AVAILABLE = original_avail
