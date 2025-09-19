from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from helper.post_setting_helper import get_settings
from models.system_prompt import SystemPrompts  # Assuming you have this model
import json

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


# Fetch SystemPrompt from the DB or use default if not found
async def get_prompt_for_client(client_id: Optional[int]) -> str:
    if client_id:
        prompt = await SystemPrompts.filter(client_id=client_id).first()
        if prompt and prompt.message_prompt:
            return prompt.message_prompt
    
    # Fallback to default prompt if client_id is not found or message_prompt is None
    default_prompt = await SystemPrompts.filter(client_id=None, role_name="Super Admin").first()
    
    # If no prompt found, return a default message
    return default_prompt.message_prompt if default_prompt else "Default message prompt for clients."

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
                model="gpt-4o-mini",  # consistent with your app
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
        message_prompt = await get_prompt_for_client(client_id)

        # Ensure message_prompt is not None and is a string
        message_prompt = message_prompt or "Default message prompt."

        # Create prompt with dynamic message
        prompt = ChatPromptTemplate.from_messages([ 
            ("system", message_prompt + "\n{format_instructions}"),  # concatenating the valid string
            ("user",
             "Context:\n"
             "- mean_potential_score: {mean_potential}\n"
             "- threshold_hint: 0.60\n\n"
             "Items JSON:\n```json\n{items_json}\n```\n"
             "Return ONLY the JSON (no prose).")
        ])

        formatted = prompt.format_messages(
            format_instructions=self.parser.get_format_instructions(),
            mean_potential=mean_potential,
            items_json=json.dumps([i.model_dump() for i in items], ensure_ascii=False)
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

            return data

        except Exception as e:
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
                "used_lead_ids": []
            }

service = FollowupSuggestService()

@router.post("/followup/suggest")
async def followup_suggest(body: SuggestBody, client_id: Optional[int] = None):
    return await service.suggest(body.items, client_id)
