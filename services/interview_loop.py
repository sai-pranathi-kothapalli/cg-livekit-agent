"""
Interview time loop - monitors duration, sends time updates, triggers wrap-up/conclude/closing.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional, Any, Dict

from livekit.agents import JobContext

from app.utils.datetime_utils import get_now_ist  # type: ignore
from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


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
) -> None:
    """
    Run the main time loop until interview ends or room disconnects.
    Handles: time updates, 5-min warning, wrapping up, conclude, closing, disconnect.
    Always calls finalize_interview in finally block.
    """
    warning_sent = False
    wrapping_up_instruction_sent = False
    conclude_instruction_sent = False
    closing_triggered = False
    interview_time_limit_reached = False
    last_time_update = interview_start_time

    try:
        while ctx.room.isconnected() and not interview_time_limit_reached:
            current_time_ist = get_now_ist()
            elapsed_minutes = (current_time_ist - interview_start_time).total_seconds() / 60

            time_limit_reached = False
            time_remaining_minutes = 0
            at_least_90_pct = elapsed_minutes >= (interview_duration_minutes * 0.9)

            if scheduled_end_time:
                time_remaining_minutes = (scheduled_end_time - current_time_ist).total_seconds() / 60
                past_scheduled_end = current_time_ist >= scheduled_end_time
                if past_scheduled_end and at_least_90_pct:
                    time_limit_reached = True
                    logger.info(f"⏰ Interview time limit reached (scheduled end: {scheduled_end_time}, elapsed: {elapsed_minutes:.1f} min)")
                elif past_scheduled_end and not at_least_90_pct:
                    logger.info(f"⏰ Scheduled end passed but elapsed {elapsed_minutes:.1f} min < 90% - waiting for full duration")
            else:
                time_remaining_minutes = interview_duration_minutes - elapsed_minutes
                if elapsed_minutes >= interview_duration_minutes:
                    time_limit_reached = True
                    logger.info(f"⏰ Interview duration limit reached ({interview_duration_minutes} minutes elapsed)")

            # Send time remaining update every 10 seconds
            time_since_last_update = (current_time_ist - last_time_update).total_seconds()
            if time_since_last_update >= 10:
                try:
                    time_update_message = json.dumps({
                        "type": "time_remaining",
                        "time_remaining_minutes": max(0, time_remaining_minutes),
                    }).encode('utf-8')
                    await ctx.room.local_participant.publish_data(
                        time_update_message,
                        topic="lk-chat",
                        reliable=False,
                    )
                    last_time_update = current_time_ist
                    logger.debug(f"⏰ Sent time remaining update: {time_remaining_minutes:.1f} minutes")
                except Exception as e:
                    logger.debug(f"⚠️  Failed to send time update: {e}")

            # Send 5-minute warning to frontend
            if not warning_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 5:
                warning_sent = True
                try:
                    warning_message = json.dumps({
                        "type": "interview_warning",
                        "message": f"Interview will end in approximately {int(time_remaining_minutes)} minute(s). Please wrap up your responses.",
                    }).encode('utf-8')
                    await ctx.room.local_participant.publish_data(
                        warning_message,
                        topic="lk-chat",
                        reliable=True,
                    )
                    logger.info(f"⚠️  Sent 5-minute warning ({(time_remaining_minutes):.1f} min remaining)")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to send warning: {e}")

            # At ~5 min remaining: wrapping up instruction
            if not wrapping_up_instruction_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 5:
                wrapping_up_instruction_sent = True
                try:
                    wrapping_up_instructions = (
                        f"SYSTEM: You have about {int(time_remaining_minutes)} minutes left. "
                        "Tell the candidate we are wrapping up (e.g. 'We have about 5 minutes left' or 'We are coming to the end'). "
                        "Ask one or two final questions from the question bank. Do NOT say full goodbye or thank them for their time yet; save that for when you receive END_INTERVIEW. "
                        "Keep it natural and brief."
                    )
                    await session.generate_reply(instructions=wrapping_up_instructions)
                    logger.info(f"✅ Sent wrapping-up instruction to agent (~{int(time_remaining_minutes)} min left)")
                    print(f"⏰ Wrapping-up instruction sent (~{int(time_remaining_minutes)} min left)", flush=True)
                except Exception as e:
                    logger.warning(f"⚠️  Could not send wrapping-up instruction: {e}")

            # At ~2 min remaining: conclude instruction
            if not conclude_instruction_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 2:
                conclude_instruction_sent = True
                try:
                    conclude_instructions = (
                        f"SYSTEM: You have about {int(time_remaining_minutes)} minutes left. Do NOT ask any more questions. "
                        "Say clearly that we are concluding (e.g. 'We have a couple of minutes left, so let us conclude.' or 'That brings us to the end.'). "
                        "One short sentence only. Do NOT say full goodbye yet; you will receive END_INTERVIEW in a moment for that."
                    )
                    await session.generate_reply(instructions=conclude_instructions)
                    logger.info(f"✅ Sent conclude instruction to agent (~{int(time_remaining_minutes)} min left)")
                    print(f"⏰ Conclude instruction sent (~{int(time_remaining_minutes)} min left)", flush=True)
                except Exception as e:
                    logger.warning(f"⚠️  Could not send conclude instruction: {e}")

            # Trigger closing when full duration reached
            trigger_closing_now = time_limit_reached and not closing_triggered
            if trigger_closing_now:
                closing_triggered = True
                interview_time_limit_reached = True
                logger.info("⏰ Full interview duration reached - ending interview gracefully")
                print("⏰ Full duration reached - ending interview", flush=True)

                try:
                    closing_instructions = """SYSTEM: END_INTERVIEW.

You may now conclude the interview. Politely conclude in 2–3 sentences: thank the candidate, say the interview is complete, and that they will be redirected to the evaluation page where they can view results and feedback. Wish them well. Keep it brief and professional."""
                    await session.generate_reply(instructions=closing_instructions)
                    await asyncio.sleep(5)
                    logger.info("✅ Closing message completed")
                except Exception as e:
                    logger.warning(f"⚠️  Could not generate closing message: {e}")

                try:
                    completion_message = json.dumps({
                        "type": "interview_completed",
                        "message": "Interview completed. Redirecting to evaluation page...",
                        "token": booking_token,
                        "duration_minutes": int(elapsed_minutes),
                    }).encode('utf-8')
                    await ctx.room.local_participant.publish_data(
                        completion_message,
                        topic="lk-chat",
                        reliable=True,
                    )
                    logger.info("✅ Sent interview completion signal to frontend")
                    print("✅ Sent completion signal to frontend", flush=True)
                except Exception as e:
                    logger.warning(f"⚠️  Failed to send completion signal: {e}")

                await asyncio.sleep(2)

                if booking_token:
                    try:
                        from app.services.booking_service import BookingService  # type: ignore
                        booking_service = BookingService(config)
                        booking_service.update_booking_status(booking_token, "completed")
                        logger.info(f"✅ Updated booking status to 'completed' for {booking_token}")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to update booking status: {e}")

                try:
                    logger.info("🔌 Disconnecting from room to end interview")
                    await ctx.room.disconnect()
                    logger.info("✅ Successfully disconnected from room")
                except Exception as e:
                    logger.warning(f"⚠️  Error disconnecting from room: {e}")
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
            interview_start_time=interview_start_time,
            plugins=plugins,
            config=config,
        )
