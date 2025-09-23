# E:\Shoaib\Projects\hHub\hHub-backend\controller\client_lead_message_suggest.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Set  # using builtin list[...] below
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from helper.post_setting_helper import get_settings
from models.system_prompt import SystemPrompts
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# -------- Input model --------
class LeadItem(BaseModel):
    id: int
    description: Optional[str] = ""
    transcription: Optional[str] = ""
    potential_score: float = 0.0

class SuggestBody(BaseModel):
    items: list[LeadItem] = Field(default_factory=list)

# -------- Output model (matches your Primary/Backup prompt) --------
class ActionBlock(BaseModel):
    action: str
    reason: str
    channel: str        # e.g., "SMS — same day" or "Email — immediate"
    message: str        # 300–400 chars, starts with your required prefix
    model_config = ConfigDict(extra="ignore")

class FollowupDecision(BaseModel):
    decision: Literal["send", "hold"]
    primary: Optional[ActionBlock] = None
    backup: Optional[ActionBlock] = None
    confidence: float
    lead_ids: list[int]
    model_config = ConfigDict(extra="ignore")

# ---------- Helpers ----------
ALLOWED_VARS: Set[str] = {"format_instructions", "mean_potential", "items_json"}

def sanitize_db_prompt(raw: Optional[str], allowed: Set[str] = ALLOWED_VARS) -> str:
    """Escape all braces then un-escape only allowed placeholders."""
    if not raw:
        return ""
    s = raw.replace("{", "{{").replace("}", "}}")
    for var in allowed:
        s = s.replace("{{" + var + "}}", "{" + var + "}")
    return s

async def get_prompt_for_client(client_id: Optional[int]) -> str:
    if client_id:
        prompt = await SystemPrompts.filter(client_id=client_id).first()
        if prompt and getattr(prompt, "message_prompt", None):
            return prompt.message_prompt
    default_prompt = await SystemPrompts.filter(client_id=None, role_name="Super Admin").first()
    return default_prompt.message_prompt if (default_prompt and getattr(default_prompt, "message_prompt", None)) else "Default message prompt for clients."

def _mean_score(items: list[LeadItem]) -> float:
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
                model="gpt-4o-mini",
                temperature=0.2,
                api_key=api_key,
            )

    async def suggest(self, items: list[LeadItem], client_id: Optional[int] = None) -> dict:
        await self._init_llm()

        if not items:
            return {"decision": "hold", "primary": None, "backup": None, "confidence": 0.7, "lead_ids": []}

        mean_potential = _mean_score(items)

        # Build prompt
        message_prompt_raw = await get_prompt_for_client(client_id)
        message_prompt = sanitize_db_prompt(message_prompt_raw or "Default message prompt.", ALLOWED_VARS)

        prompt = ChatPromptTemplate.from_messages([
            ("system", message_prompt + "\n{format_instructions}"),
            ("user",
             "Context:\n"
             "- mean_potential_score: {mean_potential}\n"
             "- threshold_hint: 0.60\n\n"
             "Items JSON:\n```json\n{items_json}\n```\n"
             "Return ONLY the JSON (no prose).")
        ])

        kwargs = {
            "format_instructions": self.parser.get_format_instructions(),
            "mean_potential": mean_potential,
            "items_json": json.dumps([i.model_dump() for i in items], ensure_ascii=False),
        }

        try:
            formatted = prompt.format_messages(**kwargs)
        except KeyError as e:
            missing = str(e).strip("'")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "prompt_placeholder_missing",
                    "missing": missing,
                    "hint": f"Allowed placeholders: {sorted(list(ALLOWED_VARS))}",
                    "raw_prompt_excerpt": (message_prompt_raw or "")[:2000],
                },
            )

        # Call LLM
        resp = await self.llm.ainvoke(formatted)
        raw_content = resp.content or ""
        logger.info("followup_suggest LLM raw snippet: %s", raw_content[:500])

        # 1) Preferred parse (new schema)
        try:
            decision = self.parser.parse(raw_content)
            data = decision.model_dump()
        except Exception as e1:
            logger.warning("Primary parse failed: %s", e1)

            # 2) Backward-compat: try to coerce from old schema (primary_message, action, reason, channel at top)
            try:
                raw = json.loads(raw_content)
            except Exception as e2:
                logger.error("Failed to JSON-decode LLM output: %s", e2)
                return {
                    "decision": "hold",
                    "primary": None,
                    "backup": None,
                    "confidence": 0.4,
                    "lead_ids": [it.id for it in items],
                }

            def coerce_action_block(src: dict, fallback_msg_key: str = "primary_message") -> Optional[dict]:
                if not isinstance(src, dict):
                    return None
                msg = src.get("message") or raw.get(fallback_msg_key)
                act = src.get("action")  or raw.get("action")
                rsn = src.get("reason")  or raw.get("reason")
                chn = src.get("channel") or raw.get("channel")
                if not msg or not act or not rsn or not chn:
                    return None
                return {"action": act, "reason": rsn, "channel": chn, "message": msg}

            primary_src = raw.get("primary") if isinstance(raw.get("primary"), dict) else {}
            backup_src  = raw.get("backup")  if isinstance(raw.get("backup"),  dict) else {}

            transformed = {
                "decision": raw.get("decision", "hold"),
                "primary":  coerce_action_block(primary_src) or coerce_action_block(raw, "primary_message"),
                "backup":   coerce_action_block(backup_src),
                "confidence": float(raw.get("confidence", 0.6)),
                "lead_ids": raw.get("used_lead_ids") or raw.get("lead_ids") or [it.id for it in items],
            }

            try:
                decision = FollowupDecision(**transformed)
                data = decision.model_dump()
            except Exception as e3:
                logger.error("Transformed parse still invalid: %s | data=%s", e3, transformed)
                data = {
                    "decision": "hold",
                    "primary": None,
                    "backup": None,
                    "confidence": 0.4,
                    "lead_ids": [it.id for it in items],
                }

        # Enforce: if send, primary must exist with a message
        if data["decision"] == "send":
            ok = bool(data.get("primary") and (data["primary"].get("message") or "").strip())
            if not ok:
                data["decision"] = "hold"
                data["confidence"] = min(0.5, float(data.get("confidence") or 0.5))

        if not data.get("lead_ids"):
            data["lead_ids"] = [it.id for it in items]

        return data

service = FollowupSuggestService()

@router.post("/followup/suggest")
async def followup_suggest(body: SuggestBody, client_id: Optional[int] = None):
    return await service.suggest(body.items, client_id)
