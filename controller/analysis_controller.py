# controller/analysis_controller.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import os, json, re
from typing import Optional

# OpenAI async client (same lib you used elsewhere)
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
# LLM Prompt - Receptionist Performance Evaluation
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an AI assistant that evaluates dental clinic receptionist performance based on call transcripts.\n\n"
    
    "CRITICAL: Only rate calls where the caller is a PATIENT seeking dental services. "
    "Do NOT rate calls about: jobs, internships, vendor inquiries, friend/family behalf calls (unless booking for them), spam, or wrong numbers. "
    "If the call is not patient-related, return {\"analysis_score\": 0}.\n\n"
    
    "For valid PATIENT calls, evaluate the receptionist on these criteria (0-100 scale):\n\n"
    
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
    "   - Voicemail only (no human interaction): 0 points\n"
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
    "   - Invalid call (job inquiry, spam, voicemail only): 0\n\n"
    
    "Return ONLY a JSON object:\n"
    "{\"analysis_score\": <0-100>}"
)

def user_prompt_for(transcription: str) -> str:
    return f'Call Transcript:\n"""\n{transcription}\n"""\n\nEvaluate the receptionist\'s performance and return the analysis_score.'


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _heuristic_score(transcription: Optional[str]) -> int:
    """Fallback heuristic for receptionist performance (0–100)."""
    if not transcription or not transcription.strip():
        return 0
    t = transcription.lower()

    # Check if it's a patient call
    non_patient = ["job", "internship", "employment", "hiring", "vendor", "delivery", "sales call"]
    if any(word in t for word in non_patient):
        return 0

    # Check for voicemail
    voicemail_indicators = ["leave a message", "we will call you back", "please hold"]
    if any(phrase in t for phrase in voicemail_indicators) and "receptionist:" not in t.lower():
        return 0

    score = 30  # base score for valid patient call

    # Positive receptionist behaviors
    friendly = ["thank you", "how can i help", "happy to", "of course", "absolutely", "great question"]
    questions = ["new patient", "insurance", "what brings you", "when would you like", "any pain", "symptoms"]
    scheduling = ["schedule", "book", "appointment", "available", "confirm", "see you"]
    
    # Negative behaviors
    rude = ["busy", "can't help", "no time", "call back later", "that's not my job"]

    score += sum(3 for phrase in friendly if phrase in t)
    score += sum(4 for phrase in questions if phrase in t)
    score += sum(5 for phrase in scheduling if phrase in t)
    score -= sum(10 for phrase in rude if phrase in t)

    return max(0, min(100, int(score)))

def _extract_json_int(raw: str) -> Optional[int]:
    """
    Try to parse {"analysis_score": <int>} from model output.
    Handles code fences or surrounding text.
    """
    if not raw:
        return None
    # strip code fences if present
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()

    # direct JSON first
    try:
        data = json.loads(raw)
        val = data.get("analysis_score", None)
        if isinstance(val, (int, float)):
            return max(0, min(100, int(val)))
    except Exception:
        pass

    # fallback: regex find a number after the key
    m = re.search(r'"analysis_score"\s*:\s*(\d{1,3})', raw)
    if m:
        return max(0, min(100, int(m.group(1))))

    return None


# ──────────────────────────────────────────────────────────────────────────────
# LLM scorer (async)
# ──────────────────────────────────────────────────────────────────────────────

async def llm_analysis_score(transcription: str) -> int:
    """
    Calls OpenAI with the receptionist evaluation prompt and returns an int 0–100.
    Falls back to heuristic if something goes wrong.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # no key set; fall back
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
        val = _extract_json_int(raw)
        if val is None:
            # parsing failed → heuristic
            return _heuristic_score(transcription)
        return val
    except Exception:
        # network/api error → heuristic
        return _heuristic_score(transcription)


# ──────────────────────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/analysis/score", response_model=AnalysisResponse, tags=["analysis"])
async def score(req: AnalysisRequest):
    try:
        # Prefer LLM; graceful fallback to heuristic
        analysis_score = await llm_analysis_score(req.transcription)

        return AnalysisResponse(
            client_id=req.client_id,
            contact_number=req.contact_number,
            analysis_score=analysis_score,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))