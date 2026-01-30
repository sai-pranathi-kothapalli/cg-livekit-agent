"""
Legacy Agent Entry Point

This file is maintained for backward compatibility.
It imports and runs the new enterprise-structured agent entrypoint.
"""

# Load environment variables
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add backend to Python path FIRST so we can import from app (try both folder names)
_root = Path(__file__).parent.parent
backend_path = _root / "Livekit-Backend-agent-backend"
if not backend_path.exists():
    backend_path = _root / "backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
    print(f"[INFO] Backend path added: {backend_path}", flush=True)
else:
    print(f"[WARNING] Backend not found at {_root / 'Livekit-Backend-agent-backend'} or {_root / 'backend'}", flush=True)

# Try loading from different possible locations (backend .env has GEMINI_API_KEY etc.)
root_env_path = _root / ".env.local"
backend_env_path = _root / "Livekit-Backend-agent-backend" / ".env"
if not backend_env_path.exists():
    backend_env_path = _root / "backend" / ".env"

if backend_env_path.exists():
    print(f"[INFO] Loading environment from {backend_env_path}", flush=True)
    load_dotenv(backend_env_path, override=True)
elif root_env_path.exists():
    print(f"[INFO] Loading environment from {root_env_path}", flush=True)
    load_dotenv(root_env_path, override=True)
else:
    print("[WARNING] No .env found in Livekit-Backend-agent-backend or .env.local - GEMINI_API_KEY may be missing!", flush=True)

# NOW import other modules (after backend path is set and environment is loaded)
from agents.entrypoint import entrypoint
from livekit import agents
from livekit.agents import JobRequest  # type: ignore
from app.config import get_config  # type: ignore

# Don't create logger here - it will be created AFTER logging is configured
# logger = get_logger(__name__)  # MOVED BELOW


async def job_request_handler(req: JobRequest) -> None:
    """
    Handle job requests from LiveKit Cloud.
    
    CRITICAL: This function must accept/reject IMMEDIATELY.
    Heavy work (logging, config loading) happens AFTER acceptance.
    """
    # CRITICAL: Use print with flush FIRST - this will ALWAYS appear
    # Even if logging is broken, these prints will show
    import sys
    print(f"\n[DEBUG] [JOB] Job Request Received! ID: {req.job.id}, Room: {req.job.room.name}", flush=True)
    sys.stdout.flush()
    
    # Extract basic info quickly (no config loading yet)
    job_id = req.job.id
    room_name = req.job.room.name
    room_sid = req.job.room.sid
    
    # Extract agent name from job if available (fast operation)
    agent_name_in_job = None
    try:
        if hasattr(req.job, 'agent_name'):
            agent_name_in_job = req.job.agent_name
        elif hasattr(req, 'agent_name'):
            agent_name_in_job = req.agent_name
    except Exception:
        pass
    
    # CRITICAL PRINT - This MUST appear if job is received
    # Write to file as backup
    try:
        from pathlib import Path
        log_file = Path(__file__).parent / "job_requests.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"JOB REQUEST RECEIVED: {job_id}\n")
            f.write(f"Room: {room_name}, SID: {room_sid}\n")
            f.write(f"Agent Name: {agent_name_in_job if agent_name_in_job else 'NOT SPECIFIED'}\n")
            f.write(f"{'='*60}\n")
    except Exception:
        pass
    
    print("\n" + "=" * 60, flush=True)
    print("[JOB][JOB][JOB] JOB REQUEST RECEIVED FROM LIVEKIT CLOUD [JOB][JOB][JOB]", flush=True)
    print("=" * 60, flush=True)
    print(f"   Job ID: {job_id}", flush=True)
    print(f"   Room Name: {room_name}", flush=True)
    print(f"   Room SID: {room_sid}", flush=True)
    print(f"   Agent Name (in job): {agent_name_in_job if agent_name_in_job else 'NOT SPECIFIED'}", flush=True)
    print("=" * 60, flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Import logger here to ensure it's available (logging should be configured by now)
    import logging
    logger = logging.getLogger(__name__)
    
    # Force logger to show - set level to ensure visibility
    logger.setLevel(logging.DEBUG)
    
    # ACCEPT IMMEDIATELY - don't wait for config or heavy logging!
    # LiveKit has a timeout (~7 seconds) for job assignment after accept()
    # Use CRITICAL level to ensure it shows up
    logger.critical(f"[JOB] Job request received: {job_id}, Room: {room_name}")
    logger.info(f"[JOB] Job request received: {job_id}, Room: {room_name}")
    print(f"[JOB] Accepting job: {job_id}", flush=True)
    sys.stdout.flush()
    
    try:
        await req.accept()
        accept_msg = f"[OK] Job ACCEPTED: {job_id}"
        logger.critical(accept_msg)  # Use CRITICAL to ensure visibility
        logger.info(accept_msg)
        print(f"[OK][OK][OK] Job ACCEPTED: {job_id} - Entrypoint will be called!", flush=True)
        print("=" * 60 + "\n", flush=True)
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"[ERR] Failed to accept job {job_id}: {e}", exc_info=True)
        print(f"[ERR][ERR][ERR] FAILED TO ACCEPT JOB: {e}", flush=True)
        print("=" * 60 + "\n", flush=True)
        raise
    
    # NOW do heavy work (logging, config) AFTER acceptance
    try:
        config = get_config()
        
        # Detailed logging after acceptance
        print("\n" + "=" * 60)
        print("[JOB] JOB REQUEST DETAILS")
        print("=" * 60)
        logger.info("=" * 60)
        logger.info("[JOB] JOB REQUEST DETAILS")
        logger.info("=" * 60)
        
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   Room Name: {room_name}")
        logger.info(f"   Room SID: {room_sid}")
        logger.info(f"   Agent Name (worker expects): {config.livekit.agent_name}")
        logger.info(f"   Agent Name (in job): {agent_name_in_job if agent_name_in_job else 'NOT SPECIFIED'}")
        logger.info(f"   Dispatch ID: {req.job.dispatch_id}")
        
        resuming_status = getattr(req, 'resuming', 'N/A')
        logger.info(f"   Resuming: {resuming_status}")
        
        print(f"   Job ID: {job_id}")
        print(f"   Room Name: {room_name}")
        print(f"   Room SID: {room_sid}")
        print(f"   Agent Name (worker expects): {config.livekit.agent_name}")
        print(f"   Agent Name (in job): {agent_name_in_job if agent_name_in_job else 'NOT SPECIFIED'}")
        print(f"   Dispatch ID: {req.job.dispatch_id}")
        print(f"   Resuming: {resuming_status}")
        
        # Check for agent name mismatch
        if agent_name_in_job and agent_name_in_job != config.livekit.agent_name:
            logger.warning(f"   [WARN]  AGENT NAME MISMATCH!")
            logger.warning(f"      Worker expects: '{config.livekit.agent_name}'")
            logger.warning(f"      Job requests: '{agent_name_in_job}'")
            print(f"   [WARN]  AGENT NAME MISMATCH!")
            print(f"      Worker expects: '{config.livekit.agent_name}'")
            print(f"      Job requests: '{agent_name_in_job}'")
        else:
            logger.info(f"   [OK] Agent name matches (or not specified in job)")
            print(f"   [OK] Agent name matches (or not specified in job)")
        
        logger.info("[OK] Job request ACCEPTED - entrypoint will be called")
        print("[OK] Job request ACCEPTED - entrypoint will be called")
        print("=" * 60 + "\n")
    except Exception as e:
        # Logging errors shouldn't prevent job from proceeding
        logger.warning(f"[WARN]  Error in post-accept logging: {e}", exc_info=True)
        print(f"[WARN]  Error in post-accept logging: {e}")

if __name__ == "__main__":
    # Monkey-patch IPC log listener to avoid crash on incompatible pickle
    # (e.g. TypeError: __init__() missing 2 required keyword-only arguments: 'request' and 'response')
    try:
        import pickle
        from livekit.agents.utils.aio import duplex_unix as _duplex_unix
        from livekit.agents.ipc import log_queue

        def _patched_monitor(self):
            while True:
                try:
                    data = self._duplex.recv_bytes()
                except _duplex_unix.DuplexClosed:
                    break
                try:
                    record = pickle.loads(data)
                    self.handle(record)
                except (TypeError, AttributeError):
                    continue

        log_queue.LogQueueListener._monitor = _patched_monitor
    except Exception:
        pass

    # CRITICAL: Don't configure logging here - LiveKit will do it
    # Just ensure stdout is unbuffered so print statements appear immediately
    import sys
    import os
    sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
    os.environ['PYTHONUNBUFFERED'] = '1'  # Ensure unbuffered output
    
    # Force print statements to appear immediately
    print("=" * 60, flush=True)
    print("[AGENT] WORKER STARTING", flush=True)
    print("=" * 60, flush=True)
    
    # Get config (needed for agent name, etc.)
    config = get_config()
    
    # Create logger - LiveKit will configure logging when run_app() is called
    import logging
    logger = logging.getLogger(__name__)
    
    # Set a basic level so logs work before LiveKit configures
    logger.setLevel(logging.INFO)
    
    agent_name = config.livekit.agent_name
    
    # Print startup info (these will always appear)
    print(f"   Agent Name: '{agent_name}'", flush=True)
    print(f"   Mode: {sys.argv[1] if len(sys.argv) > 1 else 'dev'}", flush=True)
    
    # Determine mode from command line arguments
    # Default to 'dev' mode (connects to LiveKit Cloud)
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    
    if mode == "console":
        logger.warning("[WARNING] CONSOLE MODE DETECTED - This is for local testing only!")
        logger.warning("[WARNING] Console mode uses mock rooms and won't connect to LiveKit Cloud!")
        logger.warning("[WARNING] For production, run: python agent.py dev")
        print("\n[WARNING] WARNING: Running in CONSOLE MODE (local testing only)")
        print("[WARNING] This won't connect to LiveKit Cloud rooms!")
        print("[WARNING] For production, run: python agent.py dev\n")
    elif mode == "dev":
        logger.info("[DEV] Running in DEV MODE (connects to LiveKit Cloud)")
        print("[DEV] Running in DEV MODE (connects to LiveKit Cloud)")
        print("   [OK] Will connect to LiveKit Cloud and handle real rooms from frontend")
    elif mode in ["start", "production"]:
        logger.info("[PROD] Running in PRODUCTION MODE (connects to LiveKit Cloud)")
        print("[PROD] Running in PRODUCTION MODE (connects to LiveKit Cloud)")
        print("   [OK] Will connect to LiveKit Cloud and handle real rooms from frontend")
    else:
        logger.info(f"[MODE] Running in '{mode}' MODE (connects to LiveKit Cloud)")
        print(f"[MODE] Running in '{mode}' MODE (connects to LiveKit Cloud)")
    
    # Print critical info that must be visible
    print(f"   LiveKit URL: {config.livekit.url}", flush=True)
    print(f"   Status: Connecting to LiveKit Cloud...", flush=True)
    print("=" * 60, flush=True)
    print("WHAT TO LOOK FOR:", flush=True)
    print("   [OK] 'Worker connected to LiveKit Cloud' - Connection successful", flush=True)
    print("   [OK] 'Waiting for jobs from LiveKit...' - Ready to receive jobs", flush=True)
    print("   [OK] 'Job request received' - Job dispatch received", flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)  # Empty line
    
    # NOTE: This agent uses VAD-based turn detection via Silero.
    # No additional ML models required for turn detection.
    # VAD is lightweight, reliable, and recommended for production use.
    
    # IMPORTANT: LiveKit's run_app() will set up its own logging system
    # Don't configure logging here - let LiveKit do it
    # Use print() with flush=True to ensure output appears immediately
    print("CONNECTING TO LIVEKIT CLOUD...", flush=True)
    print("NOTE: LiveKit will configure its own logging system.", flush=True)
    print("      You should see LiveKit logs below this message.", flush=True)
    print("", flush=True)  # Empty line before LiveKit takes over
    
    try:
        # LiveKit's run_app() is blocking - it will set up logging and run the worker
        # All logs from here on will go through LiveKit's logging system
        agents.cli.run_app(agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=config.livekit.agent_name,
            request_fnc=job_request_handler,  # Add job request logging
        ))
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("🛑 WORKER SHUTDOWN REQUESTED")
        logger.info("=" * 60)
        print("\n" + "=" * 60)
        print("🛑 WORKER SHUTDOWN REQUESTED")
        print("=" * 60)
        raise
    except Exception as e:
        logger.error("\n" + "=" * 60, exc_info=True)
        logger.error("[ERR] WORKER FAILED TO START")
        logger.error("=" * 60)
        logger.error(f"   Error: {e}")
        logger.error("=" * 60)
        print("\n" + "=" * 60)
        print("[ERR] WORKER FAILED TO START")
        print("=" * 60)
        print(f"   Error: {e}")
        print("=" * 60)
        raise
