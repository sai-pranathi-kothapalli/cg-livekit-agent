"""
Data channel handlers for code-submission, monitoring, code-snapshot, code-idle.
"""

import asyncio
import json

from livekit import rtc

from app.utils.logger import get_logger  # type: ignore
from app.utils.datetime_utils import get_now_ist # type: ignore
from services.time_context_llm_wrapper import generate_reply_with_instructions
from services import interview_state

logger = get_logger(__name__)


def _extract_verdict_from_response(content: str) -> str:
    """
    Extract verdict (Correct, Partially Correct, Wrong) from LLM response.
    """
    content_lower = content.lower()
    
    # Look for explicit verdict statements
    if any(phrase in content_lower for phrase in ['correct', 'works correctly', 'is correct', 'solution is correct']):
        if any(phrase in content_lower for phrase in ['partially', 'mostly', 'almost', 'edge case', 'misses']):
            return "Partially Correct"
        return "Correct"
    elif any(phrase in content_lower for phrase in ['wrong', 'incorrect', 'does not work', 'fails', 'error']):
        return "Wrong"
    elif any(phrase in content_lower for phrase in ['partially', 'mostly', 'almost']):
        return "Partially Correct"
    
    # Default fallback
    return "Pending Evaluation"


def setup_data_handlers(room: rtc.Room, session, logger_instance=None) -> None:
    """
    Register data_received handler for code-submission, monitoring, code-observation.
    """
    log = logger_instance or logger

    @room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        topic = data.topic
        if topic == "code-submission":
            _handle_code_submission(data, session, log)
        elif topic == "monitoring":
            _handle_monitoring(data, session, log)
        elif topic == "code-observation":
            _handle_code_observation(data, session, log)
        elif topic == "code-snapshot":
            _handle_code_snapshot(data, session, log)
        elif topic == "code-idle":
            _handle_code_idle(data, session, log)


def _handle_code_observation(data: rtc.DataPacket, session, log) -> None:
    """Handle 8s debounce coding observation."""
    try:
        payload = json.loads(data.data)
        current_code = payload.get('current_code', '')
        question = payload.get('question', 'N/A')
        language = payload.get('language', 'N/A')

        log.info(f"👀 [CODE OBSERVATION] Candidate code update ({len(current_code.splitlines())} lines)")

        observation_context = (
    f"[INTERNAL — OBSERVATION PHASE]\n"
    f"You are observing the candidate while they are coding.\n\n"
    f"Question: {question}\n"
    f"Language: {language}\n"
    f"Current Code Progress:\n{current_code}\n\n"

    f"Your goal is to understand the candidate's approach.\n"
    f"Try to identify what strategy they are using "
    f"(e.g., brute force, hashmap, recursion, two pointers, dynamic programming).\n\n"

    f"STRICT RULES:\n"
    f"1. Do NOT reveal the correct solution.\n"
    f"2. Do NOT say the code is wrong or incomplete.\n"
    f"3. Do NOT read the code line-by-line aloud.\n"
    f"4. Ask ONE thoughtful question about their approach.\n"
    f"5. Keep it short and natural.\n\n"

    f"Examples of good questions:\n"
    f"- 'What made you choose this approach?'\n"
    f"- 'What would be the time complexity of this solution?'\n"
    f"- 'Do you think this could be optimized further?'\n"
    f"- 'Why did you choose this data structure?'\n\n"

    f"Speak like a real interviewer observing the coding process.\n"
    f"Then stay silent again.\n"
    f"[END INTERNAL]"
)

        async def _trigger_observation():
            try:
                await generate_reply_with_instructions(session, instructions=observation_context)
            except Exception as e:
                log.error(f"Failed observation reply: {e}")

        asyncio.create_task(_trigger_observation())
    except Exception as e:
        log.error(f"Error handling code-observation: {e}", exc_info=True)


def _handle_code_submission(data: rtc.DataPacket, session, log) -> None:
    """Handle final code submission with evaluation phase rules."""
    try:
        payload = json.loads(data.data)
        log.info(f"📥 [CODE SUBMISSION] Final submission received")

        candidate_code = payload.get('code', '')
        time_taken = payload.get('time_taken_seconds', 0)
        obs_count = payload.get('observation_count', 0)
        language = payload.get('language', 'N/A')
        question = payload.get('question', 'N/A')
        execution_output = payload.get('executionOutput', 'N/A')

        # Determine evaluation result (logic moved to LLM but we store metadata)
        # We'll let the evaluation service handle the final 'correct/wrong' status from transcript,
        # but we persist the submission data now.
        interview_state.add_code_submission(
            code=candidate_code,
            question=question,
            ai_verdict="Pending Evaluation",
            execution_output=execution_output,
            timestamp=get_now_ist().isoformat(),
            language=language,
            time_taken_seconds=time_taken,
            observation_count=obs_count
        )

        evaluation_context = (
            f"[INTERNAL — EVALUATION PHASE]\n"
            f"The candidate has CLICKED SUBMIT. Your role is now a professional evaluator.\n"
            f"Question: {question}\n"
            f"Language: {language}\n"
            f"Time Taken: {time_taken} seconds\n"
            f"Observations during coding: {obs_count}\n"
            f"Submitted Code:\n{candidate_code}\n\n"
            f"Execution Output: {execution_output}\n\n"
            f"Use the execution output to determine correctness:\n"
            f"- If output matches expected → Correct\n"
            f"- If output is wrong/error → Wrong or Partial\n"
            f"- If output is 'N/A' → evaluate code visually\n\n"
            f"STRICT RULES:\n"
            f"1. Evaluate correctness: Correct, Partially Correct (misses edge cases), or Wrong.\n"
            f"2. NEVER read the code aloud or say 'I see you wrote...'.\n"
            f"3. If fast (<60s) for medium problem, internally note suspicious speed.\n"
            f"4. Tell them clearly if it works or where it fails (e.g., 'This works for basic cases, but what about negatives?').\n"
            f"5. Ask exactly ONE follow-up probing question to start the Probing Phase.\n"
            f"[END INTERNAL]"
        )

        async def _trigger_evaluation():
            try:
                await generate_reply_with_instructions(session, instructions=evaluation_context)
                
                # Wait a moment for the response to be fully generated and added to chat context
                await asyncio.sleep(2)
                
                # Extract verdict from the LLM's response
                try:
                    if hasattr(session, 'chat_ctx') and hasattr(session.chat_ctx, 'messages'):
                        messages = session.chat_ctx.messages
                        # Find the last assistant message (the evaluation response)
                        for msg in reversed(messages):
                            role = getattr(msg, 'role', None)
                            if role == 'assistant' or (hasattr(msg, 'content') and getattr(msg, 'content', '')):
                                content = getattr(msg, 'content', '') or ''
                                # Extract verdict from the response
                                verdict = _extract_verdict_from_response(content)
                                if verdict:
                                    interview_state.update_latest_ai_verdict(verdict)
                                    log.info(f"✅ Updated ai_verdict: {verdict}")
                                break
                except Exception as e:
                    log.warning(f"Could not extract verdict from LLM response: {e}")
            except Exception as e:
                log.error(f"Failed evaluation reply: {e}")

        asyncio.create_task(_trigger_evaluation())
    except Exception as e:
        log.error(f"Error handling code-submission: {e}", exc_info=True)


def _handle_monitoring(data: rtc.DataPacket, session, log) -> None:
    """Handle monitoring alerts (multiple people, candidate struggling)."""
    try:
        payload = json.loads(data.data)
        alert_type = payload.get('alertType')
        message = payload.get('message', 'N/A')
        log.warning(f"🚨 [MONITORING ALERT] {alert_type} from {data.participant.identity}")

        # Persist for evaluation
        interview_state.add_violation(
            alert_type=alert_type,
            message=message,
            timestamp=get_now_ist().isoformat()
        )

        instruction = None
        if alert_type == "multiple_people_detected":
            instruction = "[SYSTEM: Multiple people detected in candidate's camera. Address this firmly but professionally. Ask if someone is helping them.]"
        elif alert_type == "candidate_struggling":
            emotion = payload.get('emotion', 'unknown')
            instruction = f"[SYSTEM: Candidate appears {emotion} or stressed. Be encouraging and offer a small hint if they seem stuck on the current question.]"

        if instruction:
            async def _trigger_monitoring_reply():
                try:
                    await generate_reply_with_instructions(session, instructions=instruction)
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
            f"lines={len(code_snippet.splitlines())} | question={str(question)}"
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
                await generate_reply_with_instructions(session, instructions=instruction)
            except Exception as e:
                log.error(f"Failed to trigger code idle reply: {e}")
        asyncio.create_task(_trigger_idle_reply())
    except Exception as e:
        log.error(f"Error handling code-idle data: {e}", exc_info=True)
