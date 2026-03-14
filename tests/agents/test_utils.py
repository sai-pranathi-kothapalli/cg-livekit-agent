import pytest
import time
from unittest.mock import MagicMock, patch
from agents.utils import PerformanceTimer, get_track_source_name, log_turn_start, log_turn_end, log_stt_complete, log_tts_start

def test_performance_timer_basic():
    """Test basic functionality of PerformanceTimer."""
    with patch('agents.utils.logger') as mock_logger:
        timer = PerformanceTimer("TestOp")
        timer.start()
        mock_logger.info.assert_any_call("⏱️  [TestOp] ⏩ START")
        
        time.sleep(0.01)
        timer.checkpoint("Step1")
        # Verify checkpoint log contains "Step1" and "total"
        args, _ = mock_logger.info.call_args_list[-1]
        assert "Step1" in args[0]
        assert "total" in args[0]
        
        total = timer.end("Final")
        assert total > 0
        args, _ = mock_logger.info.call_args_list[-1]
        assert "COMPLETE" in args[0]
        assert "Final" in args[0]

def test_performance_timer_context_manager():
    """Test PerformanceTimer as a context manager."""
    with patch('agents.utils.logger') as mock_logger:
        with PerformanceTimer("CtxOp") as timer:
            assert timer.name == "CtxOp"
            timer.checkpoint("In")
        
        # Verify both start and end logs were made
        mock_logger.info.assert_any_call("⏱️  [CtxOp] ⏩ START")
        args, _ = mock_logger.info.call_args_list[-1]
        assert "COMPLETE" in args[0]

def test_log_functions():
    """Test simple logging helper functions."""
    with patch('agents.utils.logger') as mock_logger:
        log_turn_start()
        mock_logger.info.assert_any_call("👤 USER TURN START")
        
        log_turn_end(1.5)
        mock_logger.info.assert_any_call("✅ TURN COMPLETE - Total: 1.500s")
        
        log_stt_complete("Hello world", 0.5)
        mock_logger.info.assert_any_call("⏱️  [STT] ✅ Transcript ready in 0.500s")
        
        log_stt_complete("A" * 100, 0.5) # Test truncation
        mock_logger.info.assert_any_call(f"    💬 \"{'A' * 80}...\"")
        
        log_tts_start(120)
        mock_logger.info.assert_any_call("⏱️  [TTS] 🔊 Generating audio for 120 chars...")

def test_performance_timer_edge_cases():
    """Test PerformanceTimer without starting it."""
    with patch('agents.utils.logger') as mock_logger:
        timer = PerformanceTimer("Lazy")
        # Should return silently
        timer.checkpoint("Now")
        assert timer.end() == 0

def test_get_track_source_name_extended():
    """Test edge cases in track source mapping."""
    with patch('agents.utils.logger') as mock_logger:
        # 1. Test unexpected int (covers line 116)
        assert get_track_source_name(99) == "UNKNOWN(99)"
        
        # 2. Test string not in enum map (covers line 126)
        assert get_track_source_name("not_in_map") == "UNKNOWN(not_in_map)"
        
        # 3. Trigger exception by making rtc.TrackSource lookups fail
        # We patch it directly in the module where it's used
        with patch('agents.utils.rtc') as mock_rtc_in_module:
            # Side effect on accessing TrackSource should trigger Exception
            mock_rtc_in_module.TrackSource = MagicMock()
            type(mock_rtc_in_module.TrackSource).SOURCE_MICROPHONE = property(lambda x: 1/0)
            
            assert get_track_source_name("anything") == "UNKNOWN(anything)"
            mock_logger.warning.assert_called()

def test_get_track_source_name_enum():
    """Test actual enum mapping."""
    from livekit import rtc
    # Set up the mock objects that were created in conftest
    rtc.TrackSource.SOURCE_MICROPHONE = "mic_enum"
    rtc.TrackSource.SOURCE_CAMERA = "cam_enum"
    
    # These should match the enum_map in the function
    assert get_track_source_name("mic_enum") == "MICROPHONE"
    assert get_track_source_name("cam_enum") == "CAMERA"
