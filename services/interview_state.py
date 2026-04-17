"""
Interview State Store - process-local store for tracking violations and coding data.
"""

from typing import List, Dict, Any

from contextvars import ContextVar

_state_var: ContextVar[Dict[str, Any]] = ContextVar(
    "interview_state",
    default={
        "booking_token": None,
        "violations": [],
        "code_submissions": [],
        "current_question": "",
        "latest_code": ""
    }
)

def initialize_from_db(booking_token: str, state: Dict[str, Any]) -> None:
    """
    Initialize the local state from a database record.
    """
    state_cpy = _state_var.get().copy()
    state_cpy["booking_token"] = booking_token
    if state:
        state_cpy["violations"] = state.get("violations", [])
        state_cpy["code_submissions"] = state.get("code_submissions", [])
        state_cpy["current_question"] = state.get("current_question", "")
        state_cpy["latest_code"] = state.get("latest_code", "")
    _state_var.set(state_cpy)

def set_current_question(question: str) -> None:
    """
    Set the current interview question being asked.
    """
    state_cpy = _state_var.get().copy()
    state_cpy["current_question"] = question
    _state_var.set(state_cpy)

def get_current_question() -> str:
    """
    Get the current interview question being asked.
    """
    return _state_var.get().get("current_question", "")

def update_latest_code(code: str) -> None:
    """
    Update the latest unsaved code and trigger persistence.
    """
    state_cpy = _state_var.get().copy()
    if state_cpy["latest_code"] != code:
        state_cpy["latest_code"] = code
        _state_var.set(state_cpy)
        # Trigger background save
        import asyncio
        try:
            asyncio.create_task(save_to_backend())
        except Exception:
            pass

def get_latest_code() -> str:
    """
    Get the latest unsaved code.
    """
    return _state_var.get().get("latest_code", "")

def add_violation(alert_type: str, message: str, timestamp: str) -> None:
    state_cpy = _state_var.get().copy()
    # Ensure lists are copied to prevent shared references
    state_cpy["violations"] = list(state_cpy["violations"])
    state_cpy["violations"].append({
        "alert_type": alert_type,
        "message": message,
        "timestamp": timestamp
    })
    _state_var.set(state_cpy)
    # Trigger background save
    import asyncio
    try:
        asyncio.create_task(save_to_backend())
    except Exception:
        pass

def add_code_submission(code: str, question: str, ai_verdict: str, execution_output: str, timestamp: str, language: str, time_taken_seconds: int = 0, observation_count: int = 0, evaluation_result: str = "unknown"):
    """
    Store a code submission for later evaluation.
    """
    state_cpy = _state_var.get().copy()
    state_cpy["code_submissions"] = list(state_cpy["code_submissions"])
    state_cpy["code_submissions"].append({
        "code": code,
        "question": question,
        "ai_verdict": ai_verdict,
        "execution_output": execution_output,
        "timestamp": timestamp,
        "language": language,
        "time_taken_seconds": time_taken_seconds,
        "observation_count": observation_count,
        "evaluation_result": evaluation_result,
        "submitted_empty": len(code.strip().splitlines()) < 1,
        "probe_responses": []
    })
    _state_var.set(state_cpy)
    # Trigger background save
    import asyncio
    try:
        asyncio.create_task(save_to_backend())
    except Exception:
        pass

def add_probe_response(probe_question: str, candidate_response: str):
    """
    Store candidate's response to an interviewer's technical probe.
    Useful for integrity analysis.
    """
    # Find the most recent code submission and attach the probe
    state_cpy = _state_var.get().copy()
    if state_cpy["code_submissions"]:
        state_cpy["code_submissions"] = list(state_cpy["code_submissions"])
        latest = state_cpy["code_submissions"][-1]
        # Make a copy of the dictionary to safely mutate
        latest = latest.copy()
        latest["probe_responses"] = list(latest.get("probe_responses", []))
        latest["probe_responses"].append({
            "probe_question": probe_question,
            "candidate_response": candidate_response
        })
        state_cpy["code_submissions"][-1] = latest
        _state_var.set(state_cpy)
        # Trigger background save
        import asyncio
        try:
            asyncio.create_task(save_to_backend())
        except Exception:
            pass

def update_latest_ai_verdict(ai_verdict: str) -> None:
    """
    Update the ai_verdict of the most recent code submission.
    """
    state_cpy = _state_var.get().copy()
    if state_cpy["code_submissions"]:
        state_cpy["code_submissions"] = list(state_cpy["code_submissions"])
        latest = state_cpy["code_submissions"][-1].copy()
        latest["ai_verdict"] = ai_verdict
        state_cpy["code_submissions"][-1] = latest
        _state_var.set(state_cpy)

def get_state() -> Dict[str, Any]:
    """
    Get the current interview state (excluding process-only metadata like booking_token).
    """
    store = _state_var.get()
    return {
        "violations": store["violations"],
        "code_submissions": store["code_submissions"],
        "current_question": store["current_question"],
        "latest_code": store["latest_code"]
    }

async def save_to_backend() -> bool:
    """
    Persist the current state to the backend evaluations table.
    """
    token = _state_var.get().get("booking_token")
    if not token:
        return False
        
    try:
        from app.services.evaluation_service import EvaluationService
        from app.config import get_config
        
        # This is a bit heavy but ensures we use the correct service instance
        eval_service = EvaluationService(get_config())
        state_to_save = get_state()
        
        # We use await even if it's not async yet, because we should make it async in backend
        # Wait, I made it async in the earlier edit.
        return await eval_service.update_interview_state(token, state_to_save)
    except Exception as e:
        # Avoid circular imports or other issues
        import logging
        logging.getLogger(__name__).warning(f"Failed to save state to backend: {e}")
        return False

def clear_state() -> None:
    """
    Clear the interview state for a new session.
    """
    _state_var.set({
        "booking_token": None,
        "violations": [],
        "code_submissions": [],
        "current_question": "",
        "latest_code": ""
    })
