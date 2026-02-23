"""
Phase timing for dynamic interview pacing.

Allocates intro, technical/coding, MCQ, and conclusion phases based on
actual_duration. Conclusion is always 2 minutes; other phases scale proportionally.
"""

from typing import Dict, Tuple


# Base templates: (intro, technical, mcq) minutes — conclusion always 2
TEMPLATE_30 = (10, 10, 8)   # 28 min for first three + 2 conclusion
TEMPLATE_45 = (15, 15, 13)  # 43 min for first three + 2 conclusion


def get_phase_durations(
    actual_duration_minutes: int,
    base_template: str = "30",
) -> Dict[str, int]:
    """
    Get phase durations (intro, technical, mcq, conclusion) for given actual duration.
    Conclusion is always 2 minutes; remaining time is split by template ratio.

    Args:
        actual_duration_minutes: Total interview duration (after late-join adjustment).
        base_template: "30" or "45" — use 30-min or 45-min ratio.

    Returns:
        {"intro": int, "technical": int, "mcq": int, "conclusion": int}
    """
    conclusion_min = 2
    if actual_duration_minutes <= conclusion_min:
        return {"intro": 0, "technical": 0, "mcq": 0, "conclusion": actual_duration_minutes}

    remaining = actual_duration_minutes - conclusion_min
    if base_template == "45":
        intro, technical, mcq = TEMPLATE_45
    else:
        intro, technical, mcq = TEMPLATE_30

    total_base = intro + technical + mcq
    intro_min = max(0, round(remaining * intro / total_base))
    tech_min = max(0, round(remaining * technical / total_base))
    mcq_min = max(0, remaining - intro_min - tech_min)  # ensure sum = remaining
    if mcq_min < 0:
        mcq_min = 0
        # rebalance
        intro_min = min(intro_min, remaining)
        tech_min = remaining - intro_min

    return {
        "intro": intro_min,
        "technical": tech_min,
        "mcq": mcq_min,
        "conclusion": conclusion_min,
    }


def get_phase_boundaries(phase_durations: Dict[str, int]) -> Tuple[float, float, float]:
    """
    Return (intro_end_min, technical_end_min, mcq_end_min) in minutes from start.
    Elapsed >= intro_end means intro phase ended; etc.
    """
    intro = phase_durations["intro"]
    technical = phase_durations["technical"]
    mcq = phase_durations["mcq"]
    intro_end = intro
    technical_end = intro + technical
    mcq_end = intro + technical + mcq
    return (intro_end, technical_end, mcq_end)


def get_current_phase(
    elapsed_minutes: float,
    duration_minutes: int,
    base_template: str = "30",
) -> str:
    """
    Determine current interview phase from elapsed time (BEFORE generating next question).
    Used so the LLM asks phase-appropriate questions.

    Phase rules (scaled for actual_duration when candidate joins late):
    - 30-min template: 0–10 intro, 10–20 technical, 20–28 mcq, 28–30 conclusion
    - 45-min template: 0–15 intro, 15–30 technical, 30–43 mcq, 43–45 conclusion

    Returns one of: "introduction", "technical", "mcq", "conclusion"
    """
    if duration_minutes <= 0:
        return "conclusion"
    phase_durations = get_phase_durations(duration_minutes, base_template)
    intro_end, technical_end, mcq_end = get_phase_boundaries(phase_durations)
    if elapsed_minutes < intro_end:
        return "introduction"
    if elapsed_minutes < technical_end:
        return "technical"
    if elapsed_minutes < mcq_end:
        return "mcq"
    return "conclusion"
