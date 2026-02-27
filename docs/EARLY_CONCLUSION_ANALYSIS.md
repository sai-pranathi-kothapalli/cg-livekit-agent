# Interview Early Conclusion — Root Cause Analysis

## Problem
Interview concludes around **7 minutes** despite configured 30-minute duration; all sections (intro, technical, MCQ, general) appear to be covered quickly, then the agent delivers the closing statement.

---

## 1. Are phase transitions based on question count or elapsed time?

**Answer: Phase transitions are correctly based on elapsed time only.**

- **Code path:** `TimeContextLLMWrapper.__call__` → `get_store()` → `get_now_ist()` → `elapsed_minutes = (now - start_time).total_seconds() / 60` → `get_current_phase(elapsed_minutes, duration_minutes, base_template)`.
- **Phase logic:** `utils/phase_timing.py` — `get_current_phase()` uses only `elapsed_minutes` and phase boundaries (e.g. intro 0–6, technical 6–16, mcq 16–26, general 26–29, conclusion 29–30). No question count is used.
- **Conclusion:** Phase is purely time-based. At 7 min the injected phase would be **Technical** (6–16), not conclusion.

---

## 2. Does the prompt instruct the LLM to conclude after finishing sections?

**Answer: Yes — implicitly. This is the primary cause of early conclusion.**

- **Phase-based prompt** (`phase_based_interview_prompt.py`) structures Phase 3 as:
  - **Part 1** — MCQ Round (5–6 questions)
  - **Part 2** — General Questions (open-ended)
  - **Part 3** — **CLOSING STATEMENT** ("This is the **last thing said**. No new questions after closing begins." + exact closing text)

- The prompt presents Part 3 as the **natural next step** after Part 2. It says "Continue until TIME CONTEXT shows conclusion phase or the system sends END_INTERVIEW" for Part 2, but **Part 3 does not say "Do NOT deliver until END_INTERVIEW."** RULE 3 says "NEVER move to the Closing Statement on your own," but that rule can be outweighed by the strong narrative: "after Part 2, do Part 3."

- **Code path:** The agent's instructions are built in `ProfessionalArjun._build_instructions()` from `PHASE_BASED_INTERVIEW_DEFAULT`. The base prompt is long; the Part 3 closing block is a clear, actionable "do this next" instruction. The model can complete sections quickly (short answers, 1–2 intro questions, 1 technical, 5–6 MCQs, 1–2 general) and then treat "Part 3 — CLOSING STATEMENT" as "now do the closing," without waiting for END_INTERVIEW.

---

## 3. Do fixed numbers of questions per section cause all phases to complete early?

**Answer: They encourage it.**

- The prompt specifies:
  - Phase 1: "Phase 1 is complete when **all four** are satisfied" (criteria-based, but can be met in 2–4 exchanges).
  - Phase 2: "Phase 2 complete when visible: judgment under constraint…" (vague; one short scenario can be treated as "complete").
  - Phase 3 Part 1: "**Ask exactly 5–6 MCQs.**"

- With short candidate answers, the LLM can do: 1 welcome + 1 intro, 1 anchor, 1–2 depth → Phase 1 "done"; 1 technical/scenario → Phase 2 "done"; 5–6 MCQs in quick succession → Part 1 "done"; 1–2 general → Part 2 "done" → then Part 3 closing. That can fit in ~7 minutes of wall clock if the model does not strictly respect "stay in phase until minute X."

- The **time context** tells the model "Current phase: Technical", "this phase ends at minute 16", "Do NOT conclude." So early conclusion happens when the model **prioritizes section-completion flow over the injected time context** (or the closing instruction is more salient than the time block).

---

## 4. Is there logic that triggers conclusion when all sections are covered, regardless of time?

**Answer: No in backend; yes in prompt semantics.**

- **Backend:** `interview_loop.py` triggers END_INTERVIEW **only** when `time_limit_reached` is True, i.e. `current_time_ist >= resolved_end_time` (line 219–221). There is no "all sections done" check.
- **Exact code path for real conclusion:**
  1. `elapsed_minutes = (current_time_ist - resolved_start_time).total_seconds() / 60`
  2. `time_remaining_minutes = (resolved_end_time - current_time_ist).total_seconds() / 60`
  3. `time_limit_reached = current_time_ist >= resolved_end_time`
  4. If `trigger_closing_now = time_limit_reached and not closing_triggered`, then `closing_instructions = "SYSTEM: END_INTERVIEW. ..."` and `session.generate_reply(instructions=closing_instructions)`.

- So **backend never** concludes early based on sections. Early "conclusion" is the **LLM speaking the closing statement on its own** after it has mentally completed all sections, without receiving END_INTERVIEW.

---

## 5. Are time-remaining updates used only for display or also for flow control?

**Answer: They are used for flow control in the agent, but the critical path is the per-turn time context, not the 10s updates.**

- **Time remaining updates** (`interview_loop.py` ~line 184–201): sent every 10 seconds as `{"type": "time_remaining", "time_remaining_minutes": ...}` on topic `lk-chat`. These are for **frontend display**; they are not injected into the LLM as system messages.
- **Flow control** is done by:
  1. **Session time store** — set when the candidate joins (`set_store(resolved_start_time, safe_duration, base_template)`).
  2. **TimeContextLLMWrapper** — on **every** LLM call, reads the store, computes `elapsed_minutes` and `minutes_remaining`, determines `current_phase`, and **injects a system message** with "Current minute: X of Y", "Current phase: …", "Time remaining …", "Instructions: …". So the **per-turn injection** is what controls flow; the 10s updates do not.

- If the store is **not set** (e.g. candidate not yet detected, or race), the wrapper injects a **fallback**: "Current minute: 0 of 30", "Introduction", "Time remaining: 30 minutes". So the model could see "minute 0" for several turns; it would not see "conclusion" from the wrapper. Early conclusion in that case would still be the model moving to closing on its own (e.g. after "finishing" sections in its own view).

---

## Summary: Exact code paths and conditions

| What triggers real (backend) conclusion | Condition | Code path |
|----------------------------------------|-----------|-----------|
| END_INTERVIEW + closing message        | `current_time_ist >= resolved_end_time` | `interview_loop.py`: `time_limit_reached` → `trigger_closing_now` → `closing_instructions` with "END_INTERVIEW" → `session.generate_reply(instructions=closing_instructions)` |

| What can cause *early* (LLM-only) "conclusion" | Cause | Where |
|-----------------------------------------------|--------|--------|
| LLM says closing statement without END_INTERVIEW | Prompt presents "Part 3 — CLOSING STATEMENT" as next step after Part 2; Part 3 does not restate "only after END_INTERVIEW." | `phase_based_interview_prompt.py` Part 3 section |
| LLM finishes sections quickly                  | Fixed counts (5–6 MCQs) and completion criteria (Phase 1 "all four," Phase 2 "when visible") allow short path through all parts. | Same prompt |
| Time context not dominant                      | Long base prompt + clear "do Part 3 closing" may outweigh the injected "Do NOT conclude / wait for END_INTERVIEW." | Prompt vs. time-context salience |

---

## Recommended fixes (applied in code)

1. **Prompt:** In Part 3 (CLOSING STATEMENT), add an explicit line: "Do NOT deliver Part 3 / the closing statement until the system sends END_INTERVIEW. Ignore section completion; only the backend signals when to close."
2. **Prompt:** In Phase 3 intro, state: "Part 3 (Closing) happens ONLY when the system sends END_INTERVIEW, not when you have finished MCQs or general questions."
3. **Time context:** In non-conclusion phases, add a one-line reminder: "The closing statement is ONLY for after END_INTERVIEW — never deliver it just because you have finished a section or asked N questions."
