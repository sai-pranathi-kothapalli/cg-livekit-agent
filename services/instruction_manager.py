"""
Instruction Manager

Centralized utility to build clean system instructions for the AgentSession.
Maintains base prompt + phase status + time without using [INTERNAL] markers 
that could leak into the conversation or transcript.
"""

from typing import List, Optional

def get_phase_display_name(focus: str, requires_coding: bool = True) -> str:
    """Human-readable focus name for instructions."""
    names = {
        "intro":          "Introduction",
        "assessment":     "Assessment (Technical / MCQ)",
        "coding_window":  "Coding & Debugging" if requires_coding else "Advanced Technical / Scenarios",
        "mixed":          "Mixed (MCQ / Technical / Scenario)",
        "wrap_up":        "Wrap Up",
        "conclude":       "Conclusion",
    }
    return names.get(focus, focus.replace("_", " ").title())


def build_session_instructions(
    base_instructions: str,
    remaining_minutes: int,
    focus: str,
    duration_minutes: int,
    requires_coding: bool = False
) -> str:
    """
    Combine base instructions with current phase and timing.
    This string is suitable for session.update_instructions().
    
    NO [INTERNAL] markers are used here to avoid leakage.
    """
    
    phase_name = get_phase_display_name(focus, requires_coding=requires_coding)
    
    # 1. Start with the core base instructions from the dashboard
    final_prompt = base_instructions.strip() + "\n\n"
    
    # 2. Add current status (Time and Phase)
    # Using 'Current Status' header which is more natural for a system instruction
    status_header = (
        "## Current Interview Status\n"
        f"- Time Remaining: {remaining_minutes} minutes (Total duration: {duration_minutes} minutes)\n"
        f"- Active Phase: {phase_name}\n\n"
    )
    final_prompt += status_header
    
    # 3. Add Phase-Specific Guidance
    phase_guidance = "## Phase Guidance\n"
    
    if focus == "intro":
        instructions = [
            "You are in the INTRODUCTION phase.",
            "Ask warm, conversational questions about the candidate's background and projects.",
            "Do NOT ask technical or coding questions yet.",
            "NEVER leave this phase on your own — only phase changes end the intro.",
        ]
    elif focus == "assessment":
        instructions = [
            "You are in the ASSESSMENT phase (Technical Depth + MCQs).",
            "Freely mix deep technical questions and single-answer MCQs based on the candidate's depth.",
            "Choose question types that fit the conversation naturally.",
            "Do NOT ask coding/debugging problems yet.",
        ]
    elif focus == "coding_window":
        if requires_coding:
            instructions = [
                "You are in the CODING & DEBUGGING phase.",
                "If no coding question has been asked — ask one now and guide them to the editor (</>).",
                "You may include debugging questions with code snippets.",
                "Prioritize coding over pure MCQs in this phase.",
            ]
        else:
            instructions = [
                "You are in the ADVANCED TECHNICAL phase.",
                "Focus on complex scenarios and architectural trade-offs.",
                "MCQs are also encouraged to test broad knowledge.",
                "Do NOT ask the candidate to write code or open the code editor.",
            ]
    elif focus == "mixed":
        instructions = [
            "You are in the MIXED phase — use a varied combination of question types.",
            "Vary format: MCQ, scenario, situational, or follow-up technical questions.",
            "Keep the conversation dynamic.",
        ]
    elif focus == "wrap_up":
        instructions = [
            "You are in the final WRAP UP window.",
            "Ask ONE final open-ended question (strengths, questions for you, etc.).",
            "Stay fully engaged; do NOT say goodbye yet.",
        ]
    else:
        # conclude
        instructions = [
            "The interview has concluded. Thank the candidate warmly.",
            "Explain the evaluation and follow-up process, then say goodbye and end the call.",
            "Do NOT ask any more interview questions.",
        ]

    # Common rules
    common_rules = [
        "ONE TURN = ONE QUESTION. Ask one question, then stop and wait.",
        "Only conclude when you receive the 'conclude' status guidance.",
    ]
    
    all_guidance = instructions + common_rules
    final_prompt += "\n".join(f"- {i}" for i in all_guidance)
    
    return final_prompt
