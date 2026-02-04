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
    
    # Fallback when admin dashboard has no context. Primary context is stored in DB (job_descriptions.context).
    BASE_INSTRUCTIONS = """
You are a professional interviewer. Ask one question at a time. Be brief (1-3 lines) and natural. Do not conclude or say goodbye until the system signals the interview is ending. Keep asking the next question.
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
        
        # Replace SCHEDULED DURATION line (keep "until system signals... wind up naturally" for all durations)
        scheduled_duration_base = (
            "**SCHEDULED DURATION: 30 minutes.** Intro: first ~5 min. Main Q&A: rest of the time. "
            "Keep asking questions from the question bank until the system signals that the interview is ending. "
            "Do not stop or say goodbye on your own; only when you receive that signal, wind up naturally (e.g. \"Let's wind up\", wish them all the best) and keep it smooth."
        )
        scheduled_duration_adapted = (
            f"**SCHEDULED DURATION: {duration_minutes} minutes.** Intro: first ~{intro_minutes} min. Main Q&A: rest of the time. "
            "Keep asking questions from the question bank until the system signals that the interview is ending. "
            "Do not stop or say goodbye on your own; only when you receive that signal, wind up naturally (e.g. \"Let's wind up\", wish them all the best) and keep it smooth."
        )
        adapted = adapted.replace(scheduled_duration_base, scheduled_duration_adapted)
        
        # Replace Rule 8 first line (intro minutes only)
        adapted = re.sub(
            r"(- First ~)5( min: Intro only)",
            rf"\g<1>{intro_minutes}\2",
            adapted,
            count=1
        )
        
        # Replace phase 1 timing
        phase1_pattern = r"### PHASE 1: WELCOME \(first ~5 min\)"
        new_phase1 = f"### PHASE 1: WELCOME (first ~{intro_minutes} min)"
        adapted = re.sub(phase1_pattern, new_phase1, adapted)
        
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

