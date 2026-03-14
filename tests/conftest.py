import sys
from unittest.mock import MagicMock, AsyncMock

# Define MockAgent before using it
class MockAgent:
    def __init__(self, *args, **kwargs):
        self.on = MagicMock()
        self.start = MagicMock()
        self.say = MagicMock()
        self.agent_state = "listening"
        self.chat = MagicMock()
        self.instructions = kwargs.get('instructions', '')
        self.chat_ctx = MagicMock()
        self.chat_ctx.messages = []
    
    def on_error(self, error):
        pass

    def is_running(self):
        return True

    async def generate_reply(self, *args, **kwargs):
        pass

class ChatContext:
    def __init__(self, messages=None):
        self.messages = messages or []
    def copy(self):
        return ChatContext(list(self.messages))
    def add_message(self, role, content, **kwargs):
        msg = MagicMock()
        msg.role = role
        msg.content = content
        self.messages.append(msg)

class LLM:
    ChatContext = ChatContext
    def __init__(self, *args, **kwargs):
        pass

# Mock livekit and its submodules
mock_livekit = MagicMock()
mock_agents = MagicMock()
mock_agents.Agent = MockAgent

# Create llm module
mock_llm_mod = MagicMock()
mock_llm_mod.ChatContext = ChatContext
mock_llm_mod.LLM = LLM

mock_agents.llm = mock_llm_mod

mock_rtc = MagicMock()
mock_plugins = MagicMock()

# Ensure plugins has the necessary submodules as attributes
mock_plugins.openai = MagicMock()
mock_plugins.google = MagicMock()
mock_plugins.elevenlabs = MagicMock()
mock_plugins.silero = MagicMock()
mock_plugins.liveavatar = MagicMock()
mock_plugins.noise_cancellation = MagicMock()

sys.modules['livekit'] = mock_livekit
sys.modules['livekit.agents'] = mock_agents
sys.modules['livekit.agents.llm'] = mock_llm_mod
sys.modules['livekit.rtc'] = mock_rtc
sys.modules['livekit.plugins'] = mock_plugins
sys.modules['livekit.plugins.noise_cancellation'] = mock_plugins.noise_cancellation
sys.modules['livekit.plugins.openai'] = mock_plugins.openai
sys.modules['livekit.plugins.google'] = mock_plugins.google
sys.modules['livekit.plugins.elevenlabs'] = mock_plugins.elevenlabs
sys.modules['livekit.plugins.silero'] = mock_plugins.silero
sys.modules['livekit.plugins.liveavatar'] = mock_plugins.liveavatar

# Mock app submodules
mock_app = MagicMock()
mock_app.utils = MagicMock()
mock_app.config = MagicMock()
mock_app.services = MagicMock()

sys.modules['app'] = mock_app
sys.modules['app.utils'] = mock_app.utils
sys.modules['app.config'] = mock_app.config
sys.modules['app.services'] = mock_app.services

# Real exceptions for mocking
class AgentError(Exception):
    pass

class ConfigurationError(Exception):
    pass

class ServiceError(Exception):
    pass

# Assign exceptions to mocks
mock_exceptions = MagicMock()
mock_exceptions.AgentError = AgentError
mock_exceptions.ConfigurationError = ConfigurationError
mock_exceptions.ServiceError = ServiceError
sys.modules['app.utils.exceptions'] = mock_exceptions

# Function to safely mock complex paths
def mock_submodule(path):
    m = sys.modules.get(path)
    if not m:
        m = MagicMock()
        sys.modules[path] = m
    return m

mock_booking = mock_submodule('app.services.booking_service')
mock_booking.BookingService = MagicMock()
mock_submodule('app.services.application_form_service')
mock_submodule('app.services.evaluation_service')
mock_submodule('app.services.transcript_storage_service')
mock_submodule('app.services.system_instructions_service')
mock_submodule('app.services.transcript_storage_wrapper')
mock_submodule('app.services.candidate_profile')
mock_submodule('app.services.history_managed_llm_wrapper')
mock_submodule('app.services.plugin_service')
mock_submodule('app.services.transcript_service')

sys.modules['app.utils.logger'] = MagicMock()
sys.modules['app.utils.datetime_utils'] = MagicMock()

# Ensure get_logger returns a mock
sys.modules['app.utils.logger'].get_logger.return_value = MagicMock()

# Ensure get_now_ist returns a datetime-like object or mock with strftime
from datetime import datetime
mock_now = MagicMock(spec=datetime)
mock_now.strftime.return_value = "2026-03-14 (current year 2026)"
sys.modules['app.utils.datetime_utils'].get_now_ist.return_value = mock_now

# Mock external dependencies often imported
sys.modules['elevenlabs'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['heygen_live_avatar'] = MagicMock()
