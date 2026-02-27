"""
Event handlers for AgentSession and Room (participant/track events).
"""

import asyncio
import json
from typing import Optional

from livekit import agents, rtc
from livekit.agents import JobContext

from agents.utils import get_track_source_name
from app.utils.logger import get_logger  # type: ignore
from services.time_context_llm_wrapper import generate_reply_with_instructions

logger = get_logger(__name__)


def setup_session_event_handlers(
    session: agents.AgentSession,
    logger_instance,
    booking_token: str = None,
    room_name: str = None,
    transcript_storage=None,
    ctx: Optional[JobContext] = None,
) -> None:
    """
    Setup event handlers on AgentSession to track user speech and agent replies.
    
    ctx is used to publish user transcripts to the frontend via data channel.
    """
    log = logger_instance or logger
    nudge_task: Optional[asyncio.Task] = None

    async def _run_nudge_timer():
        nonlocal nudge_task
        try:
            await asyncio.sleep(30)
            log.info("⏰ No user speech detected for 30s - triggering nudge")
            nudge_instruction = (
                "[INTERNAL — DO NOT READ ALOUD. The candidate has been silent for 30 seconds.]\n"
                "Briefly nudge the candidate. Ask if they are there, if they need help, or if they "
                "want more time to think. Be polite and professional. One short sentence only.\n"
                "[END INTERNAL CONTEXT]"
            )
            # Trigger nudge via a new task
            asyncio.create_task(generate_reply_with_instructions(session, instructions=nudge_instruction))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning(f"Error in nudge timer: {e}")

    def start_nudge_timer():
        nonlocal nudge_task
        if nudge_task:
            nudge_task.cancel()
        nudge_task = asyncio.create_task(_run_nudge_timer())

    def cancel_nudge_timer():
        nonlocal nudge_task
        if nudge_task:
            nudge_task.cancel()
            nudge_task = None

    @session.on("user_state_changed")
    def on_user_state_changed(event):
        try:
            old_state = event.old_state if hasattr(event, 'old_state') else 'unknown'
            new_state = event.new_state if hasattr(event, 'new_state') else 'unknown'
            log.debug(f"👤 [USER STATE] {old_state} → {new_state}")
            if new_state == "speaking":
                log.debug("🎤 [STT] User started speaking (VAD detected)")
                cancel_nudge_timer()
            elif new_state == "listening":
                log.debug("🔇 [STT] User stopped speaking (VAD detected silence)")
        except Exception as e:
            log.debug(f"Error in user_state_changed handler: {e}")

    @session.on("agent_state_changed")
    def on_agent_state_changed(event):
        try:
            old_state = event.old_state if hasattr(event, 'old_state') else 'unknown'
            new_state = event.new_state if hasattr(event, 'new_state') else 'unknown'
            log.debug(f"🤖 [AGENT STATE] {old_state} → {new_state}")
            if new_state == "thinking":
                log.debug("💭 [LLM] Agent started thinking (generating reply)")
            elif new_state == "speaking":
                log.debug("🔊 [TTS] Agent started speaking (audio playing)")
                cancel_nudge_timer()
            elif new_state == "listening":
                log.debug("👂 [AGENT] Agent is listening (ready for user input)")
                start_nudge_timer()
        except Exception as e:
            log.debug(f"Error in agent_state_changed handler: {e}")

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        try:
            transcript = getattr(event, 'transcript', '') or ''
            is_final = getattr(event, 'is_final', False)
            status = "FINAL" if is_final else "INTERIM"
            log.debug(f"📝 [STT] Transcript ({status}): '{transcript}'")

            if is_final and transcript and transcript_storage and booking_token:
                try:
                    from datetime import datetime
                    existing_transcripts = transcript_storage.get_transcript(booking_token)
                    next_index = max([t.get('index', 0) for t in existing_transcripts], default=-1) + 1
                    transcript_storage.save_transcript_message(
                        booking_token=booking_token,
                        room_name=room_name,
                        role="user",
                        content=transcript,
                        message_index=next_index,
                        timestamp=datetime.utcnow(),
                    )
                    log.debug(f"✅ Saved user transcript to database (index: {next_index})")
                except Exception as e:
                    log.warning(f"Failed to save user transcript: {e}")

            if is_final and transcript and ctx and ctx.room.isconnected():
                try:
                    loop = asyncio.get_running_loop()
                    async def _publish_user_transcript():
                        try:
                            payload = json.dumps({"type": "userTranscript", "message": transcript}).encode("utf-8")
                            await ctx.room.local_participant.publish_data(
                                payload, topic="lk-chat", reliable=True
                            )
                            log.debug("Sent user transcript to frontend via data channel")
                        except Exception as e:
                            log.warning(f"Failed to send user transcript to frontend: {e}")
                    loop.create_task(_publish_user_transcript())
                except RuntimeError:
                    log.debug("No running event loop for user transcript publish (skipping data channel)")
                except Exception as e:
                    log.warning(f"Could not schedule user transcript send: {e}")
            if is_final:
                log.debug("[OK] [STT] Final transcript received - will trigger LLM")
        except Exception as e:
            log.error(f"[ERR] Error in user_input_transcribed handler: {e}", exc_info=True)
            print(f"[ERR] Error in user_input_transcribed handler: {e}")

    @session.on("error")
    def on_error(event):
        try:
            error_msg = str(event) if event else "Unknown error"
            log.error(f"[ERR] [SESSION ERROR] {error_msg}")
            print(f"[ERR] [SESSION ERROR] {error_msg}")
        except Exception as e:
            log.error(f"[ERR] Error in error handler: {e}", exc_info=True)

    @session.on("conversation_item_added")
    def on_conversation_item_added(item):
        try:
            role = getattr(item, 'role', 'unknown')
            content = getattr(item, 'content', '')
            log.debug(f"💬 [CONVERSATION] {role.upper()} message added")
            if role == "user" and content:
                log.debug(f"   User said: {content}")
        except Exception as e:
            log.debug(f"Error in conversation_item_added handler: {e}")

    @session.on("speech_created")
    def on_speech_created(event):
        try:
            log.info(f"🗣️  [TTS] Speech created")
            print(f"🗣️  [TTS] Speech created")
        except Exception as e:
            log.debug(f"Error in speech_created handler: {e}")

    @session.on("metrics_collected")
    def on_metrics_collected(event):
        try:
            metrics = getattr(event, 'metrics', None)
            if metrics:
                stt_latency = getattr(metrics, 'stt_latency', 0)
                llm_latency = getattr(metrics, 'llm_latency', 0)
                tts_latency = getattr(metrics, 'tts_latency', 0)
                if stt_latency or llm_latency or tts_latency:
                    log.info(f"📊 [METRICS] STT: {stt_latency:.3f}s, LLM: {llm_latency:.3f}s, TTS: {tts_latency:.3f}s")
                    print(f"📊 [METRICS] STT: {stt_latency:.3f}s, LLM: {llm_latency:.3f}s, TTS: {tts_latency:.3f}s")
        except Exception as e:
            log.debug(f"Error in metrics_collected handler: {e}")

    log.info("[OK] Session event handlers installed for speech tracking")
    print("[OK] Session event handlers installed for speech tracking")


def setup_participant_handlers(ctx: JobContext, room_sid: str, logger_instance=None) -> None:
    """
    Setup event handlers for participant and track events.
    """
    log = logger_instance or logger

    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        total = len(ctx.room.remote_participants) + 1
        participant_type = "Agent" if "agent" in participant.identity.lower() else "User"
        log.info("─" * 60)
        log.info("[OK] NEW PARTICIPANT JOINED")
        log.info("─" * 60)
        log.info(f"   Room SID: {room_sid}")
        log.info(f"   Room Name: {ctx.room.name}")
        log.info(f"   Identity: {participant.identity}")
        log.info(f"   SID: {participant.sid}")
        log.info(f"   Name: {participant.name}")
        log.info(f"   Type: {participant_type}")
        log.info(f"   📊 UPDATED PARTICIPANT COUNT: Total: {total}")
        log.info("─" * 60)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(
        participant: rtc.RemoteParticipant,
        reason: Optional[str] = None
    ) -> None:
        total = len(ctx.room.remote_participants) + 1
        participant_type = "Agent" if "agent" in participant.identity.lower() else "User"
        log.info("─" * 60)
        log.info("[ERR] PARTICIPANT LEFT")
        log.info("─" * 60)
        log.info(f"   Room SID: {room_sid}")
        log.info(f"   Room Name: {ctx.room.name}")
        log.info(f"   Identity: {participant.identity}")
        log.info(f"   SID: {participant.sid}")
        log.info(f"   Name: {participant.name}")
        log.info(f"   Type: {participant_type}")
        log.info(f"   Reason: {reason if reason else 'Unknown'}")
        log.info(f"   📊 UPDATED PARTICIPANT COUNT: Total: {total}")
        log.info("─" * 60)

    @ctx.room.on("track_published")
    def on_track_published(
        publication: rtc.TrackPublication,
        participant: rtc.Participant
    ) -> None:
        track_name = get_track_source_name(publication.source)
        log.info(f"🎤 TRACK PUBLISHED:")
        log.info(f"   Participant: {participant.identity}")
        log.info(f"   Track Type: {track_name}")
        log.info(f"   Room: {ctx.room.name}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.Participant
    ) -> None:
        track_name = get_track_source_name(publication.source)
        log.info(f"👂 TRACK SUBSCRIBED:")
        log.info(f"   Participant: {participant.identity}")
        log.info(f"   Track Type: {track_name}")
        log.info(f"   Room: {ctx.room.name}")
