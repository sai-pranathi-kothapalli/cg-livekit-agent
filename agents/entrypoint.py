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
from typing import Optional

from livekit import agents, rtc
from livekit.agents import JobContext, AgentSession, room_io
from livekit.plugins import noise_cancellation

# Add backend to Python path so we can import from app
import sys
from pathlib import Path
backend_path = Path(__file__).parent.parent.parent / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.config import Config, get_config  # type: ignore
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
        
        # Log job details with CRITICAL level
        logger.critical(f"[INFO] JOB DETAILS:")
        logger.critical(f"   Job ID: {ctx.job.id}")
        logger.critical(f"   Room Name: {ctx.room.name}")
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
            plugins = await plugin_service.initialize_plugins(ctx.room)
            logger.info("[OK] Step 4: Plugins initialized successfully!")
            print("[OK] Step 4: Plugins initialized successfully!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 4: Failed to initialize plugins - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            raise
        
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
        
        # Fetch dynamic agent instructions
        try:
            from app.services.prompt_service import get_prompt_service  # type: ignore
            prompt_service = get_prompt_service(config)
            agent_instructions = await prompt_service.get_prompt("agent_persona_arjun")
            
            if not agent_instructions:
                logger.warning("[WARN]  Failed to fetch agent instructions from DB, using fallback")
                print("[WARN]  Failed to fetch agent instructions from DB, using fallback", flush=True)
        except Exception as e:
            logger.warning(f"[WARN]  Error fetching agent instructions: {e}, using fallback")
            print(f"[WARN]  Error fetching agent instructions: {e}, using fallback", flush=True)
            agent_instructions = None
            
        try:
            agent = ProfessionalArjun(
                candidate_profile=candidate_profile,
                job_description=jd_data,
                base_instructions=agent_instructions if agent_instructions else None
            )
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
        _setup_session_event_handlers(session, logger)
        
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
        
        # Log session state
        logger.info(f"[DEBUG] Session state check:")
        logger.info(f"   Agent state: {session.agent_state}")
        logger.info(f"   User state: {session.user_state}")
        logger.info(f"   Current speech: {session.current_speech is not None}")
        print(f"[DEBUG] Session state: agent={session.agent_state}, user={session.user_state}")
        
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
                # Set flag to skip transcript for greeting
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(True)
                
                logger.info("   Calling session.generate_reply() for greeting...")
                print("   Calling session.generate_reply() for greeting...")
                
                await session.generate_reply(
                    instructions="""
                    As Alyza, start the interview with a professional, welcoming opening:
                    - Introduce yourself warmly: "Hello! I am Alyza, a professional Banking Interviewer." (Ensure NO brackets are used).
                   
                    - Ask ONLY ONE simple question: "To begin, could you please tell me a bit about yourself and your educational background?"
                    - Keep it professional, clear, and encouraging - maintain a formal yet approachable tone.
                    - Show genuine interest in their learning journey.
                    - Make them feel comfortable and supported.
                    - CRITICAL: Ask only ONE question. Wait for their response before asking about interests or projects.
                    """
                )
                
                # Reset flag after greeting
                set_skip_transcript(False)
                logger.info("[OK] Step 6b: Success - Greeting generated! (transcript skipped)")
                print("[OK] Step 6b: Success - Greeting generated! (transcript skipped)")
                
                # CRITICAL: Verify session is ready to listen after greeting
                await asyncio.sleep(1)  # Brief pause for state to update
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
        
        import time
        session_start_time = time.time()
        last_health_check = time.time()
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        # Log initial room state
        logger.info(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        logger.info(f"[DEBUG] Session agent_state: {session.agent_state}, user_state: {session.user_state}")
        print(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        print(f"[DEBUG] Session state: agent={session.agent_state}, user={session.user_state}")
        
        try:
            while ctx.room.isconnected():
                # Log session state periodically to see if it's responding
                await asyncio.sleep(5)
                
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
                    health_summary = (
                        f"💓 Session health: {elapsed/60:.1f} min elapsed, "
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


def _setup_session_event_handlers(session: agents.AgentSession, logger) -> None:
    """
    Setup event handlers on AgentSession to track user speech and agent replies.
    
    This helps debug the STT → LLM → TTS pipeline.
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

