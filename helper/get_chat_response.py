# helper/get_chat_response.py

import os
import json
from typing import Any, Dict, List
import re
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from models.message import Message
from models.system_prompt import SystemPrompts
from helper.get_data import get_client_data

from agents.orchestrator import run_with_agent

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

# HARD SWITCH: allow general questions? default OFF
ALLOW_GENERAL_QA = os.getenv("ALLOW_GENERAL_QA", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

# ----------------------------------------------------
# Scope policy
# ----------------------------------------------------
APP_ONLY_HINT = (
    "I can help with Houmanity tasks only — e.g., view or update **leads** and **clinics**, "
    "or answer questions about your account and data in Houmanity. "
    "Try: “show lead id 42”, “find lead by email ...”, “rename clinic 5 to Downtown Dental”."
)

# -----------------------------
# Base model
# -----------------------------
BASE_MODEL_NAME = "gpt-4.1"
model = init_chat_model(BASE_MODEL_NAME, model_provider="openai")

# -----------------------------
# Intent helpers
# -----------------------------
_AGENT_KEYWORDS = (
    # Lead-related
    "lead", "leads", "update lead", "edit lead", "change lead",
    "lead id", "lead#", "lookup lead", "find lead", "search lead",
    "client lead", "client_leads", "crm",
    # Clinic-related
    "clinic", "clinics", "update clinic", "edit clinic", "change clinic",
    "rename clinic", "set clinic name", "clinic id", "clinic#", "office", "location"
)
_LEAD_NUM_TAIL = re.compile(r"\blead\s*(?:id|#)?\s*\d+\b", re.IGNORECASE)   # lead 16
_LEAD_NUM_HEAD = re.compile(r"\b\d+\s*lead\b", re.IGNORECASE)               # 16 lead

def _looks_like_agent_task(user_msg: str) -> bool:
    if not user_msg:
        return False
    return any(k in user_msg.lower() for k in _AGENT_KEYWORDS) or \
           bool(_LEAD_NUM_TAIL.search(user_msg)) or \
           bool(_LEAD_NUM_HEAD.search(user_msg))

_HOUMANITY_KEYWORDS = (
    "houmanity", "lead", "leads", "crm", "pipeline", "status",
    "clinic", "clinics", "office", "location",
    "update lead", "change lead", "edit lead",
    "rename clinic", "update clinic", "change clinic",
    "client id", "lead id", "lead#", "clinic id", "clinic#",
)
def _looks_like_houmanity_intent(user_msg: str) -> bool:
    if not user_msg:
        return False
    return any(k in user_msg.lower() for k in _HOUMANITY_KEYWORDS)

# -----------------------------
# Prompts
# -----------------------------
# Classic chat with OPTIONAL context (only used for Houmanity Qs)
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "{systemprompt}\n"
     "[Optional Context]: {data}\n"
     "Use this context only if the user is clearly asking about Houmanity (leads, clinics, or their account)."
    ),
    MessagesPlaceholder("history"),
    ("user", "{prompt}")
])

# -----------------------------
# Helpers
# -----------------------------
async def get_chat_history(chat_id: int) -> List[Any]:
    try:
        rows = await Message.filter(chat_id=chat_id).order_by("-created_at").limit(10)
        history: List[Any] = []
        for msg in reversed(rows):
            if msg.user_message:
                history.append(HumanMessage(content=msg.user_message))
            if msg.bot_response:
                history.append(AIMessage(content=msg.bot_response))
        return history
    except Exception as e:
        dlog("history.error", {"error": str(e)})
        return []

async def get_prompts() -> Dict[str, str]:
    try:
        sp = await SystemPrompts.filter().first()
        if sp and sp.system_prompt:
            return {"systemprompt": sp.system_prompt}
        # Default: app-scoped assistant
        return {"systemprompt": (
            "You are the Houmanity in-app assistant. "
            "Only assist with Houmanity-related questions (leads, clinics, account)."
        )}
    except Exception as e:
        dlog("prompts.error", {"error": str(e)})
        return {"systemprompt": (
            "You are the Houmanity in-app assistant. "
            "Only assist with Houmanity-related questions (leads, clinics, account)."
        )}

# -------------------------------------------------------
# Main entry used by chat_controller
# -------------------------------------------------------
async def generate_ai_response(user_message: str, chat_id: int, user_id: str) -> str:
    """
    Policy:
      - If NOT Houmanity intent → block (return APP_ONLY_HINT), unless ALLOW_GENERAL_QA=1.
      - If Houmanity + agent-like → run_with_agent.
      - Else (Houmanity non-agent) → classic prompt w/ optional context.
    """
    try:
        history = await get_chat_history(int(chat_id))
        response_data = await get_client_data(int(user_id))  # company/user context
        prompts = await get_prompts()

        dlog("chat.incoming", {
            "user_id": str(user_id),
            "chat_id": chat_id,
            "user_message": user_message,
            "systemprompt_head": f" {prompts['systemprompt'][:60]}",
            "has_data": bool(response_data),
        })

        houmanity_intent = _looks_like_houmanity_intent(user_message)
        agent_intent = _looks_like_agent_task(user_message)

        # 1) Out-of-scope: block or (optionally) allow
        if not houmanity_intent:
            if not ALLOW_GENERAL_QA:
                dlog("chat.reply.blocked", {"reason": "non-houmanity"})
                return APP_ONLY_HINT
            # If enabled later, you could route to a general prompt here.
            # For now policy default is to block.

        # 2) Agent path for lead/clinic operations
        if houmanity_intent and agent_intent:
            try:
                reply = await run_with_agent(
                    user_message=user_message, chat_id=int(chat_id), user_id=str(user_id)
                )
                dlog("chat.reply.agent", {"len": len(reply), "preview": reply[:140]})
                return reply or "OK"
            except Exception as e:
                dlog("orchestrator.error", {"error": str(e)})
                # fall through to classic handling

        # 3) Houmanity (non-agent) → classic with optional context
        data_for_model = response_data if response_data else "none"
        rendered = await prompt.ainvoke({
            "systemprompt": prompts["systemprompt"],
            "data": data_for_model,
            "history": history,
            "prompt": user_message
        })
        messages = rendered.to_messages()
        ai_msg = await model.ainvoke(messages)

        content = getattr(ai_msg, "content", None) or str(ai_msg) or "OK"
        dlog("chat.reply", {"len": len(content), "preview": content[:140]})
        return content

    except Exception as e:
        dlog("chat.error", {"error": str(e)})
        return "Sorry, I encountered an error. Please try again."
