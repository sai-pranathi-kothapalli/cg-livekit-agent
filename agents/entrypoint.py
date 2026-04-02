"""
LiveKit Agent Entrypoint

Enterprise-grade entrypoint for LiveKit agent jobs with proper
error handling, logging, and plugin management.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta

from livekit import agents, rtc
from livekit.agents import JobContext, AgentSession, room_io
from livekit.plugins import noise_cancellation

# Add backend to Python path so we can import from app (sniff common paths)
from pathlib import Path
_root = Path(__file__).parent.parent.parent
possible_paths = [
    Path("/app/backend"),
    Path("/Interview-Backend"),
    Path("/Livekit-Backend-agent-backend"),
    Path("/backend"),
    _root / "Livekit-Backend-agent-backend",
    _root / "backend",
]

backend_path = None
for p in possible_paths:
    if p.exists():
        backend_path = p
        break

if backend_path and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.config import Config, get_config  # type: ignore
from app.utils.datetime_utils import get_now_ist, to_ist  # type: ignore
from agents.professional_arjun import ProfessionalArjun
try:
    from app.services.plugin_service import PluginService  # type: ignore
except ImportError:
    from services.plugin_service import PluginService
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
                f.write(f"ENTRYPOINT CALLED: {time.time()}\n")
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
        room_name = "unknown"
        try:
            room_name = ctx.room.name
            # Try to extract from room name (format: "interview_<token>" or just token)
            if room_name.startswith("interview_"):
                booking_token = room_name.replace("interview_", "")
            elif len(room_name) == 32 and room_name.replace("_", "").replace("-", "").isalnum():
                booking_token = room_name
            # Try room metadata
            if not booking_token and hasattr(ctx.room, 'metadata') and ctx.room.metadata:
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
        
        # Step 0.5: Initialize Interview State with token
        if booking_token:
            try:
                from services import interview_state
                interview_state.initialize_from_db(booking_token, {})
                logger.info(f"   [OK] Booking token identified: {booking_token}")
                logger.info("[OK] Interview state initialized with booking token")
                print(f"   [OK] Booking token identified", flush=True)
            except Exception as e:
                logger.warning(f"Failed to initialize interview state token: {e}")
        
        # Step 1: Connect to room
        logger.info("📡 CONNECTION PROCESS: Step 1 - Connecting to room...")
        print("📡 CONNECTION PROCESS: Step 1 - Connecting to room...", flush=True)
        try:
            await ctx.connect()
            logger.info("[OK] Step 1: Success - Connected to room!")
            print("[OK] Step 1: Success - Connected to room!", flush=True)

            # Safety net: if somehow another agent is already here, exit immediately
            # This should never happen with the pre-acceptance checks, but just in case
            from agent import release_room
            await asyncio.sleep(1.0)  # Wait for participant list to fully propagate
            agent_count = sum(
                1 for p in ctx.room.remote_participants.values()
                if p.identity and p.identity.startswith("agent-")
            )
            if agent_count > 0:
                logger.critical(
                    f"[SAFETY NET] Another agent detected in room after connecting. "
                    f"This should not happen — pre-acceptance checks may have failed. "
                    f"Self-terminating to prevent duplicate."
                )
                print(f"[SAFETY NET] Another agent detected. Self-terminating.", flush=True)
                release_room(room_name)  # Clean up tracking
                return
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
        
        # Step 2: Fetch candidate application form from DB (for {full_name}, {email}, etc. in context)
        logger.info("Step 2: Fetching Candidate Application Data...")
        print("Step 2: Fetching Candidate Application Data...", flush=True)
        from services.candidate_profile import fetch_candidate_profile
        candidate_profile = await fetch_candidate_profile(ctx.room, config, booking_token=booking_token)
        
        # Step 2b: Fetch System Instructions & Booking Prompt
        logger.info("Step 2b: Fetching System Instructions & Booking Prompt...")
        print("Step 2b: Fetching System Instructions & Booking Prompt...", flush=True)
        
        system_instructions = ""
        booking_prompt = ""
        
        # 1. Get Global System Instructions
        try:
            from app.services.system_instructions_service import SystemInstructionsService  # type: ignore
            si_service = SystemInstructionsService(config)
            si_data = si_service.get_system_instructions()
            system_instructions = si_data.get("instructions", "")
            logger.info(f"[OK] System instructions fetched (length={len(system_instructions)})")
        except Exception as e:
            logger.warning(f"[WARN] Failed to fetch system instructions: {e}")
            print(f"[WARN] Failed to fetch system instructions: {e}", flush=True)

        # 2. Get Booking Specific Prompt
        if booking_token:
            try: 
                # Re-use booking service if possible, or create new
                from app.services.booking_service import BookingService  # type: ignore
                booking_service = BookingService(config)
                booking = booking_service.get_booking(booking_token)
                if booking and booking.get("prompt"):
                    booking_prompt = booking.get("prompt")
                    logger.info(f"[OK] Found custom prompt for this interview (length={len(booking_prompt)})")
                    print(f"[OK] Found custom prompt for this interview", flush=True)
            except Exception as e:
                logger.warning(f"[WARN] Failed to fetch booking prompt: {e}")

        # Step 3: Setup participant event handlers
        logger.info("Step 3: Setting up participant event handlers...")
        print("Step 3: Setting up participant event handlers...", flush=True)
        from handlers.event_handlers import setup_participant_handlers
        setup_participant_handlers(ctx, room_sid, logger_instance=logger)
        
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
        plugins = {}
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
            
            # Step 4.5: Load existing interview state from DB if it exists
            if booking_token:
                try:
                    from app.services.evaluation_service import EvaluationService
                    eval_service = EvaluationService(config)
                    evaluation = eval_service.get_evaluation(booking_token)
                    if evaluation and evaluation.get("interview_state"):
                        from services import interview_state
                        db_state = evaluation.get("interview_state")
                        interview_state.initialize_from_db(booking_token, db_state)
                        logger.info(f"[OK] Loaded existing interview state from DB: {len(db_state.get('code_submissions', []))} submissions found")
                        print(f"[OK] Restored past session state from database", flush=True)
                except Exception as e:
                    logger.warning(f"Failed to load existing interview state: {e}")
        except Exception as e:
            logger.warning(f"Could not get transcript storage service: {e}")
        
        # Interview timing: timer starts when candidate sends first message (see interview_loop).
        # Placeholder start; loop will set resolved_start_time when candidate joins.
        interview_start_time = None
        slot_start_ist_loop = None  # For join-delay: when slot/booking was scheduled to start
        scheduled_duration_minutes = 30  # 30 or 45 for phase template
        
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
                            if slot:
                                # Prefer explicit duration_minutes (Supabase may return int or string)
                                slot_duration = slot.get('duration_minutes')
                                if slot_duration is not None:
                                    try:
                                        d = int(float(slot_duration))
                                        if d >= 15:
                                            interview_duration_minutes = d
                                            logger.info(f"⏰ Using slot duration_minutes: {interview_duration_minutes} minutes (from slot {slot_id})")
                                        else:
                                            logger.warning(f"⏰ Slot duration_minutes={d} < 15; will enforce 30 min")
                                    except (TypeError, ValueError):
                                        logger.warning(f"⏰ Slot duration_minutes not usable: {slot_duration!r}, using default 30")
                                elif slot.get('end_time'):
                                    # Fallback: calculate from slot start/end (can be affected by timezone/booking values)
                                    slot_start_str = slot.get('start_time') or slot.get('slot_datetime')
                                    slot_end_str = slot.get('end_time')
                                    if slot_start_str and slot_end_str:
                                        try:
                                            slot_start = datetime.fromisoformat(slot_start_str.replace('Z', '+00:00'))
                                            slot_end = datetime.fromisoformat(slot_end_str.replace('Z', '+00:00'))
                                            slot_start_ist = to_ist(slot_start)
                                            slot_end_ist = to_ist(slot_end)
                                            duration_seconds = (slot_end_ist - slot_start_ist).total_seconds()
                                            interview_duration_minutes = int(duration_seconds / 60)
                                            logger.info(f"⏰ Using duration from slot start/end: {interview_duration_minutes} minutes (slot {slot_id}; no duration_minutes on slot)")
                                        except Exception as e:
                                            logger.warning(f"Could not parse slot times: {e}")
                                if slot.get('end_time'):
                                    try:
                                        slot_end_str = slot.get('end_time')
                                        slot_start_str = slot.get('start_time') or slot.get('slot_datetime')
                                        if slot_end_str:
                                            slot_end = datetime.fromisoformat(slot_end_str.replace('Z', '+00:00'))
                                            scheduled_end_time = to_ist(slot_end)
                                        if slot_start_str:
                                            slot_start = datetime.fromisoformat(slot_start_str.replace('Z', '+00:00'))
                                            slot_start_ist_loop = to_ist(slot_start)
                                    except Exception:
                                        pass
                                    # Minimum check moved below to global scope
                                    pass
                                if scheduled_end_time:
                                    logger.info(f"⏰ Slot end at IST {scheduled_end_time} (duration={interview_duration_minutes} min)")
                            else:
                                logger.warning(f"Slot not found: {slot_id}")
                        except Exception as e:
                            logger.warning(f"Could not fetch slot: {e}")
                    
                    # If no slot duration, use scheduled_at / slot_datetime + default duration
                    if not scheduled_end_time and (booking.get('scheduled_at') or booking.get('slot_datetime')):
                        scheduled_at_str = booking.get('scheduled_at') or booking.get('slot_datetime')
                        try:
                            if 'Z' in scheduled_at_str or '+00:00' in scheduled_at_str:
                                scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
                            else:
                                scheduled_at = datetime.fromisoformat(scheduled_at_str)
                            scheduled_at_ist = to_ist(scheduled_at)
                            slot_start_ist_loop = scheduled_at_ist  # For late-join calculation
                            # Default interview duration: 30 minutes; end time in IST for correct comparison
                            scheduled_end_time = scheduled_at_ist + timedelta(minutes=interview_duration_minutes)
                            logger.info(f"⏰ Interview scheduled: {scheduled_at_ist} IST, will end at: {scheduled_end_time} ({interview_duration_minutes} min duration)")
                        except Exception as e:
                            logger.warning(f"Could not parse scheduled_at: {e}, using default duration")
            except Exception as e:
                logger.warning(f"Could not fetch booking for duration: {e}")
        
        # --- GLOBAL DURATION ENFORCEMENT ---
        # Ensure interview_duration_minutes is at least 30, regardless of how it was retrieved.
        if interview_duration_minutes < 30:
            logger.info(f"⏰ Enforcing 30-min minimum (was {interview_duration_minutes} min)")
            interview_duration_minutes = 30
            # Recalculate scheduled_end_time if we have a start time
            if slot_start_ist_loop:
                scheduled_end_time = slot_start_ist_loop + timedelta(minutes=30)

        # Phase template: 30 or 45 minutes (for dynamic phase allocation when candidate joins)
        scheduled_duration_minutes = 45 if interview_duration_minutes >= 45 else 30
        
        # Ensure int everywhere (DB may return int/float; agent and loop expect whole minutes)
        interview_duration_minutes = int(interview_duration_minutes)
        scheduled_duration_minutes = int(scheduled_duration_minutes)
        
        logger.info(f"============================================================")
        logger.info(f"RESOLVED INTERVIEW DURATION: {interview_duration_minutes} MINUTES")
        if scheduled_end_time:
             logger.info(f"SCHEDULED TO END AT: {scheduled_end_time} IST")
        logger.info(f"============================================================")
        print(f"⏰ RESOLVED INTERVIEW DURATION: {interview_duration_minutes} MINUTES", flush=True)

        if scheduled_end_time:
            logger.info(f"⏰ Interview time limit: {interview_duration_minutes} minutes (ends at {scheduled_end_time}); timer starts when candidate joins")
        else:
            logger.info(f"⏰ Using default interview duration: {interview_duration_minutes} minutes from start; timer starts when candidate joins")
        
        # Session time store is set by interview_loop when candidate joins (so timer starts on join)
        
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
        logger.info("Step 6: Creating AgentSession...")
        print("Step 6: Creating AgentSession...", flush=True)
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
                min_endpointing_delay=2.0,
            )
            logger.info("[OK] Step 6: Success - AgentSession created!")
            print("[OK] Step 6: Success - AgentSession created!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 6: Failed to create AgentSession - {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg, flush=True)
            print(f"   Error type: {type(e).__name__}", flush=True)
            raise
        
        # Step 7: Start session
        logger.info("Step 7: Starting session...")
        print("Step 7: Starting session...", flush=True)
        
        # Assemble Agent Instructions
        agent_instructions = system_instructions or ""
        
        if booking_prompt:
            agent_instructions += f"\n\nIMPORTANT INTERVIEW INSTRUCTIONS FROM RECRUITER:\n{booking_prompt}"

        # Reinforce: never conclude based on question count (overrides any recruiter "3-4 questions" type guidance)
        agent_instructions += (
            "\n\n[INTERNAL — DO NOT SPEAK OR QUOTE THE FOLLOWING RULES]\n"
            "REMINDER: Do NOT conclude the interview based on question count. "
            "Having asked 3, 5, 8, or any number of questions does NOT mean the interview is over. "
            "Only the backend sends END_INTERVIEW when time expires. Continue asking until then.\n\n"
            "CONDITIONAL CODING: Ask coding/technical questions ONLY if the role requires technical evaluation "
            "or the interview type includes coding or programming problems (e.g. recruiter instructions or prompt mention technical/coding evaluation or programming problems). "
            "Programming problems means you should ask coding questions. Otherwise skip the coding phase and use that time for MCQ and logical reasoning.\n"
            "[END INTERNAL CONTEXT]"
        )
        # Detect if coding is required based on keywords requested by user: python, java, sql, code, c
        _prompt_lower = ((agent_instructions or "") + (booking_prompt or "")).lower()
        _technical_keywords = ("python", "java", "sql", "code", "c ", " c ", "cpp", "javascript", "typescript", "coding", "programming")
        requires_coding_logic = any(kw in _prompt_lower for kw in _technical_keywords)

        if requires_coding_logic:
            agent_instructions += (
                "\n\n[INTERNAL — DO NOT SPEAK OR QUOTE THE FOLLOWING RULES]\n"
                "REQUIRED: This interview mentions programming, coding, or a programming language (e.g. Java, Python). You MUST ask at least one live coding question. "
                "Ask it during the technical phase. Guide the candidate to open the code editor (</> in the bottom bar). "
                "Do not skip the coding question; even in a short interview, include one coding problem.\n"
                "[END INTERNAL CONTEXT]"
            )
            logger.info("[OK] Custom prompt contains coding-related keyword; REQUIRED: at least one live coding question")
        else:
            logger.info("[INFO] No coding keywords found; skipping mandatory coding requirement.")

        if not system_instructions:
            error_msg = (
                "❌ [NO SYSTEM INSTRUCTIONS] The dashboard has no system instructions configured. "
                "Please add system instructions in the dashboard before starting an interview. "
                "The interview cannot proceed without instructions."
            )
            logger.critical(error_msg)
            print(error_msg, flush=True)
            raise RuntimeError(
                "No system instructions found. Configure system instructions in the dashboard and retry."
            )

        logger.info(
            "[OK] Using dashboard instructions: system_instructions + custom prompt (booking_prompt). "
            "Interview will follow these."
        )
        print("[OK] Using system instructions + custom prompt for this interview", flush=True)
        
        # Substitute placeholders (e.g. {name}, {full_name}, {email}) from candidate profile
        if agent_instructions:
            try:
                from utils.prompt_utils import substitute_context_placeholders
                agent_instructions = substitute_context_placeholders(agent_instructions, candidate_profile)
            except Exception as e:
                logger.warning(f"Failed to substitute placeholders: {e}")

            preview = (agent_instructions[:120] + "…") if len(agent_instructions) > 120 else agent_instructions
            logger.info(f"[OK] Agent context prepared, length={len(agent_instructions)}, preview: {preview!r}")
            print(f"[OK] Agent context prepared: length={len(agent_instructions)}", flush=True)
            
        try:
            agent = ProfessionalArjun(
                candidate_profile=candidate_profile,
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
        from handlers.event_handlers import setup_session_event_handlers
        setup_session_event_handlers(
            session, logger, booking_token, room_name, transcript_storage, ctx
        )
        
        # Data channel handlers (code-submission, monitoring, code-snapshot, code-idle)
        try:
            from handlers.data_handlers import setup_data_handlers
            setup_data_handlers(ctx.room, session, logger_instance=logger)
        except ImportError as e:
            logger.warning(f"Could not load data handlers (coding features disabled): {e}")
        
        # Step 7: Wait for participant to join, then start session
        logger.info("Step 7: Waiting for participant to join room...")
        print("Step 7: Waiting for participant to join room...")
        max_wait_time = 5
        wait_interval = 1
        waited = 0
        while not ctx.room.remote_participants and waited < max_wait_time:
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            if waited % 5 == 0:
                logger.info(f"   Waiting for participant... ({waited}s/{max_wait_time}s)")
                print(f"   Waiting for participant... ({waited}s/{max_wait_time}s)")
        if ctx.room.remote_participants:
            participant_count = len(ctx.room.remote_participants)
            logger.info(f"[OK] Participant(s) detected: {participant_count} remote participant(s) in room")
            print(f"[OK] Participant(s) detected: {participant_count} remote participant(s) in room")
            for participant in ctx.room.remote_participants.values():
                logger.info(f"   👤 Participant: identity={participant.identity}, sid={participant.sid}")
                print(f"   👤 Participant: identity={participant.identity}, sid={participant.sid}")
        else:
            logger.warning(f"[WARN]  No participants joined after {max_wait_time}s (will greet when they join)")
            print(f"[WARN]  No participants joined after {max_wait_time}s (will greet when they join)")
        
        # Start session - greeting will be generated AFTER start (generate_reply requires session to be running)
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
                    close_on_disconnect=False,
                ),
            )
            logger.info("[OK] Step 7: Success - Session started with BVC noise cancellation!")
            print("[OK] Step 7: Success - Session started with BVC noise cancellation!", flush=True)
        except Exception as e:
            error_msg = f"[ERR] Step 7: Failed to start session - {e}"
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
        
        # Step 7.5: Start LiveAvatar (HeyGen) - falls back to static avatar automatically
        try:
            avatar_session = await plugin_service.start_live_avatar(session, ctx.room)
            if avatar_session:
                logger.info("[OK] LiveAvatar active - video track published")
                print("[OK] LiveAvatar active", flush=True)
            else:
                logger.info("[INFO] LiveAvatar not configured - using static avatar fallback")
                print("[INFO] Using static avatar fallback (LiveAvatar not configured)", flush=True)
        except Exception as e:
            logger.warning(f"[WARN] LiveAvatar initialization error (using static avatar): {e}")
            print(f"[WARN] LiveAvatar failed - using static avatar fallback", flush=True)
        
        # Step 7c: Load history and determine if we should skip greeting
        history_loaded = False
        if booking_token and transcript_storage:
            try:
                logger.info(f"[HISTORY] Checking for existing transcript for {booking_token}...")
                past_messages = transcript_storage.get_transcript(booking_token)
                if past_messages and len(past_messages) > 0:
                    logger.info(f"[HISTORY] Found {len(past_messages)} past messages. Loading into history manager...")
                    # Dive into the wrapped chat to find the history manager
                    # plugins["llm"].chat is TimingLLMWrapper
                    # timing_wrapper._original_chat is HistoryManagedLLMWrapper
                    llm_chat = plugins["llm"].chat
                    history_wrapper = getattr(llm_chat, "_original_chat", None)
                    if history_wrapper:
                        history_manager = getattr(history_wrapper, "_history_manager", None)
                        if history_manager:
                            # Sort by index to ensure order
                            sorted_messages = sorted(past_messages, key=lambda x: x.get('index', 0) if x.get('index') is not None else 0)
                            for msg in sorted_messages:
                                history_manager.add_message(msg['role'], msg['content'])
                            history_loaded = True
                            logger.info(f"[HISTORY] Successfully loaded {len(sorted_messages)} messages.")
                            print(f"[HISTORY] Loaded {len(sorted_messages)} past messages - resuming interview", flush=True)
            except Exception as e:
                logger.warning(f"[HISTORY] Failed to load past history: {e}")
                print(f"[HISTORY] Warning: Could not load past history ({e})", flush=True)

        # Step 7b: Generate initial greeting (AFTER session.start - generate_reply requires session to be running)
        if ctx.room.remote_participants and not history_loaded:
            logger.info("[GREETING] Generating initial greeting (session is now running)...")
            print("[GREETING] Generating initial greeting...", flush=True)
            try:
                from app.services.history_managed_llm_wrapper import set_skip_transcript
                from services.time_context_llm_wrapper import generate_reply_with_instructions
                set_skip_transcript(True)
                greeting_instruction = (
                    "[INTERNAL — DO NOT READ ALOUD. This is your first turn instructions.]\n"
                    "Deliver ONLY the opening of the interview:\n"
                    "1. Greet the candidate warmly (use their name if available) and introduce yourself briefly.\n"
                    "2. Ask exactly ONE opening question — invite them to introduce themselves "
                    "(e.g. 'Tell me a bit about yourself and what you've been working on recently.').\n"
                    "YOUR RESPONSE MUST END AFTER THAT ONE QUESTION. Nothing else.\n"
                    "Do NOT ask a second question. Do NOT say 'also', 'and', or add any follow-up.\n"
                    "Do NOT say 'thanks', 'great', or any filler after asking.\n"
                    "Do NOT mention phases, MCQs, coding, or what comes later.\n"
                    "Do NOT say goodbye or any closing phrase.\n"
                    "Keep it warm, brief, and professional. Speak naturally — no brackets or labels.\n"
                    "[END INTERNAL CONTEXT]"
                )
                await asyncio.wait_for(
                    generate_reply_with_instructions(session, instructions=greeting_instruction),
                    timeout=60.0
                )
                set_skip_transcript(False)
                logger.info("[GREETING] Success - Agent greeted first!")
                print("[GREETING] Success - Agent greeted first!", flush=True)
            except asyncio.TimeoutError:
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(False)
                logger.error("[GREETING] Failed - generate_reply timed out after 60 seconds")
                print("[GREETING] Failed - timed out", flush=True)
            except Exception as e:
                from app.services.history_managed_llm_wrapper import set_skip_transcript  # type: ignore
                set_skip_transcript(False)
                logger.error(f"[GREETING] Failed - {e}", exc_info=True)
                print(f"[GREETING] Failed - {e}", flush=True)
        elif history_loaded:
            logger.info("[GREETING] Skipped greeting - resumed conversation history.")
            print("[GREETING] Resuming conversation - skipping initial greeting.", flush=True)
        else:
            logger.info("[GREETING] Skipped - no participant in room")
            print("[GREETING] Skipped - no participant in room", flush=True)
        
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
        
        logger.info("--- Entrypoint Active (Interview in progress) ---")
        logger.info("💡 The AgentSession will automatically handle user speech and generate replies")
        logger.info("💡 Event handlers are installed to log all speech events")
        print("--- Entrypoint Active (Interview in progress) ---")
        print("💡 AgentSession is listening for user speech automatically")

        logger.info(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        logger.info(f"[DEBUG] Session agent_state: {session.agent_state}, user_state: {session.user_state}")
        print(f"[DEBUG] Room monitoring started - connected: {ctx.room.isconnected()}, remote_participants: {len(ctx.room.remote_participants)}")
        print(f"[DEBUG] Session state: agent={session.agent_state}, user={session.user_state}")

        from services.interview_loop import run_interview_time_loop
        await run_interview_time_loop(
            ctx=ctx,
            session=session,
            interview_start_time=interview_start_time,
            interview_duration_minutes=interview_duration_minutes,
            scheduled_end_time=scheduled_end_time,
            booking_token=booking_token,
            room_name=room_name,
            plugins=plugins,
            config=config,
            slot_start_ist=slot_start_ist_loop,
            scheduled_duration_minutes=scheduled_duration_minutes,
            requires_coding=requires_coding_logic,
        )

        logger.info("=" * 60)
        logger.info("[OK] Entrypoint Finished Successfully")
        logger.info("=" * 60)
        
        # Wait for any pending tasks
        await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.warning("🛑 Agent task cancelled (room probably closed)")
        print("🛑 Agent task cancelled", flush=True)
    except Exception as e:
        error_msg = f"[ERR] Critical error in agent entrypoint: {e}"
        
        # Write to file as backup (in case stdout is redirected)
        try:
            log_file = Path(__file__).parent.parent / "entrypoint_errors.log"
            with open(log_file, "a", encoding="utf-8") as f:
                import traceback
                f.write(f"\n{'='*60}\n")
                f.write(f"ERROR at {time.time()}\n")
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
    finally:
        # ALWAYS release the room, even if the agent crashes
        try:
            from agent import release_room
            if room_name and room_name != "unknown":
                release_room(room_name)
                logger.info(f"Agent finished and released room {room_name}")
        except Exception:
            pass
