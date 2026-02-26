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
        execution_output = payload.get('executionOutput', 'N/A')
        ai_verdict = payload.get('aiAnalysis', 'N/A')
        submission_context = (
            # Wrap everything in [INTERNAL] markers so the stream filter strips any echo
            # of this instruction block from the TTS output. The LLM reads and follows these
            # instructions from the system message but must NOT speak them aloud.
            f"[INTERNAL — DO NOT READ ALOUD. DO NOT SPEAK ANY OF THIS TEXT TO THE CANDIDATE. "
            f"These are your private instructions for evaluating the code submission.]\n\n"
            f"[CODE SUBMISSION — OVERRIDE ALL OTHER PHASE INSTRUCTIONS FOR THIS RESPONSE ONLY]\n\n"
            f"The candidate has just submitted their code solution. Regardless of what phase or topic "
            f"was discussed before, your ONLY job for this response is to evaluate the submitted code.\n\n"
            f"Problem: {payload.get('question', 'N/A')}\n"
            f"Language: {payload.get('language', 'N/A')}\n"
            f"--- CANDIDATE'S SUBMITTED CODE ---\n{candidate_code}\n--- END CODE ---\n"
            f"Execution Output: {execution_output}\n"
            f"AI Analysis Verdict: {ai_verdict}\n\n"
            f"YOUR RESPONSE MUST DO THIS IN ORDER:\n"
            f"1. Evaluate correctness FIRST — tell the candidate directly whether their solution is "
            f"correct, partially correct, or incorrect. Reference specific lines or logic in the code. "
            f"If execution output shows errors or wrong output, point that out explicitly "
            f"(e.g. 'Your solution returns X but the expected output is Y because...').\n"
            f"2. Ask exactly ONE probing follow-up question — the most revealing one based on the code:\n"
            f"   - 'Why did you choose this approach?' or 'Why did you use [data structure/algorithm they used]?'\n"
            f"   - 'How does your solution handle [edge case visible in the code]?'\n"
            f"   - 'What is the time and space complexity of your solution?'\n"
            f"   - 'If the input were much larger, would this still be efficient? How would you optimize it?'\n"
            f"   - 'Is there anything in this code you would refactor or improve given more time?'\n"
            f"3. After they answer, ask the next follow-up. One question per turn.\n"
            f"Be direct and professional. Do NOT say 'great attempt' or hedge your evaluation.\n"
            f"[END INTERNAL CONTEXT — respond naturally and evaluate the candidate's code below]"
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
    """Handle code snapshot (every 15s while typing).

    NOTE: We do NOT trigger a generate_reply on every snapshot — that would
    interrupt the candidate mid-coding every 15 seconds. Instead, we just log
    the code progress so the agent can reference it if it needs to speak.
    The agent will naturally engage when the candidate pauses or submits.
    """
    try:
        payload = json.loads(data.data)
        code_snippet = payload.get('code', '')
        question = payload.get('question', 'N/A')
        language = payload.get('language', 'N/A')
        log.info(
            f"📸 [CODE SNAPSHOT] Candidate is coding | lang={language} | "
            f"lines={len(code_snippet.splitlines())} | question={str(question)[:60]}"
        )
        # No generate_reply here — let the candidate code without interruption.
        # The agent will speak only when the candidate pauses (code-idle) or submits (code-submission).
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
