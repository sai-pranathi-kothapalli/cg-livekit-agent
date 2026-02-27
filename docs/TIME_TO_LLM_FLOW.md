# How Time Is Given to the LLM — Clear Flow

This document describes the end-to-end flow of **time** from interview start until it is injected into the LLM prompt. No time is sent to the LLM until the candidate joins.

---

## 1. Entrypoint: Initial timing (no store yet)

**File:** `agents/entrypoint.py`

- When the job starts, entrypoint sets:
  - `interview_start_time = get_now_ist()` (placeholder; used if candidate never joins).
  - `interview_duration_minutes` from **booking/slot** (slot’s end_time − start_time, or default 30).
  - `scheduled_duration_minutes = 45` if duration ≥ 45 else `30` (for phase template).
  - `slot_start_ist_loop` from slot start (or `scheduled_at`) for **late-join** calculation.
- It then starts the **interview time loop** and passes:
  - `interview_start_time`, `interview_duration_minutes`, `scheduled_end_time`,
  - `slot_start_ist`, `scheduled_duration_minutes`.

**Important:** The **session time store** is still empty here. The LLM will not get time context until the store is set (step 2).

---

## 2. Interview loop: Candidate joins → store is set

**File:** `services/interview_loop.py`

- The loop runs `while ctx.room.isconnected() ...` and only sets timing when **the first remote participant appears** (candidate joined).
- When `len(ctx.room.remote_participants) > 0`:
  1. **Candidate join time:** `candidate_join_time = get_now_ist()`.
  2. **Late-join adjustment:**  
     `join_delay_minutes = (candidate_join_time - slot_start_ist).total_seconds() / 60`  
     `actual_duration = max(5, scheduled_duration - join_delay_minutes)`  
     So if the candidate is 5 minutes late in a 30‑min slot, actual duration = 25 minutes.
  3. **Resolved timing:**
     - `resolved_start_time = candidate_join_time`  ← **timer starts here**
     - `resolved_duration_minutes = actual_duration`
     - `resolved_end_time = candidate_join_time + timedelta(minutes=actual_duration)`
  4. **Phase template:** `base_template = "45"` if scheduled ≥ 45 else `"30"`.
  5. **Store write (this is what the LLM uses):**
     ```text
     set_store(resolved_start_time, resolved_duration_minutes, base_template)
     ```
     Also: `set_session_time(...)` and `reset_questions_asked()`.

So: **time is “given” to the system only when the candidate joins**, via `set_store(start_time, duration_minutes, base_template)`.

---

## 3. Session time store (single source of truth for the LLM)

**File:** `services/session_time_store.py`

- In-memory store: `_store = {"start_time", "duration_minutes", "base_template"}`.
- **set_store(start_time, duration_minutes, base_template)**  
  Called only from the interview loop when the candidate joins (step 2).
- **get_store()**  
  Returns `(start_time, duration_minutes, base_template)`.  
  Used by **TimeContextLLMWrapper** on every LLM call.

Until the candidate joins, `get_store()` returns `(None, None, "30")`, and the wrapper does **not** inject any time context.

---

## 4. When the LLM is about to run (wrapper chain)

**File:** `services/plugin_service.py`

- LLM chat is wrapped in this order (outer → inner):
  - **TimingLLMWrapper** (logging/timing only)
  - **HistoryManagedLLMWrapper** (history + transcript)
  - **TimeContextLLMWrapper** ← injects time here
  - **original_chat** (actual LLM, e.g. Gemini)

So every time the agent calls `llm.chat(chat_ctx=..., tools=...)`, the call goes: Timing → History → **TimeContext** → LLM.

---

## 5. TimeContextLLMWrapper: How time is given to the LLM

**File:** `services/time_context_llm_wrapper.py`

This runs **before** each LLM call (i.e. before generating the next question).

**Step A — Read store**

- `start_time, duration_minutes, base_template = get_store()`.
- If `start_time` or `duration_minutes` is `None`, the wrapper **does not inject** anything and calls the original chat as-is (happens before candidate join).

**Step B — Compute time (same process, so “now” is consistent)**

- `now = get_now_ist()`
- `elapsed_minutes = (now - start_time).total_seconds() / 60`
- `minutes_remaining = max(0, duration_minutes - elapsed_minutes)`

So the LLM always sees **elapsed** and **remaining** from the **same** `start_time` and `duration_minutes` that were set when the candidate joined.

**Step C — Phase from elapsed time**

- `current_phase = get_current_phase(elapsed_minutes, duration_minutes, base_template)`  
  (**File:** `utils/phase_timing.py`.)
- Uses `get_phase_durations(duration_minutes, base_template)` (30 or 45 min template, scaled to `actual_duration`).
- Returns one of: `"introduction"`, `"technical"`, `"mcq"`, `"conclusion"`.

So phase is driven by **elapsed time**, not by a separate “phase clock”.

**Step D — Guard (force continue)**

- `questions_asked = _get_questions_asked()` (from backend history wrapper).
- `force_continue = (questions_asked < MIN_REQUIRED_QUESTIONS) or (minutes_remaining > 2)`.
- If `force_continue` is true, the injected message tells the model to **not** conclude and to ask the next question, regardless of phase.

**Step E — Build and inject one system message**

- `time_msg = _build_time_context_message(elapsed_minutes, minutes_remaining, duration_minutes, current_phase, force_continue)`.
- Every variant includes at least:
  - **One-liner:**  
    `"Time remaining: {int(minutes_remaining)} minutes. Do NOT conclude the interview. Ask the next interview question."`
  - **Structured block:**  
    `elapsed_minutes`, `remaining_minutes`, `current_phase`, `total_duration_minutes`, plus phase rules (e.g. do not ask intro in technical phase, etc.).
- Then: `chat_ctx.add_message(role="system", content=time_msg)`.
- Then the wrapper calls `self._original_chat(*args, **kwargs)`, so the **LLM sees the existing conversation plus this new system message**.

So the **only** place time is “given” to the LLM is this single system message added to `chat_ctx` immediately before each call to the underlying LLM.

---

## 6. What the LLM actually sees (time-wise)

On each turn, the model receives in its context:

1. Its normal system instructions (interview role, phases, etc.).
2. **One extra system message** from the wrapper containing:
   - `Time remaining: X minutes. Do NOT conclude the interview. Ask the next interview question.`
   - `elapsed_minutes`, `remaining_minutes`, `current_phase`, `total_duration_minutes`
   - Phase rules and, when applicable, either “do not conclude / ask next question” or “conclude now” / “begin wrapping up” (when not `force_continue` and in the last 2–5 minutes).

So the **flow of time to the LLM** is: **store (set on candidate join) → get_store() in wrapper → compute elapsed/remaining/phase → one system message per turn**.

---

## 7. Summary diagram

```text
ENTRYPOINT
  → interview_start_time, interview_duration_minutes, slot_start_ist, scheduled_duration_minutes
  → run_interview_time_loop(...)

INTERVIEW_LOOP (each tick until candidate joins)
  → candidate joins: resolved_start_time = now, actual_duration = scheduled - join_delay
  → set_store(resolved_start_time, actual_duration, base_template)   ← STORE FILLED

SESSION_TIME_STORE
  → get_store() → (start_time, duration_minutes, base_template)

ON EVERY LLM CALL (user spoke / agent must reply):
  TimeContextLLMWrapper.__call__(chat_ctx=...)
    → start_time, duration_minutes, base_template = get_store()
    → if None: skip inject; call original_chat
    → now = get_now_ist()
    → elapsed_minutes = (now - start_time).total_seconds() / 60
    → minutes_remaining = duration_minutes - elapsed_minutes
    → current_phase = get_current_phase(elapsed_minutes, duration_minutes, base_template)
    → force_continue = (questions_asked < 8) or (minutes_remaining > 2)
    → time_msg = _build_time_context_message(...)
    → chat_ctx.add_message(role="system", content=time_msg)
    → return original_chat(*args, **kwargs)   ← LLM sees chat_ctx with time message
```

So: **time is given to the LLM only after the candidate joins**, via the store, and **on every turn** via a single system message that contains remaining time, phase, and instructions (do not conclude / ask next question or conclude/wrap when allowed).
