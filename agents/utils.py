"""
Agent Utility Functions

Helper functions for LiveKit agent operations.
"""

from __future__ import annotations

import time
from typing import Union

from livekit import rtc

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class PerformanceTimer:
    """Simple performance timer for tracking pipeline delays"""
    
    def __init__(self, operation_name: str):
        self.name = operation_name
        self.start_time = None
        self.last_checkpoint = None
        
    def start(self):
        """Start the timer"""
        self.start_time = time.perf_counter()
        self.last_checkpoint = self.start_time
        logger.info(f"⏱️  [{self.name}] ⏩ START")
        return self
        
    def checkpoint(self, label: str):
        """Log a checkpoint with elapsed time"""
        if not self.start_time:
            return
            
        now = time.perf_counter()
        since_start = now - self.start_time
        since_last = now - self.last_checkpoint
        self.last_checkpoint = now
        
        logger.info(f"⏱️  [{self.name}] ✓ {label}: +{since_last:.3f}s (total: {since_start:.3f}s)")
        
    def end(self, extra_info: str = ""):
        """End the timer and log total time"""
        if not self.start_time:
            return 0
            
        total = time.perf_counter() - self.start_time
        info_str = f" - {extra_info}" if extra_info else ""
        logger.info(f"⏱️  [{self.name}] 🏁 COMPLETE: {total:.3f}s{info_str}")
        return total
    
    def __enter__(self):
        """Context manager support"""
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.end()
        return False


# Turn boundary logging functions
def log_turn_start():
    """Log the start of a conversation turn with visual separator"""
    logger.info("═" * 60)
    logger.info("👤 USER TURN START")
    logger.info("═" * 60)


def log_turn_end(total_time: float):
    """Log the end of a conversation turn with total time"""
    logger.info("═" * 60)
    logger.info(f"✅ TURN COMPLETE - Total: {total_time:.3f}s")
    logger.info("═" * 60)


def log_stt_complete(transcript: str, delay: float):
    """Log STT completion with transcript preview"""
    logger.info(f"⏱️  [STT] ✅ Transcript ready in {delay:.3f}s")
    # Show transcript (truncate if too long)
    if len(transcript) > 80:
        logger.info(f"    💬 \"{transcript[:80]}...\"")
    else:
        logger.info(f"    💬 \"{transcript}\"")


def log_tts_start(text_length: int):
    """Log TTS generation start"""
    logger.info(f"⏱️  [TTS] 🔊 Generating audio for {text_length} chars...")


def get_track_source_name(source: Union[int, rtc.TrackSource]) -> str:
    """
    Convert track source to readable name.
    
    Args:
        source: Track source (integer or enum)
        
    Returns:
        Human-readable track source name
    """
    # Map integer values to names (LiveKit uses integers: 1=MICROPHONE, 2=CAMERA, etc.)
    source_map = {
        1: "MICROPHONE",
        2: "CAMERA",
        3: "SCREEN_SHARE",
        4: "UNKNOWN"
    }
    
    # Handle integer values
    if isinstance(source, int):
        return source_map.get(source, f"UNKNOWN({source})")
    
    # Handle enum values
    try:
        enum_map = {
            rtc.TrackSource.SOURCE_MICROPHONE: "MICROPHONE",
            rtc.TrackSource.SOURCE_CAMERA: "CAMERA",
            rtc.TrackSource.SOURCE_SCREEN_SHARE: "SCREEN_SHARE",
            rtc.TrackSource.SOURCE_UNKNOWN: "UNKNOWN"
        }
        return enum_map.get(source, f"UNKNOWN({source})")
    except Exception as e:
        logger.warning(f"Error mapping track source: {e}")
        return f"UNKNOWN({source})"

