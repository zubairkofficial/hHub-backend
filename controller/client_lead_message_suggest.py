# E:\Shoaib\Projects\hHub\hHub-backend\controller\client_lead_message_suggest.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Set
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from helper.post_setting_helper import get_settings
from models.system_prompt import SystemPrompts  # Assuming you have this model
import json
import re

router = APIRouter()

# -------- Input model --------
class LeadItem(BaseModel):
    id: int
    description: Optional[str] = ""
    transcription: Optional[str] = ""
    potential_score: float = 0.0

class SuggestBody(BaseModel):
    items: List[LeadItem] = Field(default_factory=list)

# -------- Output model for strict parsing --------
class FollowupDecision(BaseModel):
    decision: Literal["send", "hold"]
    reason: str
    confidence: float
    suggested_channel: Literal["sms", "whatsapp", "email", "call", "chat", "unknown"] = "unknown"
    timing: Literal["now", "later", "schedule", "unknown"] = "unknown"
    follow_up_days: int = 0
    primary_message: str
    variants: List[str] = []
    safety_flags: List[str] = []
    used_lead_ids: List[int] = []


# ---------- Helpers ----------
ALLOWED_VARS: Set[str] = {"format_instructions", "mean_potential", "items_json"}

def sanitize_db_prompt(raw: Optional[str], allowed: Set[str] = ALLOWED_VARS) -> str:
    """
    Make DB-stored prompts safe for Python str.format by:
      1) Escaping ALL braces to literal text
      2) Un-escaping ONLY the placeholders we actually provide
    So stray {description}, {transcription}, etc. won't raise KeyError.
    """
    if not raw:
        return ""
    s = raw.replace("{", "{{").replace("}", "}}")
    for var in allowed:
        s = s.replace("{{" + var + "}}", "{" + var + "}")
    return s


# Fetch SystemPrompt from the DB or use default if not found
async def get_prompt_for_client(client_id: Optional[int]) -> str:
    if client_id:
        prompt = await SystemPrompts.filter(client_id=client_id).first()
        if prompt and getattr(prompt, "message_prompt", None):
            return prompt.message_prompt

    # Fallback to default prompt if client_id is not found or message_prompt is None
    default_prompt = await SystemPrompts.filter(client_id=None, role_name="Super Admin").first()
    return default_prompt.message_prompt if (default_prompt and getattr(default_prompt, "message_prompt", None)) else "Default message prompt for clients."


def _mean_score(items: List[LeadItem]) -> float:
    if not items:
        return 0.0
    s = sum(float(x.potential_score or 0.0) for x in items)
    return round(s / len(items), 3)


class FollowupSuggestService:
    def __init__(self):
        self.llm: Optional[ChatOpenAI] = None
        self.parser = PydanticOutputParser(pydantic_object=FollowupDecision)

    async def _init_llm(self):
        if self.llm is None:
            settings = await get_settings()
            api_key = settings["openai_api_key"]
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",   # keep consistent with your app
                temperature=0.2,
                api_key=api_key,
            )

    async def suggest(self, items: List[LeadItem], client_id: Optional[int] = None) -> dict:
        await self._init_llm()

        if not items:
            return {
                "decision": "hold",
                "reason": "No items provided.",
                "confidence": 0.7,
                "suggested_channel": "unknown",
                "timing": "unknown",
                "follow_up_days": 0,
                "primary_message": "",
                "variants": [],
                "safety_flags": ["no_data"],
                "used_lead_ids": []
            }

        mean_potential = _mean_score(items)

        # Get client-specific or default prompt dynamically
        message_prompt_raw = await get_prompt_for_client(client_id)
        # Ensure non-empty string
        message_prompt_raw = message_prompt_raw or "Default message prompt."

        # 🔒 Sanitize to prevent KeyError on unknown placeholders
        message_prompt = sanitize_db_prompt(message_prompt_raw, ALLOWED_VARS)

        # Create prompt with dynamic message (batch-first; only allowed variables used)
        prompt = ChatPromptTemplate.from_messages([
            ("system", message_prompt + "\n{format_instructions}"),
            ("user",
             "Context:\n"
             "- mean_potential_score: {mean_potential}\n"
             "- threshold_hint: 0.60\n\n"
             "Items JSON:\n```json\n{items_json}\n```\n"
             "Return ONLY the JSON (no prose).")
        ])

        # Prepare variables for formatting
        kwargs = {
            "format_instructions": self.parser.get_format_instructions(),
            "mean_potential": mean_potential,
            "items_json": json.dumps([i.model_dump() for i in items], ensure_ascii=False),
        }

        # Fail fast with a helpful 400 if any stray placeholder somehow remains
        try:
            formatted = prompt.format_messages(**kwargs)
        except KeyError as e:
            missing = str(e).strip("'")
            # Provide a clear error to the caller instead of a 500
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "prompt_placeholder_missing",
                    "missing": missing,
                    "hint": (
                        "Sanitize the DB prompt or include the placeholder in ALLOWED_VARS "
                        "and supply its value. Current allowed: "
                        f"{sorted(list(ALLOWED_VARS))}"
                    ),
                    "raw_prompt_excerpt": message_prompt_raw[:2000],  # small excerpt for debugging
                },
            )

        try:
            resp = await self.llm.ainvoke(formatted)
            decision: FollowupDecision = self.parser.parse(resp.content)
            data = decision.model_dump()

            # Safety tweak: enforce primary_message presence when decision=send
            if data["decision"] == "send" and not (data["primary_message"] or "").strip():
                data["decision"] = "hold"
                data["reason"] = (data.get("reason") or "") + " | Missing primary_message."
                data["confidence"] = min(0.5, float(data.get("confidence") or 0.5))

            # Ensure used_lead_ids is filled (nice for downstream)
            if not data.get("used_lead_ids"):
                data["used_lead_ids"] = [it.id for it in items]

            return data

        except HTTPException:
            # Bubble up our explicit HTTP errors unchanged
            raise
        except Exception as e:
            # Convert any other LLM/runtime issues to a structured hold
            return {
                "decision": "hold",
                "reason": f"LLM error: {e}",
                "confidence": 0.4,
                "suggested_channel": "unknown",
                "timing": "unknown",
                "follow_up_days": 0,
                "primary_message": "",
                "variants": [],
                "safety_flags": ["llm_error"],
                "used_lead_ids": [it.id for it in items],
            }


service = FollowupSuggestService()

@router.post("/followup/suggest")
async def followup_suggest(body: SuggestBody, client_id: Optional[int] = None):
    return await service.suggest(body.items, client_id)
