"""
STT Logger

Intercepts and logs STT transcripts with timing information.
"""

import json
from typing import Any
from agents.utils import logger, log_stt_complete


class STTLogger:
    """
    Logs STT transcripts with timing when they arrive.
    
    This can be used as a wrapper or callback to capture STT events.
    """
    
    @staticmethod
    def log_transcript(transcript_data: dict):
        """
        Log STT transcript with timing.
        
        Args:
            transcript_data: Dict containing 'user_transcript', 'transcript_delay', etc.
        """
        transcript = transcript_data.get('user_transcript', '')
        delay = transcript_data.get('transcript_delay', 0)
        language = transcript_data.get('language', 'unknown')
        
        if transcript:
            log_stt_complete(transcript, delay)
            logger.debug(f"    🌍 Language: {language}")
    
    @staticmethod
    def parse_and_log(log_line: str):
        """
        Parse a log line containing transcript data and log it.
        
        Args:
            log_line: Log line that may contain transcript JSON
        """
        try:
            # Look for JSON in the log line
            if '{' in log_line and 'user_transcript' in log_line:
                json_start = log_line.find('{')
                json_str = log_line[json_start:]
                transcript_data = json.loads(json_str)
                STTLogger.log_transcript(transcript_data)
        except Exception as e:
            logger.debug(f"Could not parse transcript from log: {e}")
