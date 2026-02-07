"""
LiveKit Agent Entrypoint

Enterprise-grade entrypoint for LiveKit agent jobs with proper
error handling, logging, and plugin management.
"""

import asyncio
import json
import logging
import sys
import os
import time
from typing import Optional
from datetime import datetime, timedelta

from livekit import agents, rtc
from livekit.agents import JobContext, AgentSession, room_io
from livekit.plugins import noise_cancellation

# Add backend to Python path so we can import from app (try both folder names)
import sys
from pathlib import Path
_root = Path(__file__).parent.parent.parent
backend_path = _root / "Livekit-Backend-agent-backend"
if not backend_path.exists():
    backend_path = _root / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.config import Config, get_config  # type: ignore
from app.utils.datetime_utils import get_now_ist, to_ist  # type: ignore
from agents.professional_arjun import ProfessionalArjun
from agents.utils import get_track_source_name
# from app.services.application_form_service import ApplicationFormService  # Service not found in backend
try:
    from app.services.plugin_service import PluginService  # type: ignore
except ImportError:
    from services.plugin_service import PluginService
try:
    from app.services.job_description_service import JobDescriptionService  # type: ignore
except ImportError:
    JobDescriptionService = None  # Optional service
from app.utils.logger import get_logger  # type: ignore
from app.utils.exceptions import AgentError  # type: ignore

logger = get_logger(__name__)


async def entrypoint(ctx: JobContext) -> None:
    """
    Main entrypoint for LiveKit agent jobs.
    """
    try:
        # Verify noise cancellation plugin is available
        try:
            import livekit.plugins.noise_cancellation as nc
            logger.info(f"✅ Noise cancellation plugin loaded (v{getattr(nc, '__version__', 'unknown')})")
            print(f"✅ Noise cancellation plugin loaded", flush=True)
        except ImportError:
            logger.warning("❌ Noise cancellation plugin NOT found in this environment!")
            print("❌ Noise cancellation plugin NOT found!", flush=True)
        # CRITICAL: LiveKit runs entrypoint in separate process via multiprocessing
        # We need to ensure logs are visible - use both logger.critical() AND print()
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Force logging to appear immediately - set level to ensure visibility
        logger.setLevel(logging.DEBUG)  # Set to DEBUG to catch everything
        
        # CRITICAL: Use logger.critical() which should always appear
        entrypoint_banner = "=" * 60
        logger.critical(entrypoint_banner)
        logger.critical("[PROD][PROD][PROD] AGENT ENTRYPOINT CALLED - JOB DISPATCHED [PROD][PROD][PROD]")
        logger.critical(entrypoint_banner)
        
        # Write to file as backup (critical for debugging)
        try:
            log_file = Path(__file__).parent.parent / "entrypoint.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"ENTRYPOINT CALLED: {asyncio.get_event_loop().time()}\n")
                f.write(f"Job ID: {ctx.job.id}\n")
                f.write(f"Room: {ctx.room.name}\n")
        except Exception:
            pass
        
        # Also print to stdout/stderr for maximum visibility
        print("\n" + entrypoint_banner, flush=True, file=sys.stdout)
        print("[PROD][PROD][PROD] AGENT ENTRYPOINT CALLED - JOB DISPATCHED [PROD][PROD][PROD]", flush=True, file=sys.stdout)
        print(entrypoint_banner + "\n", flush=True, file=sys.stdout)
        sys.stdout.flush()
        
        config = get_config()
        
        # Extract booking token from room name or metadata
        booking_token = None
        room_name = ctx.room.name
        try:
            # Try to extract from room name (format: "interview_<token>" or just token)
            if room_name.startswith("interview_"):
                booking_token = room_name.replace("interview_", "")
            elif len(room_name) == 32 and room_name.replace("_", "").replace("-", "").isalnum():
                booking_token = room_name
            # Try room metadata
            if not booking_token and hasattr(ctx.room, 'metadata') and ctx.room.metadata:
                import json
                metadata = json.loads(ctx.room.metadata)
                booking_token = metadata.get('booking_token') or metadata.get('token')
        except Exception as e:
            logger.warning(f"Could not extract booking token: {e}")
        
        # Log job details with CRITICAL level
        logger.critical(f"[INFO] JOB DETAILS:")
        logger.critical(f"   Job ID: {ctx.job.id}")
        logger.critical(f"   Room Name: {room_name}")
        logger.critical(f"   Booking Token: {booking_token or 'unknown'}")
        logger.critical(f"   Agent Name: {config.livekit.agent_name}")
        
        # Write job details to file
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"Agent Name: {config.livekit.agent_name}\n")
                f.write(f"{'='*60}\n")
        except Exception:
            pass
        
        # Also print job details
        print(f"[INFO] JOB DETAILS:", flush=True, file=sys.stdout)
        print(f"   Job ID: {ctx.job.id}", flush=True, file=sys.stdout)
        print(f"   Room Name: {ctx.room.name}", flush=True, file=sys.stdout)
        print(f"   Agent Name: {config.livekit.agent_name}", flush=True, file=sys.stdout)
        print("=" * 60, flush=True, file=sys.stdout)
        sys.stdout.flush()
        
        # Also use regular logger for structured logging
        logger.info("=" * 60)
        logger.info("[PROD] AGENT JOB DISPATCHED")
        logger.info(f"[INFO] JOB DETAILS:")
        logger.info(f"   Job ID: {ctx.job.id}")
        logger.info(f"   Room Name: {ctx.room.name}")
        logger.info(f"   Agent Name: {config.livekit.agent_name}")
        logger.info("=" * 60)
        
        # Step 1: Connect to room
        logger.info("📡 CONNECTION PROCESS: Step 1 - Connecting to room...")
        print("📡 CONNECTION PROCESS: Step 1 - Connecting to room...", flush=True)
        try:
            await ctx.connect()
            logger.info("[OK] Step 1: Success - Connected to room!")
            print("[OK] Step 1: Success - Connected to room!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 1: Failed to connect to room - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            print(f"   Error details: {str(e)}", flush=True)
            raise AgentError(f"Failed to connect to room: {str(e)}", "my-interviewer")
        
        # Get Room SID after connection
        try:
            room_sid = await ctx.room.sid
            logger.info(f"   Room SID: {room_sid}")
            print(f"   Room SID: {room_sid}", flush=True)
        except Exception as e:
            warning_msg = f"   Room SID: Error getting SID - {e}"
            logger.warning(warning_msg)
            print(warning_msg, flush=True)
            room_sid = "N/A"
        
        # Step 2: Fetch structured application data from Supabase
        logger.info("Step 2: Fetching Candidate Application Data...")
        print("Step 2: Fetching Candidate Application Data...", flush=True)
        candidate_profile = await _fetch_candidate_profile(ctx.room, config)  # Returns None if service unavailable
        
        # Step 2b: Fetch Job Description
        logger.info("Step 2b: Fetching Job Description...")
        print("Step 2b: Fetching Job Description...", flush=True)
        jd_data = None
        if JobDescriptionService:
            try:
                jd_service = JobDescriptionService(config)
                jd_data = jd_service.get_job_description()
                logger.info("[OK] Step 2b: Job description fetched successfully")
                print("[OK] Step 2b: Job description fetched successfully", flush=True)
            except Exception as e:
                warning_msg = f"[WARN]  Step 2b: Failed to fetch job description: {e}"
                logger.warning(warning_msg)
                print(warning_msg, flush=True)
                jd_data = None
        else:
            logger.warning("[WARN]  Step 2b: JobDescriptionService not available")
            print("[WARN]  Step 2b: JobDescriptionService not available", flush=True)
        
        # Step 3: Setup participant event handlers
        logger.info("Step 3: Setting up participant event handlers...")
        print("Step 3: Setting up participant event handlers...", flush=True)
        _setup_participant_handlers(ctx, room_sid)
        
        # Step 3.5: Install STT log interceptor to capture transcript timing
        logger.info("Step 3.5: Installing STT log interceptor...")
        print("Step 3.5: Installing STT log interceptor...", flush=True)
        try:
            from services.log_interceptor import install_stt_interceptor
            install_stt_interceptor()
            logger.info("[OK] STT log interceptor installed")
            print("[OK] STT log interceptor installed", flush=True)
        except Exception as e:
            warning_msg = f"[WARN]  Failed to install STT interceptor: {e}"
            logger.warning(warning_msg)
            print(warning_msg, flush=True)
        
        # Step 4: Initialize plugins
        logger.info("Step 4: Initializing Plugins (STT, LLM, TTS)...")
        print("Step 4: Initializing Plugins (STT, LLM, TTS)...", flush=True)
        try:
            plugin_service = PluginService(config)
            plugins = await plugin_service.initialize_plugins(
                ctx.room,
                booking_token=booking_token
            )
            
            # CRITICAL: Validate TTS plugin is actually initialized
            if not plugins.get("tts"):
                raise RuntimeError("TTS plugin is None - agent cannot speak!")
            logger.info(f"[OK] TTS plugin type: {type(plugins['tts']).__name__}")
            print(f"[OK] TTS plugin type: {type(plugins['tts']).__name__}", flush=True)
            
            # Validate other plugins
            if not plugins.get("stt"):
                raise RuntimeError("STT plugin is None - agent cannot hear!")
            if not plugins.get("llm"):
                raise RuntimeError("LLM plugin is None - agent cannot think!")
            if not plugins.get("vad"):
                raise RuntimeError("VAD plugin is None - turn detection will fail!")
            
            logger.info("[OK] Step 4: Plugins initialized successfully!")
            print("[OK] Step 4: Plugins initialized successfully!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 4: Failed to initialize plugins - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            raise
        
        # Store references for transcript saving and evaluation
        transcript_storage = None
        try:
            from services.transcript_storage_wrapper import get_transcript_storage_service  # type: ignore
            transcript_storage = get_transcript_storage_service()
        except Exception as e:
            logger.warning(f"Could not get transcript storage service: {e}")
        
        # Store interview start time for duration calculation
        interview_start_time = get_now_ist()
        
        # Get booking data to determine interview duration limit
        interview_duration_minutes = 30  # Default duration
        scheduled_end_time = None
        if booking_token:
            try:
                from app.services.booking_service import BookingService  # type: ignore
                from app.services.slot_service import SlotService  # type: ignore
                booking_service = BookingService(config)
                slot_service = SlotService(config)
                booking = booking_service.get_booking(booking_token)
                
                if booking:
                    # Try to get duration from slot if booking has slot_id
                    slot_id = booking.get('slot_id')
                    if slot_id:
                        try:
                            slot = slot_service.get_slot(slot_id)
                            if slot and slot.get('end_time'):
                                # Calculate duration from slot
                                slot_start_str = slot.get('start_time') or slot.get('slot_datetime')
                                slot_end_str = slot.get('end_time')
                                
                                if slot_start_str and slot_end_str:
                                    try:
                                        slot_start = datetime.fromisoformat(slot_start_str.replace('Z', '+00:00'))
                                        slot_end = datetime.fromisoformat(slot_end_str.replace('Z', '+00:00'))
                                        # Normalize to IST so comparison with current_time_ist is correct (avoids early end from UTC vs IST)
                                        slot_start_ist = to_ist(slot_start)
                                        slot_end_ist = to_ist(slot_end)
                                        duration_seconds = (slot_end_ist - slot_start_ist).total_seconds()
                                        interview_duration_minutes = int(duration_seconds / 60)
                                        scheduled_end_time = slot_end_ist
                                        # Enforce minimum 30 min so interview does not end early (e.g. 15-min slot data error)
                                        if interview_duration_minutes < 30:
                                            logger.warning(f"⏰ Slot duration {interview_duration_minutes} min < 30; using 30 min from start")
                                            interview_duration_minutes = 30
                                            scheduled_end_time = interview_start_time + timedelta(minutes=30)
                                        logger.info(f"⏰ Using slot duration: {interview_duration_minutes} minutes (from slot {slot_id}), end at IST {scheduled_end_time}")
                                    except Exception as e:
                                        logger.warning(f"Could not parse slot times: {e}")
                        except Exception as e:
                            logger.warning(f"Could not fetch slot: {e}")
                    
                    # If no slot duration, use scheduled_at + default duration
                    if not scheduled_end_time and booking.get('scheduled_at'):
                        scheduled_at_str = booking.get('scheduled_at')
                        try:
                            if 'Z' in scheduled_at_str or '+00:00' in scheduled_at_str:
                                scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
                            else:
                                scheduled_at = datetime.fromisoformat(scheduled_at_str)
                            scheduled_at_ist = to_ist(scheduled_at)
                            # Default interview duration: 30 minutes; end time in IST for correct comparison
                            scheduled_end_time = scheduled_at_ist + timedelta(minutes=interview_duration_minutes)
                            logger.info(f"⏰ Interview scheduled: {scheduled_at_ist} IST, will end at: {scheduled_end_time} ({interview_duration_minutes} min duration)")
                        except Exception as e:
                            logger.warning(f"Could not parse scheduled_at: {e}, using default duration")
            except Exception as e:
                logger.warning(f"Could not fetch booking for duration: {e}")
        
        if scheduled_end_time:
            logger.info(f"⏰ Interview time limit: {interview_duration_minutes} minutes (ends at {scheduled_end_time})")
        else:
            logger.info(f"⏰ Using default interview duration: {interview_duration_minutes} minutes from start")
        
        # Set session time in context so LLM wrapper can inject "current minute X of Y" into chat context
        try:
            from agents.session_time import set_session_time
            set_session_time(interview_start_time, interview_duration_minutes)
            logger.info(f"⏰ Session time context set: {interview_duration_minutes} min (LLM will receive current minute each turn)")
        except Exception as e:
            logger.warning(f"Could not set session time context: {e}")
        
        # Step 5: Turn detection - Using VAD only
        logger.info("Step 5: Initializing Turn Detection...")
        print("Step 5: Initializing Turn Detection...", flush=True)
        logger.info("ℹ️  Using VAD-based turn detection (recommended for production)")
        print("ℹ️  Using VAD-based turn detection (recommended for production)", flush=True)
        logger.info(f"   💡 VAD (Silero) configured: min_silence={config.silero_vad.min_silence_duration}s, min_speech={config.silero_vad.min_speech_duration}s")
        print(f"   💡 VAD (Silero) configured: min_silence={config.silero_vad.min_silence_duration}s, min_speech={config.silero_vad.min_speech_duration}s", flush=True)
        logger.info("   [OK] No additional ML models required")
        print("   [OK] No additional ML models required", flush=True)
        
        turn_detector = None  # Use VAD-based detection
        
        # Step 6: Create agent session
        logger.info("Step 5: Creating AgentSession...")
        print("Step 5: Creating AgentSession...", flush=True)
        try:
            session = AgentSession(
                stt=plugins["stt"],
                llm=plugins["llm"],
                tts=plugins["tts"],  # OpenAI TTS
                vad=plugins["vad"],  # VAD handles turn detection when multilingual model is None
                turn_detection=turn_detector,  # Optional: None defaults to VAD-based detection
                allow_interruptions=False,  # [OK] Disabled: Agent must finish speaking before listening
                false_interruption_timeout=2.0,  # [OK] Wait 2 seconds before resuming after false interruption
                resume_false_interruption=True,  # [OK] Auto-resume if background noise triggers VAD
                # CRITICAL: Increase min_endpointing_delay to give STT more time to finalize
                min_endpointing_delay=1.5,
            )
            logger.info("[OK] Step 5: Success - AgentSession created!")
            print("[OK] Step 5: Success - AgentSession created!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 5: Failed to create AgentSession - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            raise
        
        # Step 7: Start session
        logger.info("Step 6: Starting session...")
        print("Step 6: Starting session...", flush=True)
        
        # Agent context comes from Job Description (admin dashboard). Single 'context' field in DB.
        agent_instructions = None
        if jd_data and jd_data.get("context"):
            agent_instructions = jd_data["context"].strip()
            # Substitute placeholders from candidate profile (e.g. {name}, {full_name}, {email})
            agent_instructions = _substitute_context_placeholders(agent_instructions, candidate_profile)
            logger.info("[OK] Using agent context from Job Description (admin)")
        if not agent_instructions:
            logger.info("[OK] No context in Job Description; using default agent instructions")
            
        try:
            agent = ProfessionalArjun(
                candidate_profile=candidate_profile,
                job_description=None,  # Context is in base_instructions from JD; no separate JD section
                base_instructions=agent_instructions or None,
                duration_minutes=interview_duration_minutes
            )
            logger.info(f"✅ Agent created with duration: {interview_duration_minutes} minutes")
            print(f"✅ Agent created with duration: {interview_duration_minutes} minutes", flush=True)
            logger.info("[OK] Agent instance created successfully")
            print("[OK] Agent instance created successfully", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Failed to create agent instance - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            raise
        
        # Log room state before starting session
        logger.info(f"📊 Room state before session.start: connected={ctx.room.isconnected()}, participants={len(ctx.room.remote_participants)}")
        print(f"📊 Room state before session.start: connected={ctx.room.isconnected()}, participants={len(ctx.room.remote_participants)}", flush=True)
        
        # Add event handlers to track user speech and agent replies
        _setup_session_event_handlers(session, logger, booking_token, room_name, transcript_storage, ctx)
        
        # Start session - this will handle all user speech automatically
        logger.info("[PROD] Starting AgentSession (will handle user speech automatically)...")
        print("[PROD] Starting AgentSession (will handle user speech automatically)...", flush=True)
        
        try:
            run_result = await session.start(
                room=ctx.room, 
                agent=agent,
                room_options=room_io.RoomOptions(
                    audio_input=room_io.AudioInputOptions(
                        noise_cancellation=noise_cancellation.BVC(),
                    ),
                ),
            )
            logger.info("[OK] Step 6: Success - Session started with BVC noise cancellation!")
            print("[OK] Step 6: Success - Session started with BVC noise cancellation!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 6: Failed to start session - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            print(f"   Error details: {str(e)}", flush=True)
            raise
        
        if run_result:
            logger.info(f"📊 Session returned RunResult: {run_result}")
            print(f"📊 Session returned RunResult", flush=True)
        else:
            logger.info("📊 Session already started (returned None)")
            print("📊 Session already started", flush=True)
        
        # CRITICAL: Verify session components are initialized
        await asyncio.sleep(0.5)  # Brief pause for session to initialize
        if not session.tts:
            logger.error("[ERR] Session TTS is None after start() call!")
            print("[ERR] Session TTS is None after start() call!", flush=True)
            raise RuntimeError("Session TTS failed to initialize - agent cannot speak!")
        if not session.llm:
            logger.error("[ERR] Session LLM is None after start() call!")
            print("[ERR] Session LLM is None after start() call!", flush=True)
            raise RuntimeError("Session LLM failed to initialize - agent cannot think!")
        if not ctx.room.isconnected():
            logger.error("[ERR] Room is not connected after session start!")
            print("[ERR] Room is not connected after session start!", flush=True)
            raise RuntimeError("Room connection lost - agent cannot function!")
        logger.info(f"[OK] Session components verified: TTS={session.tts is not None}, LLM={session.llm is not None}, Room connected={ctx.room.isconnected()}")
        print(f"[OK] Session components verified", flush=True)
        
        # Log session state
        logger.info(f"[DEBUG] Session state check:")
        logger.info(f"   Agent state: {session.agent_state}")
        logger.info(f"   User state: {session.user_state}")
        logger.info(f"   Current speech: {session.current_speech is not None}")
        logger.info(f"   TTS plugin: {type(session.tts).__name__ if session.tts else 'None'}")
        print(f"[DEBUG] Session state: agent={session.agent_state}, user={session.user_state}")
        print(f"[DEBUG] TTS plugin: {type(session.tts).__name__ if session.tts else 'None'}")
        
        # Log room state after starting session
        logger.info(f"📊 Room state after session.start: connected={ctx.room.isconnected()}, remote_participants={len(ctx.room.remote_participants)}")
        print(f"📊 Room state after session.start: connected={ctx.room.isconnected()}, remote_participants={len(ctx.room.remote_participants)}")
        
        # Log local participant info
        local_participant = ctx.room.local_participant
        if local_participant:
            logger.info(f"🤖 Agent (local) participant: identity={local_participant.identity}, sid={local_participant.sid}")
            print(f"🤖 Agent (local) participant: identity={local_participant.identity}, sid={local_participant.sid}")
        
        # Log audio track subscriptions for debugging
        logger.info("[DEBUG] Checking audio track subscriptions...")
        print("[DEBUG] Checking audio track subscriptions...")
        audio_tracks_found = False
        for participant in ctx.room.remote_participants.values():
            logger.info(f"   👤 Checking participant: {participant.identity}")
            print(f"   👤 Checking participant: {participant.identity}")
            for track_pub in participant.track_publications.values():
                if track_pub.kind == rtc.TrackKind.KIND_AUDIO:
                    audio_tracks_found = True
                    logger.info(f"      🎤 Audio track: subscribed={track_pub.subscribed}, muted={track_pub.muted}, source={track_pub.source}")
                    print(f"      🎤 Audio track: subscribed={track_pub.subscribed}, muted={track_pub.muted}")
                    if track_pub.track:
                        logger.info(f"         [OK] Track object exists: {type(track_pub.track).__name__}")
                        print(f"         [OK] Track object exists")
                    else:
                        logger.warning(f"         [WARN]  Track object is None - audio may not be received!")
                        print(f"         [WARN]  Track object is None!")
        
        if not audio_tracks_found:
            logger.warning("[WARN]  NO AUDIO TRACKS FOUND from remote participants!")
            logger.warning("   This means the agent cannot hear the user!")
            print("[WARN]  NO AUDIO TRACKS FOUND - Agent cannot hear user!")
        else:
            logger.info("[OK] Audio tracks found - agent should be able to hear user")
            print("[OK] Audio tracks found")
        
        # Step 6: Wait for participant to join, then generate initial greeting
        logger.info("Step 6: Waiting for participant to join room...")
        print("Step 6: Waiting for participant to join room...")
        
        # Wait up to 30 seconds for a participant to join
        max_wait_time = 30
        wait_interval = 1
        waited = 0
        
        while not ctx.room.remote_participants and waited < max_wait_time:
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            if waited % 5 == 0:  # Log every 5 seconds
                logger.info(f"   Waiting for participant... ({waited}s/{max_wait_time}s)")
                print(f"   Waiting for participant... ({waited}s/{max_wait_time}s)")
        
        if ctx.room.remote_participants:
            participant_count = len(ctx.room.remote_participants)
            logger.info(f"[OK] Participant(s) detected: {participant_count} remote participant(s) in room")
            print(f"[OK] Participant(s) detected: {participant_count} remote participant(s) in room")
            
            # Log participant details
            for participant in ctx.room.remote_participants.values():
                logger.info(f"   👤 Participant: identity={participant.identity}, sid={participant.sid}")
                print(f"   👤 Participant: identity={participant.identity}, sid={participant.sid}")
            
            logger.info("Step 6b: Generating greeting...")
            print("Step 6b: Generating greeting...")
            try:
                # CRITICAL: Verify session is actually running before generating reply
                # Check if session has required components
                if not hasattr(session, 'tts') or session.tts is None:
                    raise RuntimeError("Session TTS is None - cannot generate reply!")
                if not hasattr(session, 'llm') or session.llm is None:
                    raise RuntimeError("Session LLM is None - cannot generate reply!")
                if not ctx.room.isconnected():
                    raise RuntimeError("Room is not connected - cannot generate reply!")
                
                # Verify TTS is available
                if not hasattr(session, 'tts') or session.tts is None:
                    raise RuntimeError("TTS plugin is None in session - cannot speak!")
                
                logger.info(f"   Session running: {getattr(session, '_running', False)}")
                logger.info(f"   TTS available: {session.tts is not None}")
                logger.info(f"   Agent state before greeting: {session.agent_state}")
                print(f"   Session running: {getattr(session, '_running', False)}")
                print(f"   TTS available: {session.tts is not None}")
                print(f"   Agent state: {session.agent_state}")
                
                # Set flag to skip transcript for greeting
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(True)
                
                logger.info("   Calling session.generate_reply() for greeting...")
                print("   Calling session.generate_reply() for greeting...")
                
                # Add timeout to prevent hanging
                try:
                    await asyncio.wait_for(
                        session.generate_reply(
                            instructions="""
                            As Alyza, start the interview with a professional, welcoming opening:
                            - Introduce yourself warmly: "Hello! I am Alyza, a professional Banking Interviewer." (Ensure NO brackets are used).
                           
                            - Ask ONLY ONE simple question: "To begin, could you please tell me a bit about yourself and your educational background?"
                            - Keep it professional, clear, and encouraging - maintain a formal yet approachable tone.
                            - Show genuine interest in their learning journey.
                            - Make them feel comfortable and supported.
                            - CRITICAL: Ask only ONE question. Wait for their response before asking about interests or projects.
                            """
                        ),
                        timeout=60.0  # 60 second timeout for greeting generation
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError("generate_reply timed out after 60 seconds - TTS or LLM may be stuck!")
                
                # Reset flag after greeting
                set_skip_transcript(False)
                logger.info("[OK] Step 6b: Success - Greeting generated! (transcript skipped)")
                print("[OK] Step 6b: Success - Greeting generated! (transcript skipped)")
                
                # CRITICAL: Verify session is ready to listen after greeting
                await asyncio.sleep(2)  # Increased pause for state to update and audio to play
                
                # Check if agent published audio tracks
                local_participant = ctx.room.local_participant
                audio_tracks_published = False
                if local_participant:
                    for track_pub in local_participant.track_publications.values():
                        if track_pub.kind == rtc.TrackKind.KIND_AUDIO:
                            audio_tracks_published = True
                            # LocalTrackPublication uses 'sid', RemoteTrackPublication uses 'track_sid'
                            track_id = getattr(track_pub, 'sid', getattr(track_pub, 'track_sid', 'unknown'))
                            logger.info(f"   🔊 Agent audio track published: {track_id}, muted={track_pub.muted}")
                            print(f"   🔊 Agent audio track published: {track_id}")
                            break
                
                if not audio_tracks_published:
                    logger.warning("[WARN]  No audio tracks published by agent - user may not hear agent!")
                    print("[WARN]  No audio tracks published by agent!")
                else:
                    logger.info("[OK] Agent audio track is published - user should hear agent")
                    print("[OK] Agent audio track is published")
                
                logger.info(f"[DEBUG] Post-greeting session state check:")
                logger.info(f"   Agent state: {session.agent_state}")
                logger.info(f"   User state: {session.user_state}")
                logger.info(f"   Room connected: {ctx.room.isconnected()}")
                logger.info(f"   Remote participants: {len(ctx.room.remote_participants)}")
                print(f"[DEBUG] Post-greeting state: agent={session.agent_state}, user={session.user_state}")
                
                if session.agent_state == "listening":
                    logger.info("[OK] Agent is in LISTENING state - ready to receive user speech!")
                    print("[OK] Agent is LISTENING - ready for user input!")
                else:
                    logger.warning(f"[WARN]  Agent state is '{session.agent_state}' - expected 'listening'")
                    logger.warning("   Agent may not be ready to receive user speech!")
                    print(f"[WARN]  Agent state is '{session.agent_state}' (expected 'listening')")
            except RuntimeError as e:
                # Reset flag on error
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(False)
                if "isn't running" in str(e):
                    warning_msg = "[WARN]  Session stopped before greeting could be generated (participant may have disconnected)"
                    logger.warning(warning_msg)
                    print(warning_msg, flush=True)
                else:
                    error_msg = f"[ERR] Error generating greeting: {e}"
                    logger.error(error_msg, exc_info=True)
                    print(error_msg, flush=True)
                    print(f"   Error type: {type(e).__name__}", flush=True)
                    raise
            except Exception as e:
                # Reset flag on any error
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(False)
                error_msg = f"[ERR] Unexpected error generating greeting: {e}"
                logger.error(error_msg, exc_info=True)
                print(error_msg, flush=True)
                print(f"   Error type: {type(e).__name__}", flush=True)
                print(f"   Error details: {str(e)}", flush=True)
                raise
        else:
            logger.warning(f"[WARN]  No participants joined after {max_wait_time}s, skipping greeting generation")
            print(f"[WARN]  No participants joined after {max_wait_time}s, skipping greeting generation")
            logger.info("   Agent will wait for participants to join before responding")
            print("   Agent will wait for participants to join before responding")
        
        logger.info("--- Entrypoint Active (Interview in progress) ---")
        logger.info("💡 The AgentSession will automatically handle user speech and generate replies")
        logger.info("💡 Event handlers are installed to log all speech events")
        print("--- Entrypoint Active (Interview in progress) ---")
        print("💡 AgentSession is listening for user speech automatically")
        
        session_start_time = time.time()
        last_health_check = time.time()
        consecutive_errors = 0
        max_consecutive_errors = 5
        interview_time_limit_reached = False
        warning_sent = False  # Track if 2-minute warning was sent to frontend
        wrapping_up_instruction_sent = False  # One-time: tell agent to say "we are wrapping up" and ask final questions (~28 min)
        conclude_instruction_sent = False  # One-time: tell agent to say "let us conclude" at ~29 min, no more questions
        closing_triggered = False  # One-time: send closing LLM call only when full duration reached (30 min)
        
        # Log initial room state
        logger.info(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        logger.info(f"[DEBUG] Session agent_state: {session.agent_state}, user_state: {session.user_state}")
        print(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        print(f"[DEBUG] Session state: agent={session.agent_state}, user={session.user_state}")
        
        try:
            while ctx.room.isconnected() and not interview_time_limit_reached:
                # Check if interview time limit has been reached
                current_time_ist = get_now_ist()
                elapsed_minutes = (current_time_ist - interview_start_time).total_seconds() / 60
                
                # Check time limit (either scheduled end time or duration from start)
                # End only at FULL duration (30 min); never at 90%. Optionally require at least 90% when using scheduled_end (avoid wrong slot).
                time_limit_reached = False
                time_remaining_minutes = 0
                at_least_90_pct = elapsed_minutes >= (interview_duration_minutes * 0.9)

                if scheduled_end_time:
                    # Use scheduled end time if available
                    time_remaining_minutes = (scheduled_end_time - current_time_ist).total_seconds() / 60
                    past_scheduled_end = current_time_ist >= scheduled_end_time
                    # Only end on scheduled_end when at least 90% elapsed (prevents wrong slot/TZ ending early)
                    if past_scheduled_end and at_least_90_pct:
                        time_limit_reached = True
                        logger.info(f"⏰ Interview time limit reached (scheduled end: {scheduled_end_time}, elapsed: {elapsed_minutes:.1f} min)")
                    elif past_scheduled_end and not at_least_90_pct:
                        logger.info(f"⏰ Scheduled end passed but elapsed {elapsed_minutes:.1f} min < 90% - waiting for full duration")
                else:
                    # Use duration from start — end only when full duration reached
                    time_remaining_minutes = interview_duration_minutes - elapsed_minutes
                    if elapsed_minutes >= interview_duration_minutes:
                        time_limit_reached = True
                        logger.info(f"⏰ Interview duration limit reached ({interview_duration_minutes} minutes elapsed)")
                
                # Send time remaining update every 10 seconds (for timer display)
                # Use a simple variable to track last update time
                if 'last_time_update' not in locals():
                    last_time_update = interview_start_time
                
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
                            reliable=False,  # Use unreliable for frequent updates
                        )
                        last_time_update = current_time_ist
                        logger.debug(f"⏰ Sent time remaining update: {time_remaining_minutes:.1f} minutes")
                    except Exception as e:
                        logger.debug(f"⚠️  Failed to send time update: {e}")
                
                # Send 2-minute warning to frontend before time limit
                if not warning_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 2:
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
                        logger.info(f"⚠️  Sent 2-minute warning ({(time_remaining_minutes):.1f} min remaining)")
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to send warning: {e}")
                
                # At ~2 min remaining: tell agent to say "we are wrapping up" and ask final questions (one-time)
                if not wrapping_up_instruction_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 2:
                    wrapping_up_instruction_sent = True
                    try:
                        wrapping_up_instructions = (
                            "SYSTEM: You have about 2 minutes left. "
                            "Tell the candidate we are wrapping up (e.g. 'We have a couple of minutes left' or 'We are coming to the end'). "
                            "Ask one or two final questions from the question bank. Do NOT say full goodbye or thank them for their time yet; save that for when you receive END_INTERVIEW. "
                            "Keep it natural and brief."
                        )
                        await session.generate_reply(instructions=wrapping_up_instructions)
                        logger.info("✅ Sent wrapping-up instruction to agent (~2 min left)")
                        print("⏰ Wrapping-up instruction sent (~2 min left)", flush=True)
                    except Exception as e:
                        logger.warning(f"⚠️  Could not send wrapping-up instruction: {e}")
                
                # At ~1 min remaining: tell agent to say "let us conclude" only — do not ask more questions (one-time)
                if not conclude_instruction_sent and time_remaining_minutes > 0 and time_remaining_minutes <= 1:
                    conclude_instruction_sent = True
                    try:
                        conclude_instructions = (
                            "SYSTEM: You have about 1 minute left. Do NOT ask any more questions. "
                            "Say clearly that we are concluding (e.g. 'We have a minute left, so let us conclude.' or 'That brings us to the end.'). "
                            "One short sentence only. Do NOT say full goodbye yet; you will receive END_INTERVIEW in a moment for that."
                        )
                        await session.generate_reply(instructions=conclude_instructions)
                        logger.info("✅ Sent conclude instruction to agent (~1 min left)")
                        print("⏰ Conclude instruction sent (~1 min left)", flush=True)
                    except Exception as e:
                        logger.warning(f"⚠️  Could not send conclude instruction: {e}")
                
                # Trigger closing only when FULL duration reached (30 min or scheduled end) — not at 90%
                trigger_closing_now = time_limit_reached and not closing_triggered
                if trigger_closing_now:
                    closing_triggered = True
                    interview_time_limit_reached = True
                    logger.info("⏰ Full interview duration reached - ending interview gracefully")
                    print("⏰ Full duration reached - ending interview", flush=True)
                    
                    # One LLM call: agent concludes (goodbye), then we end
                    try:
                        closing_instructions = """SYSTEM: END_INTERVIEW.

You may now conclude the interview. Politely conclude in 2–3 sentences: thank the candidate, say the interview is complete, and that they will be redirected to the evaluation page where they can view results and feedback. Wish them well. Keep it brief and professional."""
                        
                        await session.generate_reply(instructions=closing_instructions)
                        await asyncio.sleep(5)  # Wait for closing message to be fully spoken (increased from 3 to 5 seconds)
                        logger.info("✅ Closing message completed")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not generate closing message: {e}")
                        # Even if message fails, continue with completion
                    
                    # Send completion signal to frontend via data channel
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
                            reliable=True,  # Use reliable for important messages
                        )
                        logger.info("✅ Sent interview completion signal to frontend")
                        print("✅ Sent completion signal to frontend", flush=True)
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to send completion signal: {e}")
                    
                    # Give a moment for the message to be sent, then end gracefully
                    await asyncio.sleep(2)
                    
                    # Update booking status to completed
                    if booking_token:
                        try:
                            from app.services.booking_service import BookingService  # type: ignore
                            booking_service = BookingService(config)
                            booking_service.update_booking_status(booking_token, "completed")
                            logger.info(f"✅ Updated booking status to 'completed' for {booking_token}")
                        except Exception as e:
                            logger.warning(f"⚠️  Failed to update booking status: {e}")
                    
                    # Disconnect from room to end interview
                    try:
                        logger.info("🔌 Disconnecting from room to end interview")
                        await ctx.room.disconnect()
                        logger.info("✅ Successfully disconnected from room")
                    except Exception as e:
                        logger.warning(f"⚠️  Error disconnecting from room: {e}")
                    
                    # Break out of loop to end interview
                    break
                
                # Check time more frequently (every 1 second) when close to time limit
                # This ensures we catch the exact moment time runs out
                if time_remaining_minutes <= 1:
                    await asyncio.sleep(1)  # Check every second when < 1 minute remaining
                else:
                    await asyncio.sleep(5)  # Check every 5 seconds otherwise
                
                # Every 10 seconds, log session state
                if time.time() - last_health_check >= 10:
                    health_msg = f"💓 Session check - agent_state: {session.agent_state}, user_state: {session.user_state}"
                    logger.info(health_msg)
                    print(health_msg, flush=True)
                    room_status = f"   Room connected: {ctx.room.isconnected()}, participants: {len(ctx.room.remote_participants)}"
                    logger.info(room_status)
                    print(room_status, flush=True)
                    if session.current_speech:
                        speech_msg = f"   Current speech active: {session.current_speech is not None}"
                        logger.info(speech_msg)
                        print(speech_msg, flush=True)
                    last_health_check = time.time()
                
                # Periodic health check
                current_time = time.time()
                if current_time - last_health_check >= 30:  # Every 30 seconds
                    elapsed = time.time() - session_start_time
                    participant_count = len(ctx.room.remote_participants)
                    
                    # Show time remaining if limit is set
                    time_remaining = ""
                    if scheduled_end_time:
                        remaining = (scheduled_end_time - current_time_ist).total_seconds() / 60
                        if remaining > 0:
                            time_remaining = f", {remaining:.1f} min remaining"
                    elif interview_duration_minutes:
                        remaining = interview_duration_minutes - elapsed_minutes
                        if remaining > 0:
                            time_remaining = f", {remaining:.1f} min remaining"
                    
                    health_summary = (
                        f"💓 Session health: {elapsed/60:.1f} min elapsed{time_remaining}, "
                        f"{participant_count} participants, "
                        f"room connected: {ctx.room.isconnected()}"
                    )
                    logger.info(health_summary)
                    print(health_summary, flush=True)
                    last_health_check = current_time
                    
                    # Reset error counter on successful health check
                    consecutive_errors = 0
                    
        except KeyboardInterrupt:
            logger.info("🛑 Agent shutdown requested")
            print("\n🛑 Agent shutdown requested", flush=True)
            raise
        except Exception as e:
            consecutive_errors += 1
            elapsed = time.time() - session_start_time
            error_msg = f"[ERR] Loop Error (consecutive: {consecutive_errors}/{max_consecutive_errors}): {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Session duration: {elapsed/60:.1f} minutes", flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            
            # Only stop if too many consecutive errors
            if consecutive_errors >= max_consecutive_errors:
                stop_msg = "[ERR] Too many consecutive errors, stopping session"
                logger.error(stop_msg)
                print(stop_msg, flush=True)
                raise
            else:
                # Continue running despite error
                continue_msg = "[WARN]  Continuing session despite error"
                logger.warning(continue_msg)
                print(continue_msg, flush=True)
                await asyncio.sleep(5)  # Brief pause before continuing
        
        # Step 7: Update booking status and create evaluation after interview completes
        logger.info("Step 7: Finalizing interview...")
        print("Step 7: Finalizing interview...", flush=True)
        
        # Update booking status to completed if not already done
        if booking_token:
            try:
                from app.services.booking_service import BookingService  # type: ignore
                booking_service = BookingService(config)
                booking_service.update_booking_status(booking_token, "completed")
                logger.info(f"✅ Updated booking status to 'completed'")
            except Exception as e:
                logger.warning(f"⚠️  Failed to update booking status: {e}")
        
        # Create evaluation
        logger.info("Step 7b: Creating interview evaluation...")
        print("Step 7b: Creating interview evaluation...", flush=True)
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
                
                # Create evaluation
                evaluation_id = evaluation_service.calculate_evaluation_from_transcript(
                    booking_token=booking_token,
                    room_name=room_name,
                    transcript=transcript,
                )
                
                if evaluation_id:
                    logger.info(f"✅ Evaluation created: {evaluation_id}")
                    print(f"✅ Evaluation created: {evaluation_id}", flush=True)
                else:
                    logger.warning("⚠️  Failed to create evaluation")
            else:
                logger.warning("⚠️  No booking token available, skipping evaluation creation")
        except Exception as e:
            logger.warning(f"⚠️  Error creating evaluation: {e}", exc_info=True)
            print(f"⚠️  Error creating evaluation: {e}", flush=True)
        
        logger.info("=" * 60)
        logger.info("[OK] Entrypoint Finished Successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        error_msg = f"[ERR] Critical error in agent entrypoint: {e}"
        
        # Write to file as backup (in case stdout is redirected)
        try:
            log_file = Path(__file__).parent.parent / "entrypoint_errors.log"
            with open(log_file, "a", encoding="utf-8") as f:
                import traceback
                f.write(f"\n{'='*60}\n")
                f.write(f"ERROR at {asyncio.get_event_loop().time()}\n")
                f.write(f"{error_msg}\n")
                f.write(f"Error type: {type(e).__name__}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
                f.write(f"{'='*60}\n")
        except Exception:
            pass  # Don't fail if file write fails
        
        logger.critical(error_msg)
        logger.error(error_msg, exc_info=True)
        print("\n" + "=" * 60, flush=True, file=sys.stderr)
        print("[ERR][ERR][ERR] CRITICAL ERROR IN ENTRYPOINT [ERR][ERR][ERR]", flush=True, file=sys.stderr)
        print("=" * 60, flush=True, file=sys.stderr)
        print(error_msg, flush=True, file=sys.stderr)
        print(f"   Error type: {type(e).__name__}", flush=True, file=sys.stderr)
        print(f"   Error details: {str(e)}", flush=True, file=sys.stderr)
        print("=" * 60 + "\n", flush=True, file=sys.stderr)
        sys.stderr.flush()
        raise AgentError(f"Agent entrypoint failed: {str(e)}", "my-interviewer")


def _substitute_context_placeholders(context: str, candidate_profile: Optional[dict]) -> str:
    """
    Replace placeholders in dashboard context with candidate profile values.
    E.g. {name} or {full_name} -> candidate name, {email} -> email, etc.
    Uses candidate_profile keys; {name} is aliased to full_name.
    Unknown placeholders are left as-is.
    """
    if not context or not context.strip():
        return context
    subs = {}
    if candidate_profile and isinstance(candidate_profile, dict):
        for k, v in candidate_profile.items():
            if k and isinstance(k, str):
                subs[k] = str(v).strip() if v is not None else ""
        # Alias: {name} -> full_name
        if "full_name" in subs:
            subs["name"] = subs["full_name"]
        elif "full_name" in candidate_profile:
            subs["name"] = str(candidate_profile["full_name"]).strip() if candidate_profile["full_name"] else ""
    # Replace {key} with value for each key in subs
    for key, value in subs.items():
        if key:
            context = context.replace("{" + key + "}", value)
    return context


async def _fetch_candidate_profile(room: rtc.Room, config: Config) -> Optional[dict]:
    """
    Fetch candidate application profile from Supabase using metadata ID.
    
    Args:
        room: LiveKit room instance
        config: App config
        
    Returns:
        Structured dictionary of application data or None
    """
    try:
        if hasattr(room, 'metadata') and room.metadata:
            try:
                metadata = json.loads(room.metadata)
                
                # Check for identifiers in metadata
                form_id = metadata.get('application_form_id') or metadata.get('application_id')
                user_id = metadata.get('user_id') or metadata.get('userId')
                
                # ApplicationFormService not available in current backend
                # form_service = ApplicationFormService(config)
                
                if form_id:
                    logger.info(f"[DEBUG] Application Form ID found: {form_id} (service not available)")
                    # return form_service.get_form_by_id(form_id)
                elif user_id:
                    logger.info(f"[DEBUG] User ID found: {user_id} (service not available)")
                    # return form_service.get_form_by_user_id(user_id)
                else:
                    logger.warning("[WARN]  No 'application_form_id' or 'user_id' found in room metadata")
                    
            except json.JSONDecodeError:
                logger.warning("[WARN]  Could not parse room metadata as JSON")
        else:
            logger.info("📄 APPLICATION STATUS: No metadata found in room")
            
    except Exception as e:
        logger.warning(f"[WARN]  Error fetching candidate profile: {e}")
    
    return None


def _setup_session_event_handlers(
    session: agents.AgentSession,
    logger,
    booking_token: str = None,
    room_name: str = None,
    transcript_storage = None,
    ctx: Optional[JobContext] = None,
) -> None:
    """
    Setup event handlers on AgentSession to track user speech and agent replies.
    
    This helps debug the STT → LLM → TTS pipeline.
    ctx is used to publish user transcripts to the frontend via data channel.
    """
    @session.on("user_state_changed")
    def on_user_state_changed(event):
        try:
            old_state = event.old_state if hasattr(event, 'old_state') else 'unknown'
            new_state = event.new_state if hasattr(event, 'new_state') else 'unknown'
            logger.info(f"👤 [USER STATE] {old_state} → {new_state}")
            print(f"👤 [USER STATE] {old_state} → {new_state}")
            
            if new_state == "speaking":
                logger.info("🎤 [STT] User started speaking (VAD detected)")
                print("🎤 [STT] User started speaking (VAD detected)")
            elif new_state == "listening":
                logger.info("🔇 [STT] User stopped speaking (VAD detected silence)")
                print("🔇 [STT] User stopped speaking (VAD detected silence)")
        except Exception as e:
            logger.debug(f"Error in user_state_changed handler: {e}")
    
    @session.on("agent_state_changed")
    def on_agent_state_changed(event):
        try:
            old_state = event.old_state if hasattr(event, 'old_state') else 'unknown'
            new_state = event.new_state if hasattr(event, 'new_state') else 'unknown'
            logger.info(f"🤖 [AGENT STATE] {old_state} → {new_state}")
            print(f"🤖 [AGENT STATE] {old_state} → {new_state}")
            
            if new_state == "thinking":
                logger.info("💭 [LLM] Agent started thinking (generating reply)")
                print("💭 [LLM] Agent started thinking (generating reply)")
            elif new_state == "speaking":
                logger.info("🔊 [TTS] Agent started speaking (audio playing)")
                print("🔊 [TTS] Agent started speaking (audio playing)")
            elif new_state == "listening":
                logger.info("👂 [AGENT] Agent is listening (ready for user input)")
                print("👂 [AGENT] Agent is listening (ready for user input)")
        except Exception as e:
            logger.debug(f"Error in agent_state_changed handler: {e}")
    
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        try:
            transcript = getattr(event, 'transcript', '') or ''
            is_final = getattr(event, 'is_final', False)
            status = "FINAL" if is_final else "INTERIM"
            logger.info(f"📝 [STT] Transcript ({status}): '{transcript}'")
            print(f"📝 [STT] Transcript ({status}): '{transcript}'")
            
            # Save user transcript to database if final
            if is_final and transcript and transcript_storage and booking_token:
                try:
                    from datetime import datetime
                    # Get current max index to ensure proper ordering
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
                    logger.debug(f"✅ Saved user transcript to database (index: {next_index})")
                except Exception as e:
                    logger.warning(f"Failed to save user transcript: {e}")
            
            # Send final user transcript to frontend via data channel so it shows in transcript UI
            if is_final and transcript and ctx and ctx.room.isconnected():
                try:
                    loop = asyncio.get_running_loop()
                    async def _publish_user_transcript():
                        try:
                            payload = json.dumps({"type": "userTranscript", "message": transcript}).encode("utf-8")
                            await ctx.room.local_participant.publish_data(
                                payload, topic="lk-chat", reliable=True
                            )
                            logger.debug("Sent user transcript to frontend via data channel")
                        except Exception as e:
                            logger.warning(f"Failed to send user transcript to frontend: {e}")
                    loop.create_task(_publish_user_transcript())
                except RuntimeError:
                    logger.debug("No running event loop for user transcript publish (skipping data channel)")
                except Exception as e:
                    logger.warning(f"Could not schedule user transcript send: {e}")
            if is_final:
                logger.info("[OK] [STT] Final transcript received - will trigger LLM")
                print("[OK] [STT] Final transcript received - will trigger LLM")
        except Exception as e:
            logger.error(f"[ERR] Error in user_input_transcribed handler: {e}", exc_info=True)
            print(f"[ERR] Error in user_input_transcribed handler: {e}")
    
    @session.on("error")
    def on_error(event):
        try:
            error_msg = str(event) if event else "Unknown error"
            logger.error(f"[ERR] [SESSION ERROR] {error_msg}")
            print(f"[ERR] [SESSION ERROR] {error_msg}")
        except Exception as e:
            logger.error(f"[ERR] Error in error handler: {e}", exc_info=True)
    
    @session.on("conversation_item_added")
    def on_conversation_item_added(item):
        try:
            role = getattr(item, 'role', 'unknown')
            content = getattr(item, 'content', '')
            logger.info(f"💬 [CONVERSATION] {role.upper()} message added")
            print(f"💬 [CONVERSATION] {role.upper()} message added")
            if role == "user" and content:
                logger.debug(f"   User said: {content}")
        except Exception as e:
            logger.debug(f"Error in conversation_item_added handler: {e}")
    
    @session.on("speech_created")
    def on_speech_created(event):
        try:
            speech_id = getattr(event, 'speech', {}).get('id', 'unknown') if hasattr(event, 'speech') else 'unknown'
            logger.info(f"🗣️  [TTS] Speech created")
            print(f"🗣️  [TTS] Speech created")
        except Exception as e:
            logger.debug(f"Error in speech_created handler: {e}")
    
    @session.on("metrics_collected")
    def on_metrics_collected(event):
        try:
            metrics = getattr(event, 'metrics', None)
            if metrics:
                stt_latency = getattr(metrics, 'stt_latency', 0)
                llm_latency = getattr(metrics, 'llm_latency', 0)
                tts_latency = getattr(metrics, 'tts_latency', 0)
                logger.info(f"📊 [METRICS] STT: {stt_latency:.3f}s, LLM: {llm_latency:.3f}s, TTS: {tts_latency:.3f}s")
                print(f"📊 [METRICS] STT: {stt_latency:.3f}s, LLM: {llm_latency:.3f}s, TTS: {tts_latency:.3f}s")
        except Exception as e:
            logger.debug(f"Error in metrics_collected handler: {e}")
    
    logger.info("[OK] Session event handlers installed for speech tracking")
    print("[OK] Session event handlers installed for speech tracking")


def _setup_participant_handlers(ctx: JobContext, room_sid: str) -> None:
    """
    Setup event handlers for participant and track events.
    
    Args:
        ctx: JobContext instance
        room_sid: Room SID for logging
    """
    room_sid_storage = {"sid": room_sid}
    
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        total = len(ctx.room.remote_participants) + 1
        participant_type = (
            "Agent" if "agent" in participant.identity.lower() else "User"
        )
        
        logger.info("─" * 60)
        logger.info("[OK] NEW PARTICIPANT JOINED")
        logger.info("─" * 60)
        logger.info(f"   Room SID: {room_sid_storage['sid']}")
        logger.info(f"   Room Name: {ctx.room.name}")
        logger.info(f"   Identity: {participant.identity}")
        logger.info(f"   SID: {participant.sid}")
        logger.info(f"   Name: {participant.name}")
        logger.info(f"   Type: {participant_type}")
        logger.info(f"   📊 UPDATED PARTICIPANT COUNT: Total: {total}")
        logger.info("─" * 60)
    
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(
        participant: rtc.RemoteParticipant,
        reason: Optional[str] = None
    ) -> None:
        total = len(ctx.room.remote_participants) + 1
        participant_type = (
            "Agent" if "agent" in participant.identity.lower() else "User"
        )
        
        logger.info("─" * 60)
        logger.info("[ERR] PARTICIPANT LEFT")
        logger.info("─" * 60)
        logger.info(f"   Room SID: {room_sid_storage['sid']}")
        logger.info(f"   Room Name: {ctx.room.name}")
        logger.info(f"   Identity: {participant.identity}")
        logger.info(f"   SID: {participant.sid}")
        logger.info(f"   Name: {participant.name}")
        logger.info(f"   Type: {participant_type}")
        logger.info(f"   Reason: {reason if reason else 'Unknown'}")
        logger.info(f"   📊 UPDATED PARTICIPANT COUNT: Total: {total}")
        logger.info("─" * 60)
    
    @ctx.room.on("track_published")
    def on_track_published(
        publication: rtc.TrackPublication,
        participant: rtc.Participant
    ) -> None:
        track_name = get_track_source_name(publication.source)
        logger.info(f"🎤 TRACK PUBLISHED:")
        logger.info(f"   Participant: {participant.identity}")
        logger.info(f"   Track Type: {track_name}")
        logger.info(f"   Room: {ctx.room.name}")
    
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.Participant
    ) -> None:
        track_name = get_track_source_name(publication.source)
        logger.info(f"👂 TRACK SUBSCRIBED:")
        logger.info(f"   Participant: {participant.identity}")
        logger.info(f"   Track Type: {track_name}")
        logger.info(f"   Room: {ctx.room.name}")


if __name__ == "__main__":
    import sys
    
    logger.info("=" * 60)
    logger.info("[DEV] AGENT WORKER STARTING")
    logger.info("=" * 60)
    
    config = get_config()
    
    # Determine mode from command line arguments
    mode = sys.argv[1] if len(sys.argv) > 1 else "production"
    
    if mode == "console":
        logger.warning("[WARN]  CONSOLE MODE DETECTED - This is for local testing only!")
        logger.warning("[WARN]  Console mode uses mock rooms and won't connect to LiveKit Cloud!")
        print("\n[WARN]  WARNING: Running in CONSOLE MODE (local testing only)")
        print("[WARN]  This won't connect to LiveKit Cloud rooms!\n")
    elif mode == "dev":
        logger.info("[DEV] Running in DEV MODE (connects to LiveKit Cloud)")
        print("[DEV] Running in DEV MODE (connects to LiveKit Cloud)")
    else:
        logger.info("[PROD] Running in PRODUCTION MODE (connects to LiveKit Cloud)")
        print("[PROD] Running in PRODUCTION MODE (connects to LiveKit Cloud)")
    
    logger.info(f"   Agent Name: '{config.livekit.agent_name}'")
    logger.info(f"   Mode: {mode}")
    logger.info(f"   Status: Registering with LiveKit Cloud...")
    logger.info(f"   Waiting for job dispatch...")
    logger.info("=" * 60)
    
    agents.cli.run_app(agents.WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name=config.livekit.agent_name,
    ))

