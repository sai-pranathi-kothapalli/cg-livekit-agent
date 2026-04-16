"""
Interview finalization - update booking status and create evaluation.
"""

from typing import Optional, Any, Dict

from app.utils.datetime_utils import get_now_ist  # type: ignore
from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


async def finalize_interview(
    booking_token: Optional[str],
    room_name: str,
    interview_start_time: Any,
    plugins: Dict[str, Any],
    config: Any
) -> None:
    """
    Finalize interview: update status and create evaluation.
    This is called in a finally block to ensure it always runs.
    """
    logger.info("Step 8: Finalizing interview...")
    print("Step 8: Finalizing interview...", flush=True)

    # Update booking status to completed if not already done
    if booking_token:
        try:
            from app.services.booking_service import BookingService  # type: ignore
            booking_service = BookingService(config)
            booking_service.update_booking_status(booking_token, "completed")
            logger.info(f"✅ [FINALIZE] Updated booking status to 'completed'")
        except Exception as e:
            logger.warning(f"⚠️  [FINALIZE] Failed to update booking status: {e}")

    # Create evaluation
    logger.info("Step 8b: Creating interview evaluation...")
    print("Step 8b: Creating interview evaluation...", flush=True)
    try:
        if booking_token:
            from app.services.evaluation_service import EvaluationService  # type: ignore
            from app.services.transcript_storage_service import TranscriptStorageService  # type: ignore

            evaluation_service = EvaluationService(config)
            transcript_service = TranscriptStorageService(config)

            # Get transcript
            transcript = transcript_service.get_transcript(booking_token)

            # Calculate duration
            duration_minutes = None
            if interview_start_time:
                duration_minutes = int((get_now_ist() - interview_start_time).total_seconds() / 60)

            # Extract token usage from LLM timing wrapper
            token_usage = None
            try:
                llm = plugins.get("llm") if plugins else None
                if llm:
                    llm_type = type(llm).__name__
                    logger.info(f"📊 [FINALIZE] Extracting usage from LLM type: {llm_type}")

                    # 1. Check for wrapped chat (TimingLLMWrapper) on .chat attribute
                    if hasattr(llm, "chat") and hasattr(llm.chat, "get_total_usage"):
                        token_usage = llm.chat.get_total_usage()
                        logger.info(f"📊 [FINALIZE] Token usage from llm.chat: {token_usage}")

                    # 2. Fallback: Check if the LLM object itself has get_total_usage
                    elif hasattr(llm, "get_total_usage"):
                        token_usage = llm.get_total_usage()
                        logger.info(f"📊 [FINALIZE] Token usage from llm object: {token_usage}")

                    if not token_usage:
                        chat_attr = getattr(llm, "chat", None)
                        chat_type = type(chat_attr).__name__ if chat_attr else "None"
                        logger.warning(f"⚠️  [FINALIZE] Token usage NOT found! llm_type={llm_type}, chat_type={chat_type}")
                else:
                    logger.warning(f"⚠️  [FINALIZE] LLM plugin not found in plugins dict (keys={list(plugins.keys()) if plugins else 'None'})")
            except Exception as e:
                logger.warning(f"⚠️  [FINALIZE] Failed to extract token usage: {e}", exc_info=True)

            # Get interview state (violations, code submissions)
            try:
                from services import interview_state
                session_state = interview_state.get_state()
                logger.info(f"📊 [FINALIZE] Retrieved session state: {len(session_state.get('violations', []))} violations, {len(session_state.get('code_submissions', []))} code submissions")
                
                # Merge with any existing interview_state if needed, though usually this IS the state
                interview_state_data = session_state
            except Exception as e:
                logger.warning(f"⚠️  [FINALIZE] Failed to retrieve session state: {e}")
                interview_state_data = None

            # Create evaluation
            evaluation_id = await evaluation_service.calculate_evaluation_from_transcript(
                booking_token=booking_token,
                room_name=room_name,
                transcript=transcript,
                token_usage=token_usage,
                interview_state=interview_state_data,
            )
            
            # Clear state to prevent leaks into next session in same process (if re-used)
            try:
                from services import interview_state
                interview_state.clear_state()
            except:
                pass

            if evaluation_id:
                logger.info(f"✅ [FINALIZE] Evaluation created: {evaluation_id}")
                print(f"✅ [FINALIZE] Evaluation created: {evaluation_id}", flush=True)
            else:
                logger.warning("⚠️  [FINALIZE] Failed to create evaluation")
        else:
            logger.warning("⚠️  [FINALIZE] No booking token available, skipping evaluation creation")
    except Exception as e:
        logger.error(f"❌ [FINALIZE] CRITICAL - Evaluation creation failed for booking {booking_token}: {e}", exc_info=True)
        print(f"❌ [FINALIZE] CRITICAL - Evaluation creation failed: {e}", flush=True)
