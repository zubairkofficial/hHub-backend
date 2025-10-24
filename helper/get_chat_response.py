# helper/get_chat_response.py

import os
import json
from typing import Any, Dict, List
import re
# ⬇️ Add this so classic path also ensures registry is loaded (safe either way)
import agents.defs  # noqa: F401
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from models.message import Message
from models.system_prompt import SystemPrompts
from helper.get_data import get_client_data

# === if you still want direct tool-binding calls here, you can import tools
# from helper.tools.lead_tools import update_lead  # not needed in this file now

# use orchestrator only for lead/agent stuff
from agents.orchestrator import run_with_agent

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

# -----------------------------
# Classic chat chain (your old)
# -----------------------------
prompt = ChatPromptTemplate.from_messages([
    ("system", "{systemprompt}. Use this data to answer: {data}"),
    MessagesPlaceholder("history"),
    ("user", "{prompt}")
])

# Keep the non-tool model for normal replies
BASE_MODEL_NAME = "gpt-4.1"
model = init_chat_model(BASE_MODEL_NAME, model_provider="openai")


# -----------------------------
# Helpers
# -----------------------------
async def get_chat_history(chat_id: int) -> List[Any]:
    """Last ~10 messages as LC messages (Human/AI)."""
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
    """System prompt row from DB (fallback to default)."""
    try:
        sp = await SystemPrompts.filter().first()
        if sp and sp.system_prompt:
            return {"systemprompt": sp.system_prompt}
        return {"systemprompt": "You are an assistant of 'Houmanity' project"}
    except Exception as e:
        dlog("prompts.error", {"error": str(e)})
        return {"systemprompt": "You are an assistant of 'Houmanity' project"}

# very light intent check to decide if we should go to agents
# helper/get_chat_response.py

# very light intent check to decide if we should go to agents
_AGENT_KEYWORDS = (
    # Lead-related
    "lead", "leads", "update lead", "edit lead", "change lead",
    "lead id", "lead#", "lookup lead", "find lead", "search lead",
    "client lead", "client_leads", "crm",
    # Clinic-related
    "clinic", "clinics", "update clinic", "edit clinic", "change clinic",
    "rename clinic", "set clinic name", "clinic id", "clinic#", "office", "location",
    "update the my clinic", "change my clinic"," edit my clinic"," update my clinic",
    " my clinic"," clinic details"," clinic information"," clinic info"," clinic data",
    " get clinic"," fetch clinic"," show clinic"," view clinic",""
    # ✅ Service-related (ADD THESE)
    "service", "services", "update service","change service",
    # Appointment-related
    "appointment", "appointments", "book", "booking", "schedule", "reschedule","update appointment","change appointment",
    "appointment id", "appointment#", "lookup appointment", "find appointment", "search appointment","give me available slots",
    "client appointment", "client_appointments"," set appointment", " set appointment for "," schedule appointment for ",
    "get appointment","fetch appointment","show appointment","view appointment"," make appointment"," arrange appointment",
    "edit appointment"," update my appointment"," change my appointment"," reschedule my appointment",
    "cancel appointment", "cancel booking", "slot", "slots", "availability", "available slots","give me detail about appointments",
    " what appointments do I have"," when is my next appointment"," list my appointments"," upcoming appointments"," my appointments",
    " book an appointment for me"," schedule an appointment for me",
)


_LEAD_NUM_TAIL = re.compile(r"\blead\s*(?:id|#)?\s*\d+\b", re.IGNORECASE)   # lead 16
_LEAD_NUM_HEAD = re.compile(r"\b\d+\s*lead\b", re.IGNORECASE)               # 16 lead

def _looks_like_agent_task(user_msg: str) -> bool:
    if not user_msg:
        return False
    m = user_msg.lower()
    # keywords OR either numeric pattern
    return any(k in m for k in _AGENT_KEYWORDS) or \
           bool(_LEAD_NUM_TAIL.search(user_msg)) or \
           bool(_LEAD_NUM_HEAD.search(user_msg))



# -------------------------------------------------------
# Main entry used by chat_controller: generate_ai_response
# -------------------------------------------------------
async def generate_ai_response(user_message: str, chat_id: int, user_id: str) -> str:
    """
    1) If the message looks like a lead/CRM operation → route to the agent orchestrator
       (supports fetching leads by id/email/phone and updating via tools).
    2) Otherwise → use your classic chain with {data} injected so
       profile/company questions like 'what's my name/company' work again.
    """
    try:
        history = await get_chat_history(int(chat_id))
        response_data = await get_client_data(int(user_id))  # this contains company/user data
        prompts = await get_prompts()

        dlog("chat.incoming", {
            "user_id": str(user_id),
            "chat_id": chat_id,
            "user_message": user_message,
            "systemprompt_head": f" {prompts['systemprompt'][:60]}",
            "has_data": bool(response_data),
        })

        # 1) Agent path for lead/CRM type requests
        if _looks_like_agent_task(user_message):
            try:
                reply = await run_with_agent(user_message=user_message, chat_id=int(chat_id), user_id=str(user_id))
                # Orchestrator already enforces client_id on fetches and can update leads.
                dlog("chat.reply.agent", {"len": len(reply), "preview": reply[:140]})
                return reply or "OK"
            except Exception as e:
                dlog("orchestrator.error", {"error": str(e)})
                # If agents fail, fall back to classic chain (still respond)
                # (continue to classic path below)

        # 2) Classic path (context-injected chat): best for profile/company questions
        #    This is exactly your old behavior.
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
