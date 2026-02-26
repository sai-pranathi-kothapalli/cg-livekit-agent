"""
Phase timing for dynamic interview pacing.

Fixed structure: intro (6 min) → technical (10 min) → mcq (10 min) → general (3 min) → conclusion (1 min).
For 45-min interviews, phases scale proportionally.
"""

from typing import Dict, Tuple


# Fixed structure for 30 min: intro=6, technical=10, mcq=10, general=3, conclusion=1
TEMPLATE_30 = (6, 10, 10, 3, 1)
# For 45 min: scale proportionally (intro=9, technical=15, mcq=15, general=4, conclusion=2)
TEMPLATE_45 = (9, 15, 15, 4, 2)


def get_phase_durations(
    actual_duration_minutes: int,
    base_template: str = "30",
) -> Dict[str, int]:
    """
    Get phase durations (intro, technical, mcq, general, conclusion) for given actual duration.

    Args:
        actual_duration_minutes: Total interview duration (after late-join adjustment).
        base_template: "30" or "45" — use 30-min or 45-min ratio.

    Returns:
        {"intro": int, "technical": int, "mcq": int, "general": int, "conclusion": int}
    """
    if base_template == "45":
        intro, technical, mcq, general, conclusion = TEMPLATE_45
    else:
        intro, technical, mcq, general, conclusion = TEMPLATE_30

    total_template = intro + technical + mcq + general + conclusion
    if actual_duration_minutes <= 0:
        return {"intro": 0, "technical": 0, "mcq": 0, "general": 0, "conclusion": 1}

    # Scale proportionally; ensure conclusion is at least 1 min
    scale = actual_duration_minutes / total_template
    intro_min = max(0, round(intro * scale))
    tech_min = max(0, round(technical * scale))
    mcq_min = max(0, round(mcq * scale))
    general_min = max(0, round(general * scale))
    conclusion_min = max(1, actual_duration_minutes - intro_min - tech_min - mcq_min - general_min)
    # Rebalance: if over, trim general; if under, add to general
    allocated = intro_min + tech_min + mcq_min + general_min + conclusion_min
    general_min = max(0, general_min + (actual_duration_minutes - allocated))

    return {
        "intro": intro_min,
        "technical": tech_min,
        "mcq": mcq_min,
        "general": general_min,
        "conclusion": conclusion_min,
    }


def get_phase_boundaries(phase_durations: Dict[str, int]) -> Tuple[float, float, float, float]:
    """
    Return (intro_end_min, technical_end_min, mcq_end_min, general_end_min) in minutes from start.
    Elapsed >= intro_end means intro phase ended; etc.
    """
    intro = phase_durations["intro"]
    technical = phase_durations["technical"]
    mcq = phase_durations["mcq"]
    general = phase_durations.get("general", 0)
    intro_end = intro
    technical_end = intro + technical
    mcq_end = intro + technical + mcq
    general_end = intro + technical + mcq + general
    return (intro_end, technical_end, mcq_end, general_end)


def get_phase_end_minutes(
    duration_minutes: int,
    base_template: str = "30",
) -> Dict[str, float]:
    """
    Return phase end boundaries: {"introduction": 6, "technical": 16, "mcq": 26, "general": 29, "conclusion": 30}.
    Used to tell the LLM when each phase ends so it does not rush or conclude early.
    """
    if duration_minutes <= 0:
        return {
            "introduction": 0, "technical": 0, "mcq": 0, "general": 0,
            "conclusion": 1.0,
        }
    phase_durations = get_phase_durations(duration_minutes, base_template)
    intro_end, technical_end, mcq_end, general_end = get_phase_boundaries(phase_durations)
    return {
        "introduction": intro_end,
        "technical": technical_end,
        "mcq": mcq_end,
        "general": general_end,
        "conclusion": float(duration_minutes),
    }


def get_phase_start_minutes(
    duration_minutes: int,
    base_template: str = "30",
) -> Dict[str, float]:
    """
    Return phase start boundaries (minutes from interview start).
    Used for strict phase locking: minutes_elapsed_in_phase = elapsed - phase_start.
    """
    if duration_minutes <= 0:
        return {
            "introduction": 0.0, "technical": 0.0, "mcq": 0.0, "general": 0.0,
            "conclusion": 0.0,
        }
    phase_durations = get_phase_durations(duration_minutes, base_template)
    intro_end, technical_end, mcq_end, general_end = get_phase_boundaries(phase_durations)
    return {
        "introduction": 0.0,
        "technical": intro_end,
        "mcq": technical_end,
        "general": mcq_end,
        "conclusion": general_end,
    }


def get_current_phase(
    elapsed_minutes: float,
    duration_minutes: int,
    base_template: str = "30",
) -> str:
    """
    Determine current interview phase from elapsed time (BEFORE generating next question).

    Phase rules (30-min): 0–6 intro, 6–16 technical, 16–26 mcq, 26–29 general, 29–30 conclusion
    Phase rules (45-min): scaled proportionally

    Returns one of: "introduction", "technical", "mcq", "general", "conclusion"
    """
    if duration_minutes <= 0:
        return "conclusion"
    # Edge case: negative elapsed (timezone bug or clock skew) - treat as intro
    if elapsed_minutes < 0:
        return "introduction"
    # Edge case: interview over - force conclusion
    if elapsed_minutes >= duration_minutes:
        return "conclusion"
    phase_durations = get_phase_durations(duration_minutes, base_template)
    intro_end, technical_end, mcq_end, general_end = get_phase_boundaries(phase_durations)
    if elapsed_minutes < intro_end:
        return "introduction"
    if elapsed_minutes < technical_end:
        return "technical"
    if elapsed_minutes < mcq_end:
        return "mcq"
    if elapsed_minutes < general_end:
        return "general"
    return "conclusion"
