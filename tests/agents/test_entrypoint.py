import pytest
import sys
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.entrypoint import entrypoint
from app.utils.exceptions import AgentError

class MockJob:
    def __init__(self, id="job_123"):
        self.id = id

class MockRoom:
    def __init__(self, name="interview_token123"):
        self.name = name
        self.metadata = '{"booking_token": "token123"}'
        self.remote_participants = {}
        self.local_participant = MagicMock()
        self.isconnected = MagicMock(return_value=True)
        self.disconnect = AsyncMock()

class MockJobContext:
    def __init__(self):
        self.job = MockJob()
        self.room = MockRoom()
        self.connect = AsyncMock()
        self.wait_for_shutdown = AsyncMock()

@pytest.mark.asyncio
async def test_entrypoint_connection_failure():
    """Verify entrypoint re-raises AgentError on connection failure."""
    ctx = MockJobContext()
    ctx.connect.side_effect = Exception("Connection Refused")
    
    with pytest.raises(AgentError):
        await entrypoint(ctx)
    ctx.connect.assert_called_once()

@pytest.mark.asyncio
async def test_entrypoint_basic_initialization():
    """Test entrypoint initialization up to plugin setup."""
    ctx = MockJobContext()
    
    with patch('agents.entrypoint.get_config') as mock_get_config, \
         patch('services.candidate_profile.fetch_candidate_profile', new_callable=AsyncMock) as mock_fetch, \
         patch('app.services.plugin_service.PluginService') as MockPluginSvc:
        
        mock_config = MagicMock()
        mock_config.livekit.agent_name = "Arjun"
        mock_get_config.return_value = mock_config
        mock_fetch.return_value = {"full_name": "John Doe"}
        
        # Stop at plugin initialization to avoid infinite loop or heavy logic
        MockPluginSvc.return_value.initialize_plugins.side_effect = Exception("Stop Here")
        
        with pytest.raises(AgentError):
            await entrypoint(ctx)
            
        ctx.connect.assert_called_once()
        mock_fetch.assert_called()

@pytest.mark.asyncio
async def test_entrypoint_token_extraction_variations():
    """Verify token extraction from various formats."""
    # Test variation 1: interview_<token>
    ctx1 = MockJobContext()
    ctx1.room.name = "interview_abc123"
    
    # Test variation 2: metadata fallback
    ctx2 = MockJobContext()
    ctx2.room.name = "other"
    ctx2.room.metadata = '{"token": "meta_token"}'
    
    with patch('agents.entrypoint.get_config'), \
         patch('app.utils.logger.get_logger'), \
         patch('services.candidate_profile.fetch_candidate_profile', side_effect=Exception("Stop")):
        
        with pytest.raises(AgentError):
            await entrypoint(ctx1)
        
        with pytest.raises(AgentError):
            await entrypoint(ctx2)
