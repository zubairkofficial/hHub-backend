# controller/analysis_controller.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import os, json, re, logging
from typing import Optional, Tuple

# OpenAI async client
from openai import AsyncOpenAI

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    client_id: int = Field(..., description="Owner client id (echoed back)")
    contact_number: str = Field(..., description="Raw or E.164 (echoed back)")
    transcription: str = Field(..., description="Transcript text to analyse")

class AnalysisResponse(BaseModel):
    client_id: int
    contact_number: str
    analysis_score: int

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

# If there is no two-way human conversation, return this score (NOT forced 0).
MONOLOGUE_SCORE = int(os.getenv("ANALYSIS_MONOLOGUE_SCORE", "0"))

# Toggle extra logs: ANALYSIS_DEBUG=1
DEBUG = os.getenv("ANALYSIS_DEBUG", "0") == "1"
log = logging.getLogger("uvicorn.error")

SYSTEM_PROMPT = (
    "You are an AI assistant that evaluates dental clinic receptionist performance based on call transcripts.\n\n"
    
    "CRITICAL: Only rate calls where the caller is a PATIENT seeking dental services. "
    "Do NOT rate calls about: jobs, internships, vendor inquiries, friend/family behalf calls (unless booking for them), spam, or wrong numbers. "
    "If the call is not patient-related, return {\"analysis_score\": 0}.\n\n"
    
    "If there is no two-way human conversation between a caller/patient and a receptionist/staff (e.g., voicemail/IVR/one-sided monologue), "
    f"return {{\"analysis_score\": {MONOLOGUE_SCORE}}}.\n\n"
    
    "For valid PATIENT calls with two-way conversation, evaluate the receptionist on these criteria (0-100 scale):\n\n"
    
    "1. TONE & BEHAVIOR (30 points)\n"
    "   - Friendly, warm, and professional greeting\n"
    "   - Patient, empathetic, and respectful throughout\n"
    "   - No rudeness, impatience, or dismissiveness\n"
    "   - Maintains positive tone even if busy or unable to help immediately\n\n"
    
    "2. DENTAL KNOWLEDGE & ACCURACY (25 points)\n"
    "   - Correctly answers questions about treatments (cleanings, braces, Invisalign, root canals, implants, extractions, cosmetics)\n"
    "   - Provides accurate information about procedures, insurance, pricing\n"
    "   - Demonstrates understanding of dental terminology and symptoms\n"
    "   - Doesn't give misleading or incorrect medical advice\n\n"
    
    "3. LEAD QUALIFICATION & QUESTIONS (25 points)\n"
    "   - Asks relevant questions: new patient status, reason for visit, urgency, insurance, preferred dates\n"
    "   - Gathers symptoms clearly if patient mentions pain or dental issues\n"
    "   - Shows genuine interest in helping the patient\n"
    "   - Doesn't skip important qualifying questions\n\n"
    
    "4. APPOINTMENT HANDLING (20 points)\n"
    "   - Actively attempts to schedule or offers concrete next steps\n"
    "   - Checks availability and provides options\n"
    "   - Confirms details clearly (date, time, what to bring)\n"
    "   - Handles objections or scheduling conflicts professionally\n"
    "   - Provides alternative solutions if first choice unavailable\n\n"
    
    "DEDUCTIONS:\n"
    "   - Rude, dismissive, or impatient tone: -20 to -40 points\n"
    "   - Incorrect dental information given: -15 to -30 points\n"
    "   - Failed to ask basic qualifying questions: -10 to -20 points\n"
    "   - Didn't attempt to schedule when patient was ready: -15 to -25 points\n"
    "   - Put patient on hold excessively without explanation: -10 points\n\n"
    
    "EXAMPLES:\n"
    "   - Perfect call (friendly, knowledgeable, scheduled appointment): 90-100\n"
    "   - Good call (professional, answered questions, but didn't close): 70-85\n"
    "   - Adequate call (polite but missed opportunities, vague answers): 50-65\n"
    "   - Poor call (rushed, dismissive, or gave wrong info): 20-40\n"
    f"   - Invalid/voicemail/monologue (no two-way): {MONOLOGUE_SCORE}\n\n"
    
    "Return ONLY a JSON object:\n"
    "{\"analysis_score\": <0-100>}"
)

def user_prompt_for(transcription: str) -> str:
    return (
        "First, check if there is a two-way human conversation between a caller/patient and a receptionist/staff. "
        f"If not, return {{\"analysis_score\": {MONOLOGUE_SCORE}}}.\n\n"
        f'Call Transcript:\n"""\n{transcription}\n"""\n\n'
        "If it is a valid two-way patient call, evaluate the receptionist and return only "
        "{\"analysis_score\": <0-100>}."
    )

# ──────────────────────────────────────────────────────────────────────────────
# Conversation detection helpers
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_LIKE = (r"\bai\b", r"\bsystem\b", r"\bivr\b", r"\bauto( |-)attendant\b", r"\bauto( |-)message\b")

RECEPTIONIST_TAGS = (
    r"receptionist", r"front\s*desk", r"staff", r"assistant", r"agent", r"operator", r"office", r"desk"
)

CALLER_TAGS = (
    r"patient", r"caller", r"client", r"dr\.", r"mr\.", r"mrs\.", r"ms\.", r"\bparent\b",
    r"\bdaughter\b", r"\bfather\b", r"\bmother\b", r"\bson\b"
)

VOICEMAIL_PHRASES = (
    "leave a message", "we will call you back", "on the phone or assisting another patient",
    "after the tone", "your call is important", "please hold", "press 1", "press one",
    "office hours", "business hours"
)

def _split_lines(t: str) -> list[str]:
    # Normalize bullets, keep one utterance per line
    t = t.replace("\r", "")
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.MULTILINE)  # strip md bullets like "- **AI:**"
    return [ln.strip() for ln in t.split("\n") if ln.strip()]

def _tag_of(line: str) -> Optional[str]:
    """
    Try to detect speaker from a leading label (e.g., '**Helena (Receptionist):**').
    If missing/unclear, infer from content as a fallback.
    """
    m = re.match(r"^\**\s*([A-Za-z .()\-]+?)\s*:\s*", line)
    label = (m.group(1).strip().lower() if m else "")

    if label:
        if any(re.search(p, label) for p in SYSTEM_LIKE): return "system"
        if any(re.search(p, label) for p in RECEPTIONIST_TAGS): return "reception"
        if any(re.search(p, label) for p in CALLER_TAGS): return "caller"
        # generic fallbacks on label
        if "reception" in label or "front" in label or "desk" in label or "staff" in label or "office" in label:
            return "reception"
        if "patient" in label or "caller" in label or "parent" in label:
            return "caller"

    # Content-based FALLBACK (handles lines without clear labels)
    low = line.lower()
    if re.search(r"\b(this is|my name is|i would like|i'm |i am |can you|could you|calling from|i want to)\b", low):
        return "caller"
    if re.search(r"\b(how (can|may|might) i help|let me check|we can schedule|do you have insurance|when would you like)\b", low):
        return "reception"

    return None

def _conversation_stats(transcription: str) -> Tuple[int, int, int, bool, bool]:
    """
    Returns: (caller_lines, reception_lines, alternations, has_voicemailish, has_system_only)
    """
    lines = _split_lines(transcription)
    caller = reception = alternations = 0
    has_voicemailish = False
    has_system_only = True
    last_role = None

    low = transcription.lower()
    if any(p in low for p in VOICEMAIL_PHRASES):
        has_voicemailish = True

    for ln in lines:
        role = _tag_of(ln)
        if role == "caller":
            caller += 1
            has_system_only = False
        elif role == "reception":
            reception += 1
            has_system_only = False

        # alternations only count caller<->reception changes
        cur = role if role in ("caller", "reception") else None
        if cur and last_role and cur != last_role:
            alternations += 1
        if cur:
            last_role = cur

        if DEBUG:
            log.info(f"TALK role={role} | line={ln[:160]}")

    if DEBUG:
        log.info(f"conv_stats caller={caller} reception={reception} alternations={alternations} "
                 f"has_vm={has_voicemailish} system_only={has_system_only}")

    return caller, reception, alternations, has_voicemailish, has_system_only

def _has_two_way_conversation(transcription: str) -> bool:
    caller, reception, alternations, has_vm, system_only = _conversation_stats(transcription)

    # No human lines at all
    if system_only:
        return False

    # If we saw both sides at least once, accept even if alternations==0 (some transcripts group turns)
    if caller >= 1 and reception >= 1:
        return True

    # If only one side present or voicemailish with no receptionist, reject
    if has_vm and reception == 0:
        return False
    if caller == 0 or reception == 0:
        return False

    # Fallback strict rule (rarely reached now)
    return alternations >= 1

# ──────────────────────────────────────────────────────────────────────────────
# Heuristic / LLM
# ──────────────────────────────────────────────────────────────────────────────

def _heuristic_score(transcription: Optional[str]) -> int:
    if not transcription or not transcription.strip():
        return 0

    # monologue / voicemail → configured score
    if not _has_two_way_conversation(transcription):
        return MONOLOGUE_SCORE

    t = transcription.lower()

    # Non-patient intents still zero
    non_patient = ["job", "internship", "employment", "vendor", "delivery", "sales call", "wrong number"]
    if any(word in t for word in non_patient):
        return 0

    score = 30  # base for valid patient two-way

    friendly = ["thank you", "how can i help", "happy to", "of course", "absolutely", "great question"]
    questions = ["new patient", "insurance", "what brings you", "when would you like", "any pain", "symptoms"]
    scheduling = ["schedule", "book", "appointment", "available", "confirm", "see you"]
    rude = ["can't help", "no time", "call back later", "that's not my job", "busy and can't"]

    score += sum(3 for phrase in friendly if phrase in t)
    score += sum(4 for phrase in questions if phrase in t)
    score += sum(5 for phrase in scheduling if phrase in t)
    score -= sum(10 for phrase in rude if phrase in t)

    return max(0, min(100, int(score)))

def _extract_json_int(raw: str) -> Optional[int]:
    if not raw:
        return None
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
        val = data.get("analysis_score", None)
        if isinstance(val, (int, float)):
            return max(0, min(100, int(val)))
    except Exception:
        pass
    m = re.search(r'"analysis_score"\s*:\s*(\d{1,3})', raw)
    if m:
        return max(0, min(100, int(m.group(1))))
    return None

async def llm_analysis_score(transcription: str) -> int:
    # If no two-way human conversation → monologue score (not hard 0)
    if not _has_two_way_conversation(transcription):
        if DEBUG:
            log.info("two-way conversation = FALSE → returning MONOLOGUE_SCORE")
        return MONOLOGUE_SCORE

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if DEBUG:
            log.info("OPENAI_API_KEY missing → using heuristic")
        return _heuristic_score(transcription)

    client = AsyncOpenAI(api_key=api_key)
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt_for(transcription)},
            ],
        )
        raw = (completion.choices[0].message.content or "").strip()
        if DEBUG:
            log.info(f"LLM raw: {raw[:400]}")
        val = _extract_json_int(raw)
        if val is None:
            if DEBUG:
                log.info("LLM parse failed → heuristic")
            return _heuristic_score(transcription)
        return val
    except Exception as e:
        if DEBUG:
            log.exception(f"LLM exception → heuristic: {e}")
        return _heuristic_score(transcription)

# ──────────────────────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/analysis/score", response_model=AnalysisResponse, tags=["analysis"])
async def score(req: AnalysisRequest):
    try:
        analysis_score = await llm_analysis_score(req.transcription)
        return AnalysisResponse(
            client_id=req.client_id,
            contact_number=req.contact_number,
            analysis_score=analysis_score,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
