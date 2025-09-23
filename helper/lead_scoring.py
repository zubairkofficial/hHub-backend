from __future__ import annotations

from typing import Optional, Set
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser

from models.system_prompt import SystemPrompts
from helper.post_setting_helper import get_settings

load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class LeadAnalysis(BaseModel):
    intent_score: float = Field(description="Score for customer intent (0-100)")
    urgency_score: float = Field(description="Score for urgency level (0-100)")
    overall_score: float = Field(description="Combined score (0-100)")
    potential_score: float = Field(description="Score for Potential level (0-100)")
    analysis_summary: str = Field(description="Comprehensive analysis incorporating all provided data")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers (sanitization + debugging)
# ──────────────────────────────────────────────────────────────────────────────

# Placeholders allowed inside DB analytics prompt
ALLOWED_ANALYTICS_VARS: Set[str] = {
    "client_type", "service", "state", "city", "first_call",
    "rota_plan", "previous_analysis", "transcription"
}
# Placeholders allowed inside DB score prompt
ALLOWED_SCORE_VARS: Set[str] = {"format_instructions", "analysis_summary"}

def _sanitize_db_prompt(raw: Optional[str], allowed: Set[str]) -> str:
    """
    Escape all braces, then un-escape only the allowed placeholders.
    Prevents KeyError if DB text contains stray {like_this}.
    """
    if not raw:
        return ""
    s = raw.replace("{", "{{").replace("}", "}}")
    for var in allowed:
        s = s.replace("{{" + var + "}}", "{" + var + "}")
    return s

def _is_blank(s: Optional[str]) -> bool:
    return not (s and str(s).strip())

def _log_messages(title: str, messages) -> None:
    print(f"\n===== {title} =====")
    for i, m in enumerate(messages):
        role = getattr(m, "type", "message")
        print(f"\n--- [{i}] {role.upper()} ---\n{m.content}\n")
    print("=" * 40)


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class LeadScoringService:
    def __init__(self):
        # Initialize without API key, will be set in async methods
        self.llm = None
        self.parser = PydanticOutputParser(pydantic_object=LeadAnalysis)

        # ===== DEFAULT PROMPTS (YOUR TEXT) =====
        self.default_analytics_prompt = (
            "You are an expert call analyst. Given the call transcription(s), previous analysis, and client context, "
            "write a concise summary (30–40 words) that highlights key engagement signals, concerns, and conversion potential. "
            "Avoid detailed breakdowns—focus only on actionable insights.\n\n"
            "Context:\n\n"
            "Client Type: {client_type}\n\n"
            "Service: {service}\n\n"
            "Location: {state}, {city}\n\n"
            "First Call: {first_call}\n\n"
            "Rota Plan: {rota_plan}\n\n"
            "Previous Analysis (if any):\n"
            "{previous_analysis}\n\n"
            "New Call Transcriptions:"
        )

        self.default_score_prompt = (
            "You are an expert lead scoring analyst. Use the HHub Lead Scoring Matrix below to evaluate leads. "
            "Assign scores for each aspect on a 0–100 scale:\n\n"
            "Customer Intent (0–100) – Reflects whether the lead mentioned treatment keywords (e.g., “braces,” “Invisalign,” "
            "“consultation”), referral sources, or general service inquiries.\n\n"
            "Urgency (0–100) – Based on urgency cues (e.g., “soon,” “this week,” “urgent”) and appointment scheduling likelihood.\n\n"
            "Overall (0–100) – Weighted combination of call type, call outcome, duration, and other parameters in the matrix.\n\n"
            "Potential Score (0–100) – An aggregated measure that blends Intent, Urgency, and Overall into a single normalized score, "
            "representing the lead’s readiness to convert.\n\n"
            "Instructions: Apply the scoring rules from the matrix (e.g., +40 for new patient inquiry, +25 for “consultation,” "
            "-50 for spam, +50 for scheduled appointment, etc.). Normalize the raw point totals into 0–100 scores for each category. "
            "For the Potential Score, combine the three category scores (e.g., average or weighted average) into a single 0–100 score.\n\n"
            "Output: Provide scores with brief justifications (30–40 words total) citing observed triggers (keywords, urgency cues, "
            "referral source, call duration, etc.).\n\n"
            "{format_instructions}"
        )

    async def _get_api_key(self):
        settings = await get_settings()
        return settings["openai_api_key"]

    async def _init_llm(self):
        if self.llm is None:
            api_key = await self._get_api_key()
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=api_key
            )

    async def _get_rows(self, client_id: Optional[int]):
        """
        Fetch Super Admin (global) and Client rows.
        - Super Admin: client_id=None, role_name='Super Admin' (preferred)
        - Fallback global: client_id=None (any)
        - Client: client_id=client_id
        """
        try:
            super_admin = await SystemPrompts.filter(client_id=None, role_name="Super Admin").first()
            if not super_admin:
                super_admin = await SystemPrompts.filter(client_id=None).first()

            client_row = None
            if client_id is not None:
                client_row = await SystemPrompts.filter(client_id=client_id).first()

            return client_row, super_admin
        except Exception as e:
            print(f"[prompts] Error fetching SystemPrompts rows: {e}")
            return None, None

    def _pick(self, row, *names) -> Optional[str]:
        if not row:
            return None
        for nm in names:
            val = getattr(row, nm, None)
            if not _is_blank(val):
                return str(val)
        return None

    async def get_prompts(self, client_id: Optional[int] = None):
        """
        Precedence per field: Super Admin -> Client -> Built-in default.
        Also:
        - Ensure analytics prompt always includes {transcription}
        - Ensure score prompt contains {format_instructions}
        - Sanitize both prompts to avoid KeyErrors from stray braces
        """
        client_row, super_admin = await self._get_rows(client_id)

        # ANALYTICS
        analytics_prompt = (
            self._pick(super_admin, "analytics_prompt")
            or self._pick(client_row, "analytics_prompt")
            or self.default_analytics_prompt
        )
        src_a = (
            "super_admin" if analytics_prompt == self._pick(super_admin, "analytics_prompt")
            else "client" if analytics_prompt == self._pick(client_row, "analytics_prompt")
            else "default"
        )

        # Guarantee transcript inclusion:
        if "{transcription}" not in analytics_prompt:
            if "New Call Transcriptions" in analytics_prompt:
                analytics_prompt = analytics_prompt.rstrip() + "\n{transcription}"
            else:
                analytics_prompt = analytics_prompt.rstrip() + "\n\nNew Call Transcriptions:\n{transcription}"

        analytics_prompt = _sanitize_db_prompt(analytics_prompt, ALLOWED_ANALYTICS_VARS)

        # SCORE (supports both 'summery_score' and 'score_prompt')
        score_prompt = (
            self._pick(super_admin, "summery_score", "score_prompt")
            or self._pick(client_row, "summery_score", "score_prompt")
            or self.default_score_prompt
        )
        src_s = (
            "super_admin" if score_prompt == self._pick(super_admin, "summery_score", "score_prompt")
            else "client" if score_prompt == self._pick(client_row, "summery_score", "score_prompt")
            else "default"
        )

        score_prompt = _sanitize_db_prompt(score_prompt, ALLOWED_SCORE_VARS)
        if "{format_instructions}" not in score_prompt:
            score_prompt = score_prompt.rstrip() + "\n\n{format_instructions}"

        print(f"[prompts] analytics source: {src_a}")
        print(f"[prompts] score source    : {src_s}")

        return {
            "analytics_prompt": analytics_prompt,
            "score_prompt": score_prompt
        }

    async def generate_summary(
        self,
        transcription: str,
        client_type: Optional[str] = None,
        service: Optional[str] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        first_call: Optional[bool] = None,
        rota_plan: Optional[str] = None,
        previous_analysis: Optional[str] = None,
        client_id: Optional[int] = None
    ) -> dict:

        await self._init_llm()
        prompts = await self.get_prompts(client_id=client_id)

        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", prompts['analytics_prompt']),
        ])

        try:
            formatted_prompt = summary_prompt.format_messages(
                transcription=transcription,
                previous_analysis=previous_analysis or "No previous analysis available",
                client_type=client_type or "Not specified",
                service=service or "Not specified",
                state=state or "Not specified",
                city=city or "Not specified",
                first_call=first_call if first_call is not None else "Not specified",
                rota_plan=rota_plan or "Not specified"
            )
        except KeyError as e:
            missing = str(e).strip("'")
            print(f"[prompts] Missing placeholder in analytics prompt: {missing}")
            raise

        _log_messages("ANALYTICS PROMPT (FINAL)", formatted_prompt)

        response = await self.llm.ainvoke(formatted_prompt)
        return {"summary": (response.content or "").strip(), 'client_id': client_id}

    async def score_summary(self, analysis_summary: str, client_id: Optional[int] = None) -> LeadAnalysis:
        await self._init_llm()
        prompts = await self.get_prompts(client_id=client_id)

        print(f"bhai client_id = {client_id} or neechy wala score prompt hai")
        print(prompts['score_prompt'])
        print("yeh raha analysis summary:")
        print(analysis_summary)

        score_prompt = ChatPromptTemplate.from_messages([
            ("system", prompts['score_prompt']),
            ("user", "Analysis Summary:\n{analysis_summary}")
        ])

        try:
            formatted_prompt = score_prompt.format_messages(
                analysis_summary=analysis_summary,
                format_instructions=self.parser.get_format_instructions()
            )
        except KeyError as e:
            missing = str(e).strip("'")
            print(f"[prompts] Missing placeholder in score prompt: {missing}")
            raise

        _log_messages("SCORE PROMPT (FINAL)", formatted_prompt)

        response = await self.llm.ainvoke(formatted_prompt)
        analysis = self.parser.parse(response.content)
        return analysis

    async def analyze_lead(
        self,
        transcription: str,
        client_type: Optional[str] = None,
        service: Optional[str] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        first_call: Optional[bool] = None,
        rota_plan: Optional[str] = None,
        previous_analysis: Optional[str] = None,
        client_id: Optional[int] = None
    ) -> dict:

        try:
            # 1) Generate analysis summary
            summary_result = await self.generate_summary(
                transcription=transcription,
                client_type=client_type,
                service=service,
                state=state,
                city=city,
                first_call=first_call,
                rota_plan=rota_plan,
                previous_analysis=previous_analysis,
                client_id=client_id
            )

            # 2) Score the generated analysis summary
            scoring_result = await self.score_summary(summary_result["summary"], client_id=client_id)

            # 3) Return all fields (including potential_score)
            return {
                "summary": summary_result["summary"],
                "intent_score": scoring_result.intent_score,
                "urgency_score": scoring_result.urgency_score,
                "overall_score": scoring_result.overall_score,
                "potential_score": scoring_result.potential_score,
                "analysis_summary": scoring_result.analysis_summary,
                "client_id": client_id
            }

        except Exception as e:
            print(f"Error in lead analysis: {e}")
            return {
                "error": str(e),
                "summary": "Error occurred during analysis",
                "intent_score": 0,
                "urgency_score": 0,
                "overall_score": 0,
                "potential_score": 0,
                "analysis_summary": "Analysis could not be completed due to an error"
            }
