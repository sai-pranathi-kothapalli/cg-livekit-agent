"""
Output Sanitizer

Strips internal context (MINUTE., Phase:, etc.) and early-goodbye phrases from
the LLM response stream so they are never spoken or shown to the candidate.
"""

import re
from typing import Any
from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)

# Patterns that indicate internal context — strip any line containing these (hardened)
INTERNAL_LINE_PATTERNS = re.compile(
    r"MINUTE\.\s*\d+/\d+|"
    r"Phase:\s*\w+|"
    r"Phase\s+window|"
    r"Phase\s+remaining|"
    r"Interview\s+remaining|"
    r"Time\s+remaining\s*:\s*\d+|"
    r"Time\s+remaining\s*\d+|"
    r"Focus\s*:\s*\w+|"
    r"Focus\s+\w+|"
    r"\[INTERNAL\s*[^\]]*|"
    r"\[END\s+INTERNAL\s+CONTEXT[^\]]*\]|"
    r"END\s+INTERNAL\s+CONTEXT",
    re.IGNORECASE,
)

# Block from start until (and including) "[END INTERNAL CONTEXT ... ]" (hardened)
STRIP_UNTIL_MARKER = re.compile(
    r"^.*?\[END\s+INTERNAL\s+CONTEXT[^\]]*\]\s*",
    re.DOTALL | re.IGNORECASE,
)

# Early conclusion phrases — if we see these and END_INTERVIEW was not sent, we could strip (optional)
EARLY_GOODBYE_PHRASES = [
    "thank you for your time today",
    "we will be in touch with next steps",
    "all the best",
    "that concludes our interview",
]


def remove_internal_blocks(text: str) -> str:
    """
    Remove all [INTERNAL...]...[END INTERNAL CONTEXT...] blocks (hardened regex).
    Prevents prompt leakage: internal notes must never be in user-visible or model-visible dialogue.
    """
    if not text or not isinstance(text, str):
        return text
    return re.sub(
        r"\[INTERNAL.*?END\s+INTERNAL\s+CONTEXT[^\]]*\]",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )


def sanitize_agent_response(text: str) -> str:
    """
    Remove internal context and optionally early-goodbye blocks from agent text.
    Use for transcript display/DB and for any single-message sanitization.
    """
    if not text or not text.strip():
        return text
    # 1) Remove [INTERNAL ... END INTERNAL CONTEXT ... ] blocks first
    out = remove_internal_blocks(text)
    # 2) Strip block from start until [END INTERNAL CONTEXT ... ] (if pattern differs)
    out = STRIP_UNTIL_MARKER.sub("", out)
    # 2) Drop any remaining lines that look like internal context
    lines = out.split("\n")
    kept = []
    for line in lines:
        if INTERNAL_LINE_PATTERNS.search(line):
            continue
        kept.append(line)
    out = "\n".join(kept)
    return out.strip()


def _make_chunk_with_content(content: str, template_chunk: Any) -> Any:
    """Build a chunk with modified content — mutate original where possible."""
    try:
        delta = getattr(template_chunk, "delta", None)
        if delta is not None and hasattr(delta, "content"):
            try:
                delta.content = content
                return template_chunk  # return original mutated chunk
            except (AttributeError, TypeError):
                pass
        # Try direct content attribute
        if hasattr(template_chunk, "content"):
            try:
                template_chunk.content = content
                return template_chunk
            except (AttributeError, TypeError):
                pass
        # Try text attribute
        if hasattr(template_chunk, "text"):
            try:
                template_chunk.text = content
                return template_chunk
            except (AttributeError, TypeError):
                pass
    except Exception:
        pass
    # Last resort — return original chunk unmodified
    # (better than returning incompatible type)
    return template_chunk


class OutputSanitizerState:
    """Per-stream state for sanitizing LLM output."""

    # If we've buffered this many chars and still no marker, assume no marker and sanitize + passthrough
    MAX_BUFFER_BEFORE_PASSTHROUGH = 800

    def __init__(self):
        self.buffer = ""
        self.passthrough = False

    def add(self, chunk_text: str) -> None:
        if self.passthrough:
            return
        self.buffer += chunk_text

    def should_passthrough(self) -> bool:
        return self.passthrough

    def take_after_marker(self) -> str:
        """If buffer contains [END INTERNAL CONTEXT ... ], return content after it and set passthrough."""
        if "[END INTERNAL CONTEXT" not in self.buffer:
            # Fallback: if buffer is very large with no closing marker, the [INTERNAL] block
            # never closed (e.g. model truncated output mid-block). DISCARD the buffered
            # content entirely — never sanitize-and-passthrough, because sanitization may
            # be incomplete and partial internal text would leak to TTS / transcript.
            if len(self.buffer) >= self.MAX_BUFFER_BEFORE_PASSTHROUGH:
                logger.warning(
                    "[OutputSanitizer] Buffer reached %d chars with no [END INTERNAL CONTEXT] "
                    "marker — discarding buffered content entirely to prevent context leakage.",
                    len(self.buffer),
                )
                self.buffer = ""
                self.passthrough = True
                return ""  # Return empty: nothing reaches TTS or transcript from this block.
            return ""
        idx = self.buffer.find("[END INTERNAL CONTEXT")
        end = self.buffer.find("]", idx) + 1
        if end <= 0:
            return ""
        after = self.buffer[end:].lstrip()
        self.buffer = ""
        self.passthrough = True
        # Sanitize the content after marker to catch any remaining internal text
        return sanitize_agent_response(after)

    def take_buffer_as_empty(self) -> bool:
        """Return True if we should emit empty (drop) for current buffer (all internal)."""
        if not self.buffer.strip():
            return True
        # Consider entire buffer internal if it's a single line matching internal
        line = self.buffer.split("\n")[0]
        return bool(INTERNAL_LINE_PATTERNS.search(line))

    def flush_remaining(self) -> str:
        """On stream end: sanitize any remaining buffer and return."""
        if self.passthrough or not self.buffer:
            return ""
        out = sanitize_agent_response(self.buffer)
        self.buffer = ""
        return out
