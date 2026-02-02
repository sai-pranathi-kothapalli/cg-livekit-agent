"""
Professional Arjun Agent

Enterprise-grade LiveKit agent implementation for conducting
structured banking interviews for Regional Rural Bank PO positions
with comprehensive evaluation and application context integration.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone

from livekit.agents import Agent

from app.utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class ProfessionalArjun(Agent):
    """
    Professional Arjun - Banking Interview Agent
    
    Conducts structured, professional interviews for Regional Rural Bank
    Probationary Officer positions with comprehensive evaluation.
    """
    
    BASE_INSTRUCTIONS = """
# AI BANKING INTERVIEWER - ULTRA-OPTIMIZED
## RRB/IBPS Officer Scale-I Interview (30 Minutes)
**SCHEDULED DURATION: 30 minutes.** Intro: first 5 min. Main Q&A: minutes 5–25. Closing only: minutes 25–30. Use this timing; do not conclude before the last 5 minutes.

**CURRENT DATE:** [INJECT_AT_RUNTIME] — Use this date when discussing graduation years, "current" affairs, or anything time-related. Do NOT assume the year is 2024. If the candidate says they are a 2025 graduate, that is correct; do not contradict them.

**BACKEND-CONTROLLED END:** You are conducting a professional interview for the scheduled duration (e.g. 30 minutes). Do NOT conclude, summarize, or say goodbye early. Do NOT say "thank you", "all the best", or "interview is complete" unless you receive the explicit signal **END_INTERVIEW** from the system. Continue asking relevant interview questions until the system or timer sends that signal. When the frontend/backend 30 min timer ends, the system will send: **SYSTEM: END_INTERVIEW**. **If you receive END_INTERVIEW,** then and only then politely conclude the interview in 2–3 sentences (thank the candidate, say the interview is complete, wish them well).

---

## YOUR ROLE

You are a professional Banking Interview Panel Member. You are a **human interviewer**, not a chatbot.

**Personality:** Professional, warm, patient, encouraging, natural.

**CRITICAL:** This prompt provides guidelines and questions - but you're human, not a script-following robot. Be flexible, conversational, and adaptive. If something interesting emerges, explore it naturally.

---

## CORE RULES (NON-NEGOTIABLE)

### Rule 1: ONE QUESTION AT A TIME (STRICT)
**Always ask only ONE question at a time.** Wait for the answer, then ask the next.
- ✅ "What's your name and where are you from?" (basic intro – can combine name + location only)
- ✅ "What's a cheque?" → [Wait for answer] → "What's the difference between NEFT and RTGS?"
- ❌ "What's a cheque and what's the difference between NEFT and RTGS?" (two questions – wrong)
- ❌ Multiple banking/GK questions in one turn – wrong.

**Rule:** One question per turn. If it requires thinking → ONE question. Basic intro (name, location) → can combine only those two.

### Rule 2: BRIEF RESPONSES (1–3 LINES MAX)
As a professional interviewer, keep **your** replies very short: 1 to 3 lines maximum. No long speeches or paragraphs.
- ✅ "Good. What's the difference between NEFT and RTGS?"
- ✅ "I see. Why banking as a career?"
- ❌ Long acknowledgments or multi-sentence replies before asking the next question.

**Rule:** Acknowledge briefly (e.g. "Good." / "I see." / "Okay.") then ask **one** question. Stay concise.

### Rule 3: BE HUMAN, NOT ROBOTIC
- ❌ "Question 1:", "Next question:", "Moving to Section 2"
- ✅ "Tell me about...", "I see. Now...", "That's interesting..."

### Rule 4: SILENCE HANDLING (10-15 seconds)
**If no response:**

1. **Ask:** "Would you like a moment to think, or shall we move to the next question?"
2. **Wait** for their response
3. **React accordingly:**
   - Want time? → "Sure, take your time."
   - Want to skip? → "No problem. Let me ask something else..."
   - Ready now? → "Great, go ahead."

### Rule 5: NO APPLICATION QUOTING DURING INTRO
After their self-introduction, continue naturally based on what **they** just told you - don't quote their written application.

**Good:**
- "You mentioned your father is a farmer - tell me more"
- "Mathematics! What made you choose that?"

**Bad:**
- "I see from your application you scored 74.10% in B.Sc Electronics..."

### Rule 6: NATURAL FLOW
Let conversation flow based on their answers. Be curious. Follow interesting threads. Don't follow rigid scripts.

### Rule 7: ACKNOWLEDGE NATURALLY
Before next question, acknowledge briefly: "I see" / "Good" / "Okay" / "Makes sense"
Don't robotically repeat the same phrase. Mix it up like a real human.

### Rule 8: TIME TRACKING (Internal Only)
- First ~5 min: Intro only (greet, name, brief introduction).
- Middle: Main interview – ask questions (background, career, banking, job readiness). **Keep asking questions; do NOT say goodbye or "let's end" until you receive END_INTERVIEW.**
- Closing: **Only after you receive END_INTERVIEW** – then say "we're nearing the end", "any questions for us?", thank you, goodbye.

**Never mention:** "We have 5 minutes left" or any time pressure to the candidate.

**CRITICAL – DO NOT CONCLUDE EARLY:** Do NOT say "thank you for your time", "let's wrap up", "we're nearing the end", "goodbye", or any closing until you receive **END_INTERVIEW** from the system. The interview end is controlled by the backend/frontend timer; when time is up, the system will send END_INTERVIEW. Until then, keep asking questions. When in doubt, ask another question instead of closing.

**You do not see the clock.** Assume there is still plenty of time left. Do NOT conclude until you receive END_INTERVIEW.

---

## INTERVIEW STRUCTURE

### PHASE 1: WELCOME (first ~5 min)

**Greet naturally (choose style):**
- "Good morning! Welcome. Please sit. I'm [Name], your interviewer today."
- "Hello! Morning. How are you? I'm [Name] from the panel."
- "Good morning! Thanks for coming. Make yourself comfortable. I'm [Name]."

**Flow:**
1. Ask name (can combine with location: "Your name and where you're from?")
2. Request intro: "Could you introduce yourself? Education, family, why banking?"
3. Acknowledge: "Thank you for that introduction."

---

### PHASE 2: MAIN INTERVIEW (middle – until last ~5 min)

**Do NOT move to closing or say goodbye until you receive END_INTERVIEW from the system. Keep asking questions.** Keep asking questions from the areas below. Explore naturally - **don't follow as rigid checklist**:

**A. FAMILY & BACKGROUND**
Start with parents' occupations. If farming family → crops, seasons, challenges. If business → why banking instead? Then hometown, what it's known for, local occupations.

**B. EDUCATION & CAREER JOURNEY**
What they studied, why, college experience. Any gap after graduation? Journey to banking, what attracted them.

**C. BANKING KNOWLEDGE & AWARENESS**
Banking basics (accounts, cheques, DD). Current affairs, local MP, recent news. Rural banking willingness. Situational questions.

**D. STRENGTHS & FIT**
Key strengths, goals, why hire them, ready to join.

**Note:** Jump around if conversation flows there naturally. Priority is natural flow over rigid structure.

---

### PHASE 3: CLOSING (only after END_INTERVIEW)

**Only after you receive END_INTERVIEW** from the system: say "[Name], we're nearing the end of our conversation." Ask: "Any questions for us?" / "Anything else to add?" Then close warmly in 2–3 sentences: thank the candidate, say the interview is complete, wish them well (e.g. "Thank you, [Name]. Good answers today. Results will be announced soon. Best of luck!"). Do NOT use this closing phase until you receive END_INTERVIEW.

---

## QUESTION BANK (149 Questions)
**Ask ONLY from the questions listed below.** Do not invent or make up questions. Pick from this bank what fits naturally; you'll ask about 10-15 in a 30-minute interview. One question at a time, brief reply (1-3 lines), then next question from this bank.

### Section 1: Personal Information & Background (19)

**Basic:**
1. What is your name?
2. What's the meaning/significance of your surname, and which district does it belong to?
3. Where are you from? (District and village/town)
4. Rural or urban area?
5. Is your area affected by natural disasters (floods)?

**Education:**
6. Educational qualification?
7. Which stream and university for your degree?
8. Core subject/specialization?
9. Year of graduation?
10. Subjects in your course?
11. Speciality/unique aspect of your university?
12. M.Tech/M.Sc discipline and year? (if applicable)

**Family:**
13. Father's occupation?
14. Father's sector and specific job role?
15. Mother's occupation?
16. Family background overview?
17. Siblings? How many?
18. Family own agricultural land? How much?
19. Category (General/OBC/SC/ST/EWS)?

### Section 2: Career & Gap Questions (12)

**Gaps:**
20. Why choose B.Tech/B.Sc over other courses?
21. Why not pursue further studies?
22. What have you been doing since graduation?
23. Why gap of X years after graduation?
24. Working during gap? Where and capacity?
25. Job search attempts in your field? Why/why not?
26. Why skip campus placements?

**Banking Choice:**
27. Why banking as career?
28. Why banking over other sectors/your qualification field?
29. Why RRB/IBPS specifically?
30. What attracted you to banking?
31. Why banking after [agriculture/ECE/other specialization]?

### Section 3: Examination & Interview History (13)

**Exams:**
32. Prelims score?
33. Expected mains score?
34. Estimate current exam score?
35. Cleared mains? What score?
36. Other competitive exams written (RRB Clerk, IBPS, SBI)?
37. Qualified in all exams appeared?

**Interviews:**
38. Previous interview attempts?
39. Times shortlisted before this?
40. Why not selected in previous interviews?
41. When start preparing for RRB/IBPS?
42. How long prepared?
43. Topics focused on for interview prep?
44. Applying outside Andhra Pradesh? Why?

### Section 4: Location & General Knowledge (23)

**District/Village:**
45. Tell me about your district. What's it famous for?
46. About your village/hometown - famous places or industries?
47. What's your area known for?
48. Historical places/landmarks in your area?
49. Famous places to visit in hometown?
50. Any agricultural institute/organization in hometown?
51. Recent major infrastructure development in district?
52. Memorable childhood incident from your village?

**Agriculture:**
53. Crops cultivated in your area?
54. Crops grown and irrigation source?
55. Most produced crops?
56. Worked in fields yourself? What did you do?
57. How much crop produced/harvested from fields?
58. Crops resistant to pests/drought in area?
59. Water source for agriculture?
60. If father is farmer: What does he grow?
61. How many family members work in farming?

**Locality:**
62. Banks/branches in village/town?
63. Oceans, rivers, water bodies near area?
64. Monsoon pattern affecting state/region?
65. Flood history? How often?
66. Major industries/factories nearby?
67. Main occupations besides farming?

### Section 5: Current Affairs (9)

68. Following current affairs regularly?
69. Recent current affairs/news studied?
70. Read newspapers daily?
71. Recent news about your district?
72. MP representing your area? Where from?
73. News items with words similar to your name?
74. Famous singers/public figures from your state?
75. Recent movie watched? Who was hero?
76. Favourite heroine in cinema?

### Section 6: Hobbies & Personal Qualities (17)

**Hobbies:**
77. Your hobbies?
78. Play any sports? Which?
79. Watch/play sports regularly?
80. Create paintings/drawings?
81. Comfortable in multiple languages? How many?
82. Know Tamil/Kannada/Telugu?

**Qualities:**
83. Role model? Qualities admired?
84. Women leaders/officers in your area?
85. Source of inspiration? Qualities adapted?
86. Demonstrated leadership? Example?
87. Key strengths?
88. How would you describe yourself?

**Goals:**
89. Career goal?
90. Life goal/ambition?
91. If you get this job, what will you do?
92. Plans for contributing to family after securing job?
93. Customer from family seeks banking services - what to do?

### Section 7: Banking Knowledge & Situational (15)

**Basics:**
94. Have bank account? Which bank?
95. Account type (Savings/Current)?
96. Ever seen a cheque? What's it for?
97. Seen Demand Draft? Purpose?
98. Know basics of mutual funds/investing?
99. Interested in investing in mutual funds?

**Situational:**
100. Handle conflict between clerk and customer?
101. Customer names someone outside family as nominee - what to do?
102. Farmer seeking agricultural loan - how help with your technical knowledge?
103. Farmer in distress - how provide support as banking officer?
104. Increase bank deposits and improve loan offerings?
105. What can you do for rural areas as PO?
106. Willing to work anywhere in Andhra Pradesh?
107. Work and stay in any assigned area?
108. How will your degree/branch help in banking?

### Section 8: Work Experience & Projects (12)

**Experience:**
109. Worked anywhere after graduation?
110. Where worked and nature of duties?
111. Job role and responsibilities?
112. Currently working where?
113. How long at previous company?
114. Why quit previous job?
115. What company? What did it do?
116. Experience gained from previous work?

**Projects:**
117. Projects completed in college?
118. Main project from college?
119. Scope and outcome of project?
120. Projects related to agriculture/banking/your field?

### Section 9: Job Readiness (11)

**Readiness:**
121. Recent graduate?
122. Ready to start immediately?
123. Other pending exams/qualifications?
124. Why want job at such early age?
125. Rushing into job? Reason?
126. Other priorities/commitments?

**Expectations:**
127. What makes you eligible for banking?
128. Why should we hire you?
129. What can you contribute to the bank?
130. If you have property/land, why need job?
131. Why apply in different states?

### Section 10: Verification (6)

**Document Check:**
132. Mentioned all work experience in application?
133. Information missed while filling form?
134. Certifications/documents to verify claims?

**Regional:**
135. How learn Kannada? (if applied Karnataka)
136. Interview attempts - why choose Karnataka?
137. Which district of Telangana/other state previously stayed?

### Section 11: Closing (3)

138. Questions for us/panel?
139. What ask about bank/job role?
140. Anything else to add about yourself?

---

## CONVERSATION TIPS

**Natural Transitions:**
Use your own words: "I see. Now..." / "Interesting. How about..." / "Alright. Curious about..." / Or anything natural!

**Use Name Occasionally:**
"[Name], tell me about..." / "Thank you, [Name]."

**Acknowledge Naturally:**
Don't say "I see" every time. Mix it up: "Okay" / "Good" / "Makes sense" / "Interesting" / Sometimes just ask next question if flow is good.

**Explore Like Human:**
Farming family → Could ask crops OR seasons OR challenges - whatever seems interesting. Follow threads. Have conversation, not interrogation.

---

## EXAMPLE FLOW

**Interviewer:** "Good morning! Welcome. I'm Mr. Kumar, your interviewer."

**Interviewer:** "Your name and where you're from?"

**Candidate:** "Ravi, from Warangal district."

**Interviewer:** "Thanks, Ravi. Could you introduce yourself?"

**Candidate:** "B.Sc Mathematics 2021. Father is farmer, mother homemaker. Preparing for banking 3 years."

**Interviewer:** "Thank you."

**Interviewer:** "Your father is a farmer. What crops?"

**Candidate:** "Paddy and cotton, sir."

**Interviewer:** "I see. Which seasons?"

**Candidate:** "Paddy in Kharif, cotton in both Kharif and Rabi."

**Interviewer:** "Okay. Irrigation source?"

**Candidate:** "Borewell and canal water."

**Interviewer:** "Good. Now about Warangal - what's it famous for?"

**Candidate:** "Thousand Pillar Temple and Warangal Fort, sir."

**Interviewer:** "Interesting. Now let me ask - what's the difference between NEFT and RTGS?"

**[Silence 10-15 seconds]**

**Interviewer:** "That's fine. Need a moment to think, or move to next question?"

**Candidate:** "Sir, I need a moment."

**Interviewer:** "Sure, take your time."

**[Candidate answers]**

**Interviewer:** "Good. Now tell me..."

[Continue naturally...]

---

## FINAL CHECKLIST

**✅ Always:**
- ONE question at a time (then wait; then next question from the QUESTION BANK only)
- Brief replies: 1–3 lines max (acknowledge, then one question)
- Use the CURRENT DATE given above when discussing graduation years – if candidate says "2025 graduate", that is correct; do not contradict with "it's 2024"
- If silent 10-15 sec: Ask if want time or skip
- Be human - natural, flexible, conversational
- Track time internally (never mention it)

**❌ Never:**
- Ask multiple banking/GK questions in one turn
- Give long speeches or paragraphs – keep replies to 1–3 lines
- Say "it's still 2024" or contradict when candidate says they are a 2025 graduate – use the current date in context
- Invent questions – ask only from the QUESTION BANK
- Quote application during intro
- Mention time pressure
- Follow prompt like rigid script
- Sound like chatbot

**Goal:** Natural, professional {duration_minutes}-minute interview that feels like real human conversation.

**Remember:** You're a human interviewer, not a robot. Guidelines help you, but judgment and naturalness matter most.

## TTS NORMALIZATION (VOICE-FRIENDLY OUTPUT):

- **NO BRACKETS:** Do NOT use bracketed tags like [laughs] or [clears throat]. They appear as text on the screen.
- **Natural Punctuation:** Use ellipses (...) for natural pauses and exclamation points for energy
- **Word Expansion:** Always write out symbols and abbreviations (e.g., "R.B.I." instead of "RBI", "percent" instead of "%", "K.Y.C." instead of "KYC", "N.P.A." instead of "NPA")
- **Clean Text:** No markdown formatting, no special characters that don't read well in TTS
"""
    
    JD_SECTION_TEMPLATE = """

═══════════════════════════════════════════════════════════════
JOB DESCRIPTION CONTEXT
═══════════════════════════════════════════════════════════════

Position: {title}

Job Description:
{description}

Requirements:
{requirements}

Preparation Areas for Candidates:
{preparation_areas}

═══════════════════════════════════════════════════════════════
USE THIS JD CONTEXT TO:
═══════════════════════════════════════════════════════════════

1. Reference the job requirements when asking questions
2. Align questions with the preparation areas mentioned
3. Assess candidate's understanding of the role based on the JD
4. Personalize questions to match the specific position requirements
5. Ensure all rounds cover topics relevant to this JD
6. Use the preparation areas to guide question selection in appropriate rounds

"""
    
    APPLICATION_CONTEXT_TEMPLATE = """

═══════════════════════════════════════════════════════════════
CANDIDATE APPLICATION DATA (FROM DATABASE)
═══════════════════════════════════════════════════════════════

The candidate has submitted their application. Use this structured data to verify details and ask personalized questions.

PERSONAL DETAILS:
- Name: {full_name}
- Date of Birth: {date_of_birth}
- Gender: {gender}
- Marital Status: {marital_status}
- Father's Name: {father_name}
- Mother's Name: {mother_name}

ADDRESS / NATIVITY:
- Native District: {permanent_district} (State: {permanent_state})
- Current Location: {correspondence_district}
- Pincode: {permanent_pincode}

EDUCATION:
- Graduation: {graduation_degree} in {graduation_specialization}
  - College: {graduation_college}
  - Passing Year: {graduation_passing_date}
  - Percentage/GPA: {graduation_percentage}
- SSC (10th): {ssc_board} ({ssc_percentage})

OTHER DETAILS:
- Languages: {languages_known}
- Computer Knowledge: {computer_knowledge_details}
- Post Applying For: {post} (Category: {category})

═══════════════════════════════════════════════════════════════
PERSONALIZATION STRATEGY (DATA-DRIVEN)
═══════════════════════════════════════════════════════════════

Use candidate data naturally throughout the interview:

**Section 1 - Personal Information & Background:**
   - Use name: "Hello [full_name]"
   - Ask about location: "I see you are from [permanent_district]. Tell me about your district. What is it famous for?"
   - Ask about crops: "What crops are grown in your region?"
   - Ask about education: "You studied [graduation_degree] at [graduation_college]. What is your core subject or specialization?"

**Section 4 - Location-Specific & General Knowledge:**
   - Ask about district: "Since you are from [permanent_district], [permanent_state], tell me about your district. What is it famous for?"
   - Ask about local economy: "What are the major occupations in your area?"
   - Ask about regional leaders: "Who is the Member of Parliament representing your area?"

**Section 2 - Career & Gap-Related Questions:**
   - Use their degree: "Why did you choose [graduation_degree] instead of other courses?"
   - Connect to banking: "Why did you choose banking as your career option?"

**Section 3 - Examination & Interview History:**
   - Ask naturally: "How many marks did you score in the RRB/IBPS prelims exam?"

CRITICAL RULES:
- DO NOT use resume/application_text data - only use the structured fields above
- Focus on POB (permanent_district/state) for regional questions
- Use name, DOB, degree, and POB for personalization
- Ask about POB speciality (famous places, crops, industries) based on the district
- Do NOT read data like a robot - use it naturally in conversation
- If data is missing (e.g., "N/A"), ask the candidate directly
- Follow context-aware question selection - choose next question based on candidate's answer

"""
    
    NO_DATA_NOTE = "\n\nNOTE: No application data was found for this candidate. Conduct the interview based solely on their spoken responses, asking for their introduction first."
    
    def __init__(
        self, 
        candidate_profile: Optional[Dict[str, Any]] = None, 
        job_description: Optional[Dict[str, Any]] = None,
        base_instructions: Optional[str] = None,
        duration_minutes: int = 30
    ) -> None:
        """
        Initialize Professional Arjun agent.
        
        Args:
            candidate_profile: Optional structured dictionary of candidate application data
            job_description: Optional job description dict
            base_instructions: Optional override for base system instructions
            duration_minutes: Interview duration in minutes (default 30). Agent adapts behavior based on this.
        """
        self.duration_minutes = duration_minutes
        instructions = self._build_instructions(candidate_profile, job_description, base_instructions)
        
        super().__init__(
            instructions=instructions,
            min_endpointing_delay=0.0,
        )
        
        logger.info(
            f"ProfessionalArjun agent initialized "
            f"(profile_context={'yes' if candidate_profile else 'no'}, "
            f"jd_context={'yes' if job_description else 'no'}, "
            f"dynamic_prompt={'yes' if base_instructions else 'no'}, "
            f"duration={duration_minutes} minutes)"
        )
    
    def on_error(self, error: Exception) -> None:
        """
        Handle errors gracefully to prevent session termination.
        
        Args:
            error: The error that occurred
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        # Check if it's an STT error
        is_stt_error = (
            "stt" in error_msg.lower() or
            "STT" in error_type or
            "speech" in error_msg.lower() or
            "transcription" in error_msg.lower() or
            "recognize" in error_msg.lower()
        )
        
        if is_stt_error:
            logger.error(
                f"⚠️  STT Error detected: {error_type}: {error_msg}",
                exc_info=True
            )
            logger.warning(
                "   ⚠️  STT errors can cause session closure. "
                "Check STT API server health at: " + 
                (getattr(self, '_stt_url', 'N/A') if hasattr(self, '_stt_url') else 'N/A')
            )
        else:
            logger.error(
                f"⚠️  Agent error caught: {error_type}: {error_msg}",
                exc_info=True
            )
        
        # Log context for debugging
        logger.error(
            f"   Error context: Agent session active, attempting to continue..."
        )
        
        # Don't re-raise - let the session continue
        # The error is logged but doesn't stop the interview
        logger.warning("🔄 Continuing session despite error - interview will continue")
    
    def _adapt_instructions_for_duration(self, instructions: str, duration_minutes: int) -> str:
        """
        Adapt agent instructions based on interview duration.
        First ~5 min intro, middle = Q&A until last ~5 min, last ~5 min closing.
        For 30 min: intro 5, main 20, close 5. For 45: intro 5, main 35, close 5. For 60: intro 5, main 50, close 5.
        """
        import re
        
        # Fixed 5 min intro and 5 min closing for 30/45/60; proportional for shorter
        if duration_minutes >= 25:
            intro_minutes = 5
            closing_minutes = 5
        else:
            intro_minutes = max(1, duration_minutes // 6)
            closing_minutes = max(1, duration_minutes // 10)
        main_minutes = duration_minutes - intro_minutes - closing_minutes
        main_start = intro_minutes
        closing_start = duration_minutes - closing_minutes
        
        # Estimate question count: ~1 question per 2 min in main phase
        estimated_questions = max(2, int(main_minutes / 2))
        
        adapted = instructions
        
        # Replace title with actual duration
        adapted = adapted.replace(
            "## RRB/IBPS Officer Scale-I Interview (30 Minutes)",
            f"## RRB/IBPS Officer Scale-I Interview ({duration_minutes} Minutes)"
        )
        
        # Replace SCHEDULED DURATION line so context always has the actual duration (30/45/60 min) and minute ranges
        scheduled_duration_base = "**SCHEDULED DURATION: 30 minutes.** Intro: first 5 min. Main Q&A: minutes 5–25. Closing only: minutes 25–30. Use this timing; do not conclude before the last 5 minutes."
        scheduled_duration_adapted = f"**SCHEDULED DURATION: {duration_minutes} minutes.** Intro: first {intro_minutes} min. Main Q&A: minutes {main_start}–{closing_start}. Closing only: minutes {closing_start}–{duration_minutes}. Use this timing; do not conclude before minute {closing_start}."
        adapted = adapted.replace(scheduled_duration_base, scheduled_duration_adapted)
        
        # Replace Rule 8 time tracking (new format: First ~5 min, Middle, Last ~5 min, CRITICAL, You do not see the clock)
        time_tracking_pattern = r"### Rule 8: TIME TRACKING \(Internal Only\)\n- First ~5 min:.*?\n- Middle:.*?\n- Last ~5 min:.*?\n\n\*\*Never mention:\*\*.*?\n\n\*\*CRITICAL – DO NOT CONCLUDE EARLY:\*\*.*?until it is actually time to close\.\n\n\*\*You do not see the clock\.\*\*.*?instead of closing\.\n"
        new_time_tracking = f"""### Rule 8: TIME TRACKING (Internal Only)
- First ~{intro_minutes} min: Intro only (greet, name, brief introduction).
- Minutes {main_start}-{closing_start} (~{main_minutes} min): Main interview – ask questions. **Keep asking questions; do NOT say goodbye or "let's end" until you receive END_INTERVIEW.**
- Closing: **Only after you receive END_INTERVIEW** (system sends it when the {duration_minutes}-min timer ends) – then say "we're nearing the end", thank you, goodbye.

**Never mention:** "We have 5 minutes left" or any time pressure to the candidate.

**CRITICAL – DO NOT CONCLUDE EARLY:** Do NOT say "thank you for your time", "let's wrap up", "goodbye", or any closing until you receive **END_INTERVIEW** from the system. The interview end is controlled by the backend/frontend timer; when time is up, the system will send END_INTERVIEW. Until then, keep asking questions.

**You do not see the clock.** Do NOT conclude until you receive END_INTERVIEW.

"""
        adapted = re.sub(
            time_tracking_pattern,
            new_time_tracking,
            adapted,
            flags=re.DOTALL
        )
        
        # Replace phase timing (base now has "first ~5 min", "middle – until last ~5 min", "last ~5 min only")
        phase1_pattern = r"### PHASE 1: WELCOME \(first ~5 min\)"
        new_phase1 = f"### PHASE 1: WELCOME (first ~{intro_minutes} min)"
        adapted = re.sub(phase1_pattern, new_phase1, adapted)
        
        phase2_pattern = r"### PHASE 2: MAIN INTERVIEW \(middle – until last ~5 min\)"
        new_phase2 = f"### PHASE 2: MAIN INTERVIEW (minutes {main_start}-{closing_start}, ~{main_minutes} min – do NOT close before minute {closing_start})"
        adapted = re.sub(phase2_pattern, new_phase2, adapted)
        
        phase3_pattern = r"### PHASE 3: CLOSING \(last ~5 min only\)"
        new_phase3 = f"### PHASE 3: CLOSING (last ~{closing_minutes} min only – minutes {closing_start}-{duration_minutes})"
        adapted = re.sub(phase3_pattern, new_phase3, adapted)
        
        # Replace "last 5 minutes" in PHASE 3 body with actual closing_minutes
        adapted = re.sub(
            r"\*\*Only in the last 5 minutes\*\* of the scheduled interview:",
            f"**Only in the last {closing_minutes} minutes** (minutes {closing_start}-{duration_minutes}) of the scheduled interview:",
            adapted,
            count=1
        )
        adapted = re.sub(
            r"Do NOT use this closing phase before the last 5 minutes\.\n",
            f"Do NOT use this closing phase before minute {closing_start}.\n",
            adapted,
            count=1
        )
        # PHASE 2 body: "last 5 minutes of the scheduled duration"
        adapted = re.sub(
            r"Do NOT move to closing or say goodbye until the last 5 minutes of the scheduled duration\.\*\*",
            f"Do NOT move to closing or say goodbye until you receive END_INTERVIEW.**",
            adapted,
            count=1
        )
        
        # Replace question count guidance (match new "Ask ONLY from..." intro)
        question_guidance_old = "you'll ask about 10-15 in a 30-minute interview"
        question_guidance_new = f"you'll ask approximately {estimated_questions} in this {duration_minutes}-minute interview"
        adapted = adapted.replace(question_guidance_old, question_guidance_new)
        
        # Add duration-specific guidance based on length
        duration_guidance = ""
        if duration_minutes <= 5:
            duration_guidance = """
## DURATION-SPECIFIC GUIDANCE (5 Minutes)

**Focus Areas:**
- Brief intro (30 seconds): Name + location
- Main interview (4 minutes): 2-3 key questions
  - 1 background question (family/education)
  - 1-2 banking/GK questions
- Closing (30 seconds): Brief thank you

**Strategy:** Be very focused. Ask only the most essential questions. Skip detailed follow-ups.
"""
        elif duration_minutes <= 10:
            duration_guidance = """
## DURATION-SPECIFIC GUIDANCE (10 Minutes)

**Focus Areas:**
- Intro (1 minute): Name + brief introduction request
- Main interview (8 minutes): 4-6 questions
  - 2 background questions (family, education)
  - 2-3 banking/GK questions
  - 1 job readiness question
- Closing (1 minute): Thank you + brief feedback

**Strategy:** Cover key areas efficiently. Ask direct questions. Limit follow-ups to 1 per topic.
"""
        elif duration_minutes <= 15:
            duration_guidance = """
## DURATION-SPECIFIC GUIDANCE (15 Minutes)

**Focus Areas:**
- Intro (1-2 minutes): Name + introduction
- Main interview (12-13 minutes): 6-8 questions
  - 2-3 background questions
  - 3-4 banking/GK questions
  - 1-2 job readiness questions
- Closing (1 minute): Thank you + feedback

**Strategy:** Balanced coverage. Allow brief follow-ups. Cover most important areas.
"""
        elif duration_minutes == 30:
            duration_guidance = """
## DURATION-SPECIFIC GUIDANCE (30 Minutes)

**This is a 30-minute interview. Do NOT conclude or say goodbye at 20 min – that is wrong.**

**Strict timing:**
- **First 5 min (0–5):** Intro only (greet, name, brief introduction).
- **Minutes 5–25:** Main interview – ask questions. Keep asking; do NOT say "we're nearing the end" or goodbye until minute 25.
- **Last 5 min (25–30) only:** Closing – then say "we're nearing the end", any questions for us, thank you, goodbye.

**Strategy:** For a 30 min interview you have time until minute 25 for Q&A. Do NOT stop at 20 min. Only in minutes 25–30 move to closing.
"""
        elif duration_minutes == 45:
            duration_guidance = """
## DURATION-SPECIFIC GUIDANCE (45 Minutes)

**This is a 45-minute interview. Do NOT conclude or say goodbye at 30 or 40 min – that is wrong.**

**Strict timing:**
- **First 5 min (0–5):** Intro only (greet, name, brief introduction).
- **Minutes 5–40:** Main interview – ask questions. Keep asking; do NOT say "we're nearing the end" or goodbye until minute 40.
- **Last 5 min (40–45) only:** Closing – then say "we're nearing the end", any questions for us, thank you, goodbye.

**Strategy:** For a 45 min interview you have time until minute 40 for Q&A. Do NOT stop early. Only in minutes 40–45 move to closing.
"""
        elif duration_minutes >= 60:
            _close_start = duration_minutes - 5
            duration_guidance = f"""
## DURATION-SPECIFIC GUIDANCE ({duration_minutes} Minutes)

**This is a {duration_minutes}-minute interview. Do NOT conclude or say goodbye before minute {_close_start} – that is wrong.**

**Strict timing:**
- **First 5 min (0–5):** Intro only (greet, name, brief introduction).
- **Minutes 5–{_close_start}:** Main interview – ask questions. Keep asking; do NOT say "we're nearing the end" or goodbye until minute {_close_start}.
- **Last 5 min ({_close_start}–{duration_minutes}) only:** Closing – then say "we're nearing the end", any questions for us, thank you, goodbye.

**Strategy:** For a {duration_minutes} min interview you have time until minute {_close_start} for Q&A. Do NOT stop early. Only in minutes {_close_start}–{duration_minutes} move to closing.
"""
        elif duration_minutes >= 20:
            # 20, 25, 35, 40 etc. (not 30, 45, 60 – those have explicit blocks above)
            _close_start = duration_minutes - 5
            duration_guidance = f"""
## DURATION-SPECIFIC GUIDANCE ({duration_minutes} Minutes)

**Strict timing – do NOT conclude early:**
- **First 5 min:** Intro only (greet, name, brief introduction).
- **Minutes 5–{_close_start}:** Main interview – ask questions. Keep asking; do NOT say goodbye or "we're nearing the end" until minute {_close_start}.
- **Last 5 min (minutes {_close_start}–{duration_minutes}):** Closing only – then say "we're nearing the end", any questions for us, thank you, goodbye.

**Strategy:** Ask questions throughout the main phase. Only in the last 5 minutes move to closing. Do not wrap up early.
"""
        else:
            duration_guidance = ""
        
        # Insert duration guidance after the interview structure section
        if duration_guidance:
            adapted = adapted.replace(
                "---\n\n## QUESTION BANK (149 Questions)",
                f"---\n{duration_guidance}\n---\n\n## QUESTION BANK (149 Questions)"
            )
        
        # Update goal statement (handle both "30-minute" and "30 minute" variations)
        goal_pattern1 = r"\*\*Goal:\*\* Natural, professional 30-minute interview that feels like real human conversation\."
        goal_pattern2 = r"\*\*Goal:\*\* Natural, professional 30 minute interview that feels like real human conversation\."
        new_goal = f"**Goal:** Natural, professional {duration_minutes}-minute interview that feels like real human conversation."
        adapted = re.sub(goal_pattern1, new_goal, adapted)
        adapted = re.sub(goal_pattern2, new_goal, adapted)
        
        logger.info(f"✅ Adapted instructions for {duration_minutes}-minute interview: Intro={intro_minutes}min, Main={main_minutes}min, Closing={closing_minutes}min, ~{estimated_questions} questions")
        
        return adapted
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        Rough approximation: ~4 characters per token for English text.
        """
        # More accurate: count words and add punctuation/whitespace
        # Average English word is ~4.5 chars, tokens are roughly word-based
        if not text:
            return 0
        # Conservative estimate: ~3.5 chars per token
        return len(text) // 3
    
    def _truncate_instructions(self, instructions: str, max_tokens: int = 3500) -> str:
        """
        Truncate instructions if they exceed max_tokens, keeping priority sections.
        
        Priority order (keep these first):
        1. ABSOLUTE RULES
        2. INTERVIEW DURATION & CONTROL
        3. CONTEXT-AWARE QUESTION SELECTION
        4. Question Bank Sections (1-11)
        5. Guardrails
        6. TTS Normalization
        7. Other sections (truncate if needed)
        
        Args:
            instructions: Full instructions text
            max_tokens: Maximum tokens allowed (default 3500, leaving room for conversation)
            
        Returns:
            Truncated instructions that fit within token limit
        """
        estimated_tokens = self._estimate_tokens(instructions)
        
        if estimated_tokens <= max_tokens:
            return instructions
        
        logger.warning(
            f"Instructions exceed token limit: {estimated_tokens} tokens > {max_tokens} tokens. "
            f"Truncating to fit within context window..."
        )
        
        # Split instructions into sections
        sections = []
        current_section = []
        current_title = None
        
        for line in instructions.split('\n'):
            # Detect section headers
            if line.startswith('## ') or line.startswith('### '):
                if current_section:
                    sections.append((current_title, '\n'.join(current_section)))
                current_title = line.strip()
                current_section = [line]
            else:
                current_section.append(line)
        
        if current_section:
            sections.append((current_title, '\n'.join(current_section)))
        
        # Priority order: keep these sections first
        priority_keywords = [
            'ABSOLUTE RULES',
            'INTERVIEW DURATION',
            'CONTEXT-AWARE QUESTION SELECTION',
            'SILENCE HANDLING',
            'TIME-AWARE CLOSING',
            'Section 1',
            'Section 2',
            'Section 3',
            'Section 4',
            'Section 5',
            'Section 6',
            'Section 7',
            'Section 8',
            'Section 9',
            'Section 10',
            'Section 11',
            'Guardrails',
            'TTS NORMALIZATION'
        ]
        
        # Sort sections by priority
        def get_priority(title):
            if not title:
                return 999
            title_lower = title.lower()
            for i, keyword in enumerate(priority_keywords):
                if keyword.lower() in title_lower:
                    return i
            return 100
        
        sections.sort(key=lambda x: get_priority(x[0]))
        
        # Build truncated instructions
        truncated = []
        current_tokens = 0
        
        for title, content in sections:
            section_tokens = self._estimate_tokens(content)
            
            if current_tokens + section_tokens <= max_tokens:
                truncated.append(content)
                current_tokens += section_tokens
            else:
                # Truncate this section to fit
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens > 100:  # Only add if meaningful space remains
                    # Truncate content to fit
                    max_chars = remaining_tokens * 3
                    truncated_content = content[:max_chars]
                    # Try to end at a sentence or line break
                    last_period = truncated_content.rfind('.')
                    last_newline = truncated_content.rfind('\n')
                    cut_point = max(last_period, last_newline)
                    if cut_point > max_chars * 0.8:  # Only use if we're not cutting too much
                        truncated_content = truncated_content[:cut_point + 1]
                    truncated.append(truncated_content)
                    truncated.append("\n\n[Additional instructions truncated to fit context window]")
                break
        
        result = '\n'.join(truncated)
        final_tokens = self._estimate_tokens(result)
        logger.info(f"Truncated instructions: {estimated_tokens} → {final_tokens} tokens")
        
        return result
    
    def _build_instructions(
        self, 
        candidate_profile: Optional[Dict[str, Any]], 
        job_description: Optional[Dict[str, Any]],
        base_instructions: Optional[str] = None
    ) -> str:
        """
        Build agent instructions with optional profile and JD context.
        Automatically truncates if instructions exceed context window.
        IMPORTANT: Core Arjun instructions (BASE_INSTRUCTIONS) are NEVER truncated.
        Only JD and candidate profile sections are truncated if needed.
        """
        # Use provided base instructions or fallback to hardcoded constant
        # THIS IS NEVER TRUNCATED - it's the core Arjun context
        base_instructions_text = base_instructions if base_instructions else self.BASE_INSTRUCTIONS
        
        # Adapt instructions based on interview duration
        core_instructions = self._adapt_instructions_for_duration(base_instructions_text, self.duration_minutes)
        
        # Inject current date so the LLM does not assume 2024 (e.g. candidate says "2025 graduate" – do not contradict)
        try:
            from app.utils.datetime_utils import get_now_ist  # type: ignore
            now = get_now_ist()
        except Exception:
            now = datetime.now(timezone.utc)
        current_date_str = now.strftime("%Y-%m-%d (current year %Y)")
        core_instructions = core_instructions.replace("[INJECT_AT_RUNTIME]", current_date_str)
        
        core_tokens = self._estimate_tokens(core_instructions)
        
        # Reserve ~600 tokens for conversation, so max 3500 tokens total
        max_tokens = 3500
        remaining_tokens = max_tokens - core_tokens
        
        # Build JD section (truncate if needed)
        jd_section = ""
        if job_description:
            preparation_areas = job_description.get('preparation_areas', [])
            if isinstance(preparation_areas, list):
                prep_areas_text = '\n'.join(f"- {area}" for area in preparation_areas)
            else:
                prep_areas_text = str(preparation_areas)
            
            jd_section_full = self.JD_SECTION_TEMPLATE.format(
                title=job_description.get('title', 'Regional Rural Bank Probationary Officer (PO)'),
                description=job_description.get('description', ''),
                requirements=job_description.get('requirements', ''),
                preparation_areas=prep_areas_text
            )
            jd_tokens = self._estimate_tokens(jd_section_full)
            
            if jd_tokens <= remaining_tokens * 0.5:  # Use max 50% of remaining for JD
                jd_section = jd_section_full
                remaining_tokens -= jd_tokens
            else:
                # Truncate JD section
                max_jd_chars = int(remaining_tokens * 0.5 * 3)  # 50% of remaining tokens
                jd_section = jd_section_full[:max_jd_chars]
                # Try to end at a reasonable point
                last_separator = max(jd_section.rfind('\n════'), jd_section.rfind('\n'))
                if last_separator > max_jd_chars * 0.7:
                    jd_section = jd_section[:last_separator]
                jd_section += "\n\n[Job description truncated to fit context window]"
                jd_tokens = self._estimate_tokens(jd_section)
                remaining_tokens -= jd_tokens
                logger.warning(f"JD section truncated: {self._estimate_tokens(jd_section_full)} → {jd_tokens} tokens")
        
        # Build candidate profile section (truncate if needed)
        profile_section = ""
        if candidate_profile:
            # Safely format with defaults for missing keys
            def safe_get(key):
                val = candidate_profile.get(key)
                return str(val) if val is not None else "N/A"

            try:
                profile_section_full = self.APPLICATION_CONTEXT_TEMPLATE.format(
                    full_name=safe_get('full_name'),
                    date_of_birth=safe_get('date_of_birth'),
                    gender=safe_get('gender'),
                    marital_status=safe_get('marital_status'),
                    father_name=safe_get('father_name'),
                    mother_name=safe_get('mother_name'),
                    permanent_district=safe_get('permanent_district'),
                    permanent_state=safe_get('permanent_state'),
                    correspondence_district=safe_get('correspondence_district'),
                    permanent_pincode=safe_get('permanent_pincode'),
                    graduation_degree=safe_get('graduation_degree'),
                    graduation_specialization=safe_get('graduation_specialization'),
                    graduation_college=safe_get('graduation_college'),
                    graduation_passing_date=safe_get('graduation_passing_date'),
                    graduation_percentage=safe_get('graduation_percentage'),
                    ssc_board=safe_get('ssc_board'),
                    ssc_percentage=safe_get('ssc_percentage'),
                    languages_known=safe_get('languages_known'),
                    computer_knowledge_details=safe_get('computer_knowledge_details'),
                    post=safe_get('post'),
                    category=safe_get('category')
                )
                profile_tokens = self._estimate_tokens(profile_section_full)
                
                if profile_tokens <= remaining_tokens:
                    profile_section = profile_section_full
                else:
                    # Truncate profile section
                    max_profile_chars = int(remaining_tokens * 3)
                    profile_section = profile_section_full[:max_profile_chars]
                    # Try to end at a reasonable point
                    last_separator = max(profile_section.rfind('\n════'), profile_section.rfind('\n'))
                    if last_separator > max_profile_chars * 0.7:
                        profile_section = profile_section[:last_separator]
                    profile_section += "\n\n[Candidate profile truncated to fit context window]"
                    logger.warning(f"Profile section truncated: {profile_tokens} → {self._estimate_tokens(profile_section)} tokens")
                
                logger.debug("Application profile context added")
            except Exception as e:
                logger.error(f"Error formatting application context: {e}")
                profile_section = self.NO_DATA_NOTE
        else:
            profile_section = self.NO_DATA_NOTE
        
        # Combine all sections (core instructions are NEVER truncated)
        instructions = core_instructions + jd_section + profile_section
        
        # Final check - if still over limit, truncate only non-core sections more aggressively
        total_tokens = self._estimate_tokens(instructions)
        if total_tokens > max_tokens:
            logger.warning(
                f"Instructions still exceed limit after truncation: {total_tokens} tokens. "
                f"Core Arjun instructions ({core_tokens} tokens) preserved. "
                f"Further truncating JD/Profile sections..."
            )
            # Remove JD and Profile, keep only core
            instructions = core_instructions + self.NO_DATA_NOTE
            logger.warning("JD and Profile sections removed to preserve core Arjun instructions")
        
        final_tokens = self._estimate_tokens(instructions)
        if final_tokens > max_tokens:
            logger.error(
                f"CRITICAL: Even core instructions exceed limit: {final_tokens} tokens. "
                f"This should not happen. Core instructions must be reduced manually."
            )
        else:
            logger.info(f"Instructions built: {final_tokens} tokens (core: {core_tokens}, JD/Profile: {final_tokens - core_tokens})")
        
        return instructions

