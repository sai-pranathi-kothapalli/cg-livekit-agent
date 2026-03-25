"""
Interview State Store - process-local store for tracking violations and coding data.
"""

from typing import List, Dict, Any

_state: Dict[str, Any] = {
    "booking_token": None,
    "violations": [],
    "code_submissions": [],
    "current_question": "",
    "latest_code": ""
}

def initialize_from_db(booking_token: str, state: Dict[str, Any]) -> None:
    """
    Initialize the local state from a database record.
    """
    _state["booking_token"] = booking_token
    if state:
        _state["violations"] = state.get("violations", [])
        _state["code_submissions"] = state.get("code_submissions", [])
        _state["current_question"] = state.get("current_question", "")
        _state["latest_code"] = state.get("latest_code", "")

def set_current_question(question: str) -> None:
    """
    Set the current interview question being asked.
    """
    _state["current_question"] = question

def get_current_question() -> str:
    """
    Get the current interview question being asked.
    """
    return _state.get("current_question", "")

def update_latest_code(code: str) -> None:
    """
    Update the latest unsaved code and trigger persistence.
    """
    if _state["latest_code"] != code:
        _state["latest_code"] = code
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
    return _state.get("latest_code", "")

def add_violation(alert_type: str, message: str, timestamp: str) -> None:
    _state["violations"].append({
        "alert_type": alert_type,
        "message": message,
        "timestamp": timestamp
    })
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
    _state["code_submissions"].append({
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
    if _state["code_submissions"]:
        latest = _state["code_submissions"][-1]
        latest["probe_responses"].append({
            "probe_question": probe_question,
            "candidate_response": candidate_response
        })
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
    if _state["code_submissions"]:
        _state["code_submissions"][-1]["ai_verdict"] = ai_verdict

def get_state() -> Dict[str, Any]:
    """
    Get the current interview state (excluding process-only metadata like booking_token).
    """
    return {
        "violations": _state["violations"],
        "code_submissions": _state["code_submissions"],
        "current_question": _state["current_question"],
        "latest_code": _state["latest_code"]
    }

async def save_to_backend() -> bool:
    """
    Persist the current state to the backend evaluations table.
    """
    token = _state.get("booking_token")
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
    _state["booking_token"] = None
    _state["violations"].clear()
    _state["code_submissions"].clear()
    _state["current_question"] = ""
    _state["latest_code"] = ""
