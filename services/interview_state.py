"""
Interview State Store - process-local store for tracking violations and coding data.
"""

from typing import List, Dict, Any

_state: Dict[str, Any] = {
    "violations": [],
    "code_submissions": []
}

def add_violation(alert_type: str, message: str, timestamp: str) -> None:
    _state["violations"].append({
        "alert_type": alert_type,
        "message": message,
        "timestamp": timestamp
    })

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

def update_latest_ai_verdict(ai_verdict: str) -> None:
    """
    Update the ai_verdict of the most recent code submission.
    """
    if _state["code_submissions"]:
        _state["code_submissions"][-1]["ai_verdict"] = ai_verdict

def get_state() -> Dict[str, Any]:
    """
    Get the current interview state.
    """
    return _state

def clear_state() -> None:
    """
    Clear the interview state for a new session.
    """
    _state["violations"].clear()
    _state["code_submissions"].clear()
