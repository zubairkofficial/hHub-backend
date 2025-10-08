# helper/get_chat_response.py

import os
import json
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from models.message import Message
from models.system_prompt import SystemPrompts
from helper.get_data import get_client_data

from helper.tools.lead_tools import update_lead  # tool

load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

prompt = ChatPromptTemplate.from_messages([
    ("system", "{systemprompt}. Use this data to answer: {data}"),
    MessagesPlaceholder("history"),
    ("user", "{prompt}")
])

TOOL_ENABLED_MODEL_NAME = "gpt-4o-mini"
TOOLS = [update_lead]
tool_model = init_chat_model(TOOL_ENABLED_MODEL_NAME, model_provider="openai").bind_tools(TOOLS)

async def get_chat_history(chat_id: int) -> List[Any]:
    try:
        rows = await Message.filter(chat_id=chat_id).order_by('-created_at').limit(10)
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
        return {"systemprompt": "You are an assistant of 'Houmanity' project"}
    except Exception as e:
        dlog("prompts.error", {"error": str(e)})
        return {"systemprompt": "You are an assistant of 'Houmanity' project"}

async def generate_ai_response(user_message: str, chat_id: str, user_id: str) -> str:
    """Main entry: build context, let the LLM reply, and execute tool calls when requested."""
    dlog("chat.incoming", {"user_message": user_message, "chat_id": chat_id, "user_id": user_id})

    history = await get_chat_history(int(chat_id))
    response_data = await get_client_data(int(user_id))
    prompts = await get_prompts()

    # Build chat messages
    msg_bundle = await prompt.ainvoke({
        "systemprompt": prompts["systemprompt"],
        "data": response_data or "none",
        "history": history,
        "prompt": user_message,
    })
    messages = msg_bundle.to_messages()

    # For visibility, show the final rendered prompt bits
    try:
        sys_msg = msg_bundle.messages[0].content if msg_bundle.messages else "(none)"
    except Exception:
        sys_msg = "(unavailable)"
    dlog("prompt.rendered", {"system": sys_msg, "user": user_message})

    # First pass — may include tool calls
    ai_msg = await tool_model.ainvoke(messages)

    dlog("ai.first", {
        "type": type(ai_msg).__name__,
        "content": getattr(ai_msg, "content", None),
        "tool_calls": getattr(ai_msg, "tool_calls", None)
    })

    # Did the model call any tools?
    if getattr(ai_msg, "tool_calls", None):
        tool_name_to_fn = {t.name: t for t in TOOLS}
        followups: List[Any] = [ai_msg]

        for tc in ai_msg.tool_calls:
            name = tc.get("name")
            args = tc.get("args", {})

            dlog("tool.invocation", {"tool": name, "args": args})
            tool_fn = tool_name_to_fn.get(name)

            if tool_fn is None:
                tool_result = f"{name}:FAIL:Tool not registered"
                dlog("tool.error", {"tool": name, "error": "not registered"})
            else:
                try:
                    tool_result = await tool_fn.ainvoke(args)  # async tool execution
                except Exception as e:
                    tool_result = f"{name}:FAIL:{str(e)}"
                    dlog("tool.exception", {"tool": name, "error": str(e)})

            dlog("tool.result", {"tool": name, "result": tool_result})
            followups.append(ToolMessage(content=tool_result, tool_call_id=tc["id"]))

        final = await tool_model.ainvoke(messages + followups)
        dlog("ai.final", {
            "type": type(final).__name__,
            "content": getattr(final, "content", None)
        })
        return final.content

    # No tool calls → plain response
    dlog("ai.plain", {"content": getattr(ai_msg, "content", None)})
    return ai_msg.content
