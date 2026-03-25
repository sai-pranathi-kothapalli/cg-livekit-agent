"""
Interview time loop — monitors duration, sends time updates, triggers wrap-up and closing.
Timer starts when candidate sends first message (interview_started_at set in TimeContextLLMWrapper).
All timing uses utils.interview_timer; no phase state machine.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from livekit.agents import JobContext

from app.utils.datetime_utils import get_now_ist  # type: ignore
from app.utils.logger import get_logger  # type: ignore
from utils.interview_timer import get_time_remaining, get_interview_focus  # type: ignore
from services.time_context_llm_wrapper import generate_reply_with_instructions

logger = get_logger(__name__)

MIN_ACTUAL_DURATION_MINUTES = 30


async def run_interview_time_loop(
    ctx: JobContext,
    session,
    interview_start_time: datetime,
    interview_duration_minutes: int,
    scheduled_end_time: Optional[datetime],
    booking_token: Optional[str],
    room_name: str,
    plugins: Dict[str, Any],
    config: Any,
    slot_start_ist: Optional[datetime] = None,
    scheduled_duration_minutes: Optional[int] = None,
    requires_coding: bool = False,
) -> None:
    """
    Run the main time loop until interview ends or room disconnects.
    Timer starts when candidate sends first message (interview_started_at set in TimeContextLLMWrapper).
    Uses centralized get_time_remaining and get_interview_focus; no phase state machine.
    Always calls finalize_interview in finally block.
    """
    conclude_instruction_sent = False
    closing_triggered = False
    interview_time_limit_reached = False
    last_time_update = None
    resolved_start_time = interview_start_time
    resolved_duration_minutes = interview_duration_minutes
    resolved_end_time: Optional[datetime] = None
    candidate_joined = False

    try:
        while ctx.room.isconnected() and not interview_time_limit_reached:
            current_time_ist = get_now_ist()

            if not candidate_joined:
                if len(ctx.room.remote_participants) > 0:
                    candidate_join_time = current_time_ist
                    # Coerce to int (entrypoint may pass int/float; DB might be float)
                    duration_int = int(interview_duration_minutes)
                    actual_duration = max(duration_int, MIN_ACTUAL_DURATION_MINUTES)
                    resolved_duration_minutes = actual_duration
                    # Set base_template based on actual resolved duration (not original)
                    base_template = "45" if actual_duration >= 43 else "30"
                    try:
                        from services.session_time_store import set_store_duration_only
                        from app.services.history_managed_llm_wrapper import reset_questions_asked  # type: ignore
                        set_store_duration_only(actual_duration, base_template, requires_coding)
                        reset_questions_asked()
                    except Exception as e:
                        logger.warning("Could not set session time store: %s", e)
                    resolved_start_time = None
                    resolved_end_time = None
                    last_time_update = candidate_join_time
                    candidate_joined = True
                    logger.info(
                        "⏰ Candidate joined: duration=%s min (start_time will be set on first message).",
                        actual_duration,
                    )
                    print(
                        f"⏰ Candidate joined — timer will start on first message (safe_duration={actual_duration} min)",
                        flush=True,
                    )
                else:
                    await asyncio.sleep(2)
                    continue

            if candidate_joined and resolved_start_time is None:
                try:
                    from services.session_time_store import get_store
                    store_start, store_dur, _, _ = get_store()
                    if store_start is not None and store_dur is not None:
                        resolved_start_time = store_start
                        # Ensure int (store may have float if it came from DB)
                        resolved_duration_minutes = max(int(store_dur), MIN_ACTUAL_DURATION_MINUTES)
                        # Update base_template based on resolved duration
                        base_template = "45" if resolved_duration_minutes >= 43 else "30"
                        resolved_end_time = store_start + timedelta(minutes=resolved_duration_minutes)
                        logger.info(
                            "⏰ Interview started at first message: start=%s, duration=%s min, end=%s",
                            resolved_start_time,
                            resolved_duration_minutes,
                            resolved_end_time,
                        )
                except Exception as e:
                    logger.debug("Could not resolve start time from store: %s", e)

            if resolved_start_time is None:
                await asyncio.sleep(2)
                continue

            remaining_min = get_time_remaining(resolved_start_time, resolved_duration_minutes, now=current_time_ist)
            focus = get_interview_focus(remaining_min, total_duration=resolved_duration_minutes)
            logger.info("Time remaining: %s min | Focus: %s", remaining_min, focus)

            # If focus is conclude, treat as time limit reached (sync conclude focus with time_limit_reached)
            if focus == "conclude" and not closing_triggered:
                time_limit_reached = True
                logger.info("⏰ Focus is 'conclude' — treating as time limit reached")

            time_remaining_minutes = float(remaining_min)
            # Use resolved_end_time as authoritative when set; only then use remaining_min/elapsed.
            # This avoids premature end when remaining_min <= 0 due to any calc/timezone issue.
            if resolved_end_time is not None:
                time_limit_reached = current_time_ist >= resolved_end_time
                if time_limit_reached:
                    logger.info("⏰ Interview time limit reached (true end: %s)", resolved_end_time)
            else:
                elapsed_minutes = (current_time_ist - resolved_start_time).total_seconds() / 60
                time_limit_reached = elapsed_minutes >= resolved_duration_minutes
                if time_limit_reached:
                    logger.info("⏰ Interview duration limit reached (%s minutes elapsed)", resolved_duration_minutes)

            if last_time_update is not None and resolved_end_time is not None:
                time_since_last_update = (current_time_ist - last_time_update).total_seconds()
                if time_since_last_update >= 10:
                    try:
                        time_update_message = json.dumps({
                            "type": "time_remaining",
                            "time_remaining_minutes": max(0, time_remaining_minutes),
                        }).encode("utf-8")
                        await ctx.room.local_participant.publish_data(
                            time_update_message,
                            topic="lk-chat",
                            reliable=False,
                        )
                        last_time_update = current_time_ist
                        logger.debug("⏰ Sent time remaining update: %.1f minutes", time_remaining_minutes)
                    except Exception as e:
                        logger.debug("⚠️  Failed to send time update: %s", e)

            # Scale soft wrap threshold: 1 min for 30-min interviews, 2 min for 45-min interviews
            soft_wrap_threshold = max(1, round(resolved_duration_minutes / 30))  # 1 for 30min, 2 for 45min
            if resolved_end_time is not None and not conclude_instruction_sent and 0 < remaining_min <= soft_wrap_threshold:
                # Only send wrap-up when we're near the real end (avoids firing on timezone/calc glitches).
                elapsed_so_far = (current_time_ist - resolved_start_time).total_seconds() / 60
                if elapsed_so_far >= (resolved_duration_minutes - 3):
                    conclude_instruction_sent = True
                    try:
                        await generate_reply_with_instructions(
                            session, 
                            instructions=(
                                "The interview is almost over (approximately 1 minute remaining). "
                                "Gently pivot from technical questioning to a soft wrap-up. "
                                "Ask the candidate if they have any final questions for you about the role or the team. "
                                "Begin your closing arc, maintaining a friendly and professional tone. "
                                "Do NOT say goodbye yet, just signal the transition to the final stage."
                            )
                        )
                        logger.info("✅ Sent END_SOFT_WRAP (~1 min left)")
                        print("⏰ Conclude instruction sent (~1 min left)", flush=True)
                    except Exception as e:
                        logger.warning("⚠️  Could not send conclude instruction: %s", e)

            trigger_closing_now = time_limit_reached and not closing_triggered
            if trigger_closing_now:
                closing_triggered = True
                interview_time_limit_reached = True
                elapsed_minutes = (current_time_ist - resolved_start_time).total_seconds() / 60
                logger.info("⏰ Full interview duration reached - ending interview gracefully")
                print("⏰ Full duration reached - ending interview", flush=True)

                try:
                    await generate_reply_with_instructions(session, instructions="END_INTERVIEW")
                    
                    # Dynamic wait for TTS to finish speaking
                    logger.info("⏳ Waiting for agent to finish closing statement...")
                    max_wait = 30  # 30 seconds max
                    waited = 0
                    while waited < max_wait:
                        # Agent state 'listening' means it finished speaking and is waiting for user
                        if session.agent_state == "listening":
                            logger.info("✅ Agent finished speaking closing statement")
                            break
                        await asyncio.sleep(1)
                        waited += 1
                    
                    if waited >= max_wait:
                        logger.warning("⚠️  Timed out waiting for agent to finish speaking closing statement")
                    
                    logger.info("✅ Closing message flow completed")
                except Exception as e:
                    logger.warning("⚠️  Could not generate closing message: %s", e)

                try:
                    completion_message = json.dumps({
                        "type": "interview_completed",
                        "message": "Interview completed. Redirecting to evaluation page...",
                        "token": booking_token,
                        "duration_minutes": int(elapsed_minutes),
                    }).encode("utf-8")
                    await ctx.room.local_participant.publish_data(
                        completion_message,
                        topic="lk-chat",
                        reliable=True,
                    )
                    logger.info("✅ Sent interview completion signal to frontend")
                    print("✅ Sent completion signal to frontend", flush=True)
                except Exception as e:
                    logger.warning("⚠️  Failed to send completion signal: %s", e)

                await asyncio.sleep(2)

                if booking_token:
                    try:
                        from app.services.booking_service import BookingService  # type: ignore
                        booking_service = BookingService(config)
                        booking_service.update_booking_status(booking_token, "completed")
                        logger.info("✅ Updated booking status to 'completed' for %s", booking_token)
                    except Exception as e:
                        logger.warning("⚠️  Failed to update booking status: %s", e)

                try:
                    logger.info("🔌 Disconnecting from room to end interview")
                    await ctx.room.disconnect()
                    logger.info("✅ Successfully disconnected from room")
                except Exception as e:
                    logger.warning("⚠️  Error disconnecting from room: %s", e)
                break

            if time_remaining_minutes <= 1:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(5)
    finally:
        from services.interview_finalizer import finalize_interview
        await finalize_interview(
            booking_token=booking_token,
            room_name=room_name,
            interview_start_time=resolved_start_time,
            plugins=plugins,
            config=config,
        )
