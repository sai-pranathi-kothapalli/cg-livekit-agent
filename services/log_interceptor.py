"""
Log Interceptor

Intercepts LiveKit agent logs to extract STT timing information.
"""

import json
import logging
import re
from agents.utils import logger, log_stt_complete


class STTLogInterceptor(logging.Handler):
    """
    Custom log handler that intercepts LiveKit's STT logs.
    
    Captures "received user transcript" logs and extracts timing info.
    """
    
    def __init__(self):
        super().__init__()
        self.setLevel(logging.DEBUG)
    
    def emit(self, record):
        """Process log record and extract STT timing"""
        try:
            message = record.getMessage()
            
            # Look for LiveKit's "received user transcript" log
            if "received user transcript" in message.lower():
                # Try to extract JSON data from next line or same message
                self._extract_and_log_transcript(message)
                
        except Exception:
            # Silently ignore errors to avoid breaking logging
            pass
    
    def _extract_and_log_transcript(self, message: str):
        """Extract transcript and timing from log message"""
        try:
            # Look for JSON in the message
            json_match = re.search(r'\{.*"user_transcript".*\}', message, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                transcript = data.get('user_transcript', '')
                delay = data.get('transcript_delay', 0)
                
                if transcript and delay:
                    log_stt_complete(transcript, delay)
                    
        except Exception as e:
            logger.debug(f"Could not extract transcript from log: {e}")


def install_stt_interceptor():
    """
    Install the STT log interceptor on LiveKit agents logger.
    
    Call this once during agent initialization.
    """
    # Get LiveKit's agents logger
    lk_logger = logging.getLogger('livekit.agents')
    
    # Add our interceptor
    interceptor = STTLogInterceptor()
    lk_logger.addHandler(interceptor)
    
    logger.info("✅ STT log interceptor installed")
