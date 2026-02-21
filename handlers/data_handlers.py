"""
Data channel handlers for code-submission, monitoring, code-snapshot, code-idle.
"""

import asyncio
import json

from livekit import rtc

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


def setup_data_handlers(room: rtc.Room, session, logger_instance=None) -> None:
    """
    Register data_received handler for code-submission, monitoring, code-snapshot, code-idle.
    
    Args:
        room: LiveKit room to attach handler to
        session: AgentSession for generate_reply
        logger_instance: Optional logger (defaults to module logger)
    """
    log = logger_instance or logger

    @room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        if data.topic == "code-submission":
            _handle_code_submission(data, session, log)
        elif data.topic == "monitoring":
            _handle_monitoring(data, session, log)
        elif data.topic == "code-snapshot":
            _handle_code_snapshot(data, session, log)
        elif data.topic == "code-idle":
            _handle_code_idle(data, session, log)


def _handle_code_submission(data: rtc.DataPacket, session, log) -> None:
    """Handle code submission from candidate."""
    try:
        payload = json.loads(data.data)
        log.info(f"📥 [CODE SUBMISSION] Received from {data.participant.identity}")

        candidate_code = payload.get('code', '')
        submission_context = (
            f"\n\n[SYSTEM: Candidate has submitted code for analysis]\n"
            f"Problem: {payload.get('question', 'N/A')}\n"
            f"Language: {payload.get('language', 'N/A')}\n"
            f"--- CANDIDATE'S CODE ---\n{candidate_code}\n--- END CODE ---\n"
            f"Execution Output: {payload.get('executionOutput', 'N/A')}\n"
            f"AI Analysis Verdict: {payload.get('aiAnalysis', 'N/A')}\n"
            f"CRITICAL: You MUST read and analyze the candidate's code above. Discuss specific lines, logic, and implementation. "
            f"Ask follow-up questions anchored to their actual code. Provide specific feedback as per your role."
        )

        async def _trigger_reply():
            try:
                log.info("🧪 Triggering AI response for code submission...")
                await session.generate_reply(instructions=submission_context)
            except Exception as reply_err:
                log.error(f"Failed to trigger code submission reply: {reply_err}")

        asyncio.create_task(_trigger_reply())
    except Exception as e:
        log.error(f"Error handling code-submission data: {e}", exc_info=True)


def _handle_monitoring(data: rtc.DataPacket, session, log) -> None:
    """Handle monitoring alerts (multiple people, candidate struggling)."""
    try:
        payload = json.loads(data.data)
        alert_type = payload.get('alertType')
        log.warning(f"🚨 [MONITORING ALERT] {alert_type} from {data.participant.identity}")

        instruction = None
        if alert_type == "multiple_people_detected":
            instruction = "[SYSTEM: Multiple people detected in candidate's camera. Address this firmly but professionally. Ask if someone is helping them.]"
        elif alert_type == "candidate_struggling":
            emotion = payload.get('emotion', 'unknown')
            instruction = f"[SYSTEM: Candidate appears {emotion} or stressed. Be encouraging and offer a small hint if they seem stuck on the current question.]"

        if instruction:
            async def _trigger_monitoring_reply():
                try:
                    await session.generate_reply(instructions=instruction)
                except Exception as e:
                    log.error(f"Failed to trigger monitoring reply: {e}")
            asyncio.create_task(_trigger_monitoring_reply())
    except Exception as e:
        log.error(f"Error handling monitoring alert: {e}")


def _handle_code_snapshot(data: rtc.DataPacket, session, log) -> None:
    """Handle code snapshot (every 15s while typing)."""
    try:
        payload = json.loads(data.data)
        log.info(f"📸 [CODE SNAPSHOT] Received from {data.participant.identity}")

        code_snippet = payload.get('code', '')
        question = payload.get('question', 'N/A')
        language = payload.get('language', 'N/A')

        code_lower = code_snippet.lower()
        observations = []

        if 'for' in code_lower or 'while' in code_lower:
            observations.append("using a loop")
        if 'if' in code_lower or 'elif' in code_lower or 'else' in code_lower:
            observations.append("using conditionals")
        if 'def' in code_lower or 'function' in code_lower or 'class' in code_lower:
            observations.append("defining functions/classes")
        if 'return' in code_lower:
            observations.append("handling return values")
        if 'import' in code_lower or 'require' in code_lower or '#include' in code_lower:
            observations.append("importing libraries")

        if observations:
            observation_text = " and ".join(observations)
            instruction = (
                f"[SYSTEM: Candidate is actively coding. Here is their current code:\n---\n{code_snippet}\n---\n"
                f"Provide brief, encouraging feedback about what they've written. Reference specific parts if helpful. 1-2 sentences max.]\n"
                f"I can see you're {observation_text} — why did you choose that approach? Keep going!"
            )
        else:
            instruction = (
                f"[SYSTEM: Candidate is actively coding. Here is their current code:\n---\n{code_snippet}\n---\n"
                f"Provide brief encouragement. Reference what they've written if helpful. 1 sentence max.]\n"
                f"I can see you're working on the solution — keep going!"
            )

        async def _trigger_snapshot_reply():
            try:
                await session.generate_reply(instructions=instruction)
            except Exception as e:
                log.error(f"Failed to trigger code snapshot reply: {e}")
        asyncio.create_task(_trigger_snapshot_reply())
    except Exception as e:
        log.error(f"Error handling code-snapshot data: {e}", exc_info=True)


def _handle_code_idle(data: rtc.DataPacket, session, log) -> None:
    """Handle code idle (1min no typing)."""
    try:
        payload = json.loads(data.data)
        log.info(f"⏸️ [CODE IDLE] Received from {data.participant.identity}")

        code_snippet = payload.get('code', '')
        question = payload.get('question', 'N/A')

        instruction = (
            f"[SYSTEM: Candidate has been idle for 1 minute. Their current code:\n---\n{code_snippet}\n---\n"
            f"Offer a hint relevant to their code, or ask if they want to skip. Be supportive. Brief.]\n"
            f"Looks like you're stuck — need a hint, or shall we skip this question and move on?"
        )

        async def _trigger_idle_reply():
            try:
                await session.generate_reply(instructions=instruction)
            except Exception as e:
                log.error(f"Failed to trigger code idle reply: {e}")
        asyncio.create_task(_trigger_idle_reply())
    except Exception as e:
        log.error(f"Error handling code-idle data: {e}", exc_info=True)
