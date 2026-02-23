"""
Interview time loop - monitors duration, sends time updates, phase-boundary instructions,
triggers wrap-up/conclude/closing. Timer starts when candidate joins; duration adjusts for late join.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from livekit.agents import JobContext

from app.utils.datetime_utils import get_now_ist  # type: ignore
from app.utils.logger import get_logger  # type: ignore

from utils.phase_timing import get_phase_durations, get_phase_boundaries

logger = get_logger(__name__)

# Minimum interview length when candidate joins very late
MIN_ACTUAL_DURATION_MINUTES = 5


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
) -> None:
    """
    Run the main time loop until interview ends or room disconnects.
    Timer starts when candidate joins; actual_duration = scheduled_duration - join_delay.
    Sends phase-boundary SYSTEM instructions (intro → technical → MCQ → conclusion).
    Always calls finalize_interview in finally block.
    """
    warning_sent = False
    wrapping_up_instruction_sent = False
    conclude_instruction_sent = False
    closing_triggered = False
    interview_time_limit_reached = False
    last_time_update = None  # set after candidate joins
    intro_end_sent = False
    technical_end_sent = False
    mcq_end_sent = False

    # Resolved at candidate join (or kept from args if no dynamic timing)
    resolved_start_time = interview_start_time
    resolved_duration_minutes = interview_duration_minutes
    resolved_end_time = scheduled_end_time
    phase_durations: Dict[str, int] = {}
    intro_end_min = 0.0
    technical_end_min = 0.0
    mcq_end_min = 0.0
    candidate_joined = False

    # Base template for phase ratio: 30 or 45
    base_template = "45" if (scheduled_duration_minutes or interview_duration_minutes) >= 45 else "30"
    sched_duration = scheduled_duration_minutes if scheduled_duration_minutes is not None else interview_duration_minutes

    try:
        while ctx.room.isconnected() and not interview_time_limit_reached:
            current_time_ist = get_now_ist()

            # Wait for candidate to join before starting timer and phase logic
            if not candidate_joined:
                if len(ctx.room.remote_participants) > 0:
                    candidate_join_time = current_time_ist
                    join_delay_minutes = 0.0
                    if slot_start_ist is not None:
                        join_delay_minutes = max(
                            0.0,
                            (candidate_join_time - slot_start_ist).total_seconds() / 60.0,
                        )
                    actual_duration = max(
                        MIN_ACTUAL_DURATION_MINUTES,
                        sched_duration - int(join_delay_minutes),
                    )
                    resolved_start_time = candidate_join_time
                    resolved_duration_minutes = actual_duration
                    resolved_end_time = candidate_join_time + timedelta(minutes=actual_duration)
                    last_time_update = candidate_join_time
                    candidate_joined = True

                    phase_durations = get_phase_durations(actual_duration, base_template)
                    intro_end_min, technical_end_min, mcq_end_min = get_phase_boundaries(phase_durations)

                    try:
                        from agents.session_time import set_session_time
                        from services.session_time_store import set_store
                        from app.services.history_managed_llm_wrapper import reset_questions_asked  # type: ignore
                        set_session_time(resolved_start_time, resolved_duration_minutes)
                        set_store(resolved_start_time, resolved_duration_minutes, base_template)
                        reset_questions_asked()
                    except Exception as e:
                        logger.warning(f"Could not set session time store: {e}")

                    logger.info(
                        f"⏰ Candidate joined: start={resolved_start_time}, actual_duration={actual_duration} min "
                        f"(scheduled={sched_duration}, join_delay={join_delay_minutes:.1f} min). "
                        f"Phases: intro={phase_durations['intro']}, technical={phase_durations['technical']}, "
                        f"mcq={phase_durations['mcq']}, conclusion={phase_durations['conclusion']}"
                    )
                    print(
                        f"⏰ Timer started on candidate join: {actual_duration} min (join delay: {join_delay_minutes:.1f} min)",
                        flush=True,
                    )
                    # At start: instruct agent to begin with introduction
                    try:
                        await session.generate_reply(
                            instructions="SYSTEM: Begin with introduction and background questions. Welcome the candidate and set the pace for the interview."
                        )
                        logger.info("✅ Sent start instruction: introduction phase")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not send start instruction: {e}")
                else:
                    await asyncio.sleep(2)
                    continue

            elapsed_minutes = (current_time_ist - resolved_start_time).total_seconds() / 60
            time_limit_reached = False
            time_remaining_minutes = 0.0
            if resolved_end_time:
                time_remaining_minutes = (resolved_end_time - current_time_ist).total_seconds() / 60
                past_end = current_time_ist >= resolved_end_time
                at_least_90_pct = elapsed_minutes >= (resolved_duration_minutes * 0.9)
                if past_end and at_least_90_pct:
                    time_limit_reached = True
                    logger.info(
                        f"⏰ Interview time limit reached (end: {resolved_end_time}, elapsed: {elapsed_minutes:.1f} min)"
                    )
            else:
                time_remaining_minutes = max(0, resolved_duration_minutes - elapsed_minutes)
                if elapsed_minutes >= resolved_duration_minutes:
                    time_limit_reached = True
                    logger.info(
                        f"⏰ Interview duration limit reached ({resolved_duration_minutes} minutes elapsed)"
                    )

            # Phase-boundary SYSTEM instructions
            if not intro_end_sent and elapsed_minutes >= intro_end_min and intro_end_min > 0:
                intro_end_sent = True
                try:
                    msg = (
                        "SYSTEM: Introduction phase is complete. "
                        "Move to technical or expertise questions if the role requires technical evaluation or the interview includes coding. "
                        "Otherwise move to MCQ and logical reasoning questions. Keep pacing natural."
                    )
                    await session.generate_reply(instructions=msg)
                    logger.info(f"✅ Sent phase instruction: end of introduction (elapsed {elapsed_minutes:.1f} min)")
                except Exception as e:
                    logger.warning(f"⚠️  Could not send intro-end instruction: {e}")

            if not technical_end_sent and elapsed_minutes >= technical_end_min and technical_end_min > 0:
                technical_end_sent = True
                try:
                    msg = (
                        "SYSTEM: Technical/coding phase is complete. "
                        "Move to MCQ and logical reasoning questions. Keep to the question bank and time remaining."
                    )
                    await session.generate_reply(instructions=msg)
                    logger.info(f"✅ Sent phase instruction: end of technical (elapsed {elapsed_minutes:.1f} min)")
                except Exception as e:
                    logger.warning(f"⚠️  Could not send technical-end instruction: {e}")

            if not mcq_end_sent and elapsed_minutes >= mcq_end_min and mcq_end_min > 0:
                mcq_end_sent = True
                try:
                    msg = (
                        "SYSTEM: MCQ phase is complete. "
                        "Begin wrapping up toward the conclusion. You will receive a final conclude instruction when 2 minutes remain."
                    )
                    await session.generate_reply(instructions=msg)
                    logger.info(f"✅ Sent phase instruction: end of MCQ (elapsed {elapsed_minutes:.1f} min)")
                except Exception as e:
                    logger.warning(f"⚠️  Could not send mcq-end instruction: {e}")

            # Send time remaining update every 10 seconds
            if last_time_update is not None:
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
                        logger.debug(f"⏰ Sent time remaining update: {time_remaining_minutes:.1f} minutes")
                    except Exception as e:
                        logger.debug(f"⚠️  Failed to send time update: {e}")

            # 5-minute warning to frontend
            if not warning_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 5:
                warning_sent = True
                try:
                    warning_message = json.dumps({
                        "type": "interview_warning",
                        "message": f"Interview will end in approximately {int(time_remaining_minutes)} minute(s). Please wrap up your responses.",
                    }).encode("utf-8")
                    await ctx.room.local_participant.publish_data(
                        warning_message,
                        topic="lk-chat",
                        reliable=True,
                    )
                    logger.info(f"⚠️  Sent 5-minute warning ({time_remaining_minutes:.1f} min remaining)")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to send warning: {e}")

            # ~5 min remaining: wrapping up
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
                    logger.info(f"✅ Sent wrapping-up instruction (~{int(time_remaining_minutes)} min left)")
                    print(f"⏰ Wrapping-up instruction sent (~{int(time_remaining_minutes)} min left)", flush=True)
                except Exception as e:
                    logger.warning(f"⚠️  Could not send wrapping-up instruction: {e}")

            # ~2 min remaining: conclude
            if not conclude_instruction_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 2:
                conclude_instruction_sent = True
                try:
                    conclude_instructions = (
                        f"SYSTEM: You have about {int(time_remaining_minutes)} minutes left. Do NOT ask any more questions. "
                        "Say clearly that we are concluding (e.g. 'We have a couple of minutes left, so let us conclude.' or 'That brings us to the end.'). "
                        "One short sentence only. Do NOT say full goodbye yet; you will receive END_INTERVIEW in a moment for that."
                    )
                    await session.generate_reply(instructions=conclude_instructions)
                    logger.info(f"✅ Sent conclude instruction (~{int(time_remaining_minutes)} min left)")
                    print(f"⏰ Conclude instruction sent (~{int(time_remaining_minutes)} min left)", flush=True)
                except Exception as e:
                    logger.warning(f"⚠️  Could not send conclude instruction: {e}")

            # Trigger closing when time ends
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
                    }).encode("utf-8")
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
            interview_start_time=resolved_start_time,
            plugins=plugins,
            config=config,
        )
