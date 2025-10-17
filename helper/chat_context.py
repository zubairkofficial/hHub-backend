# helper/chat_context.py
from typing import Any, List
from langchain_core.messages import HumanMessage, AIMessage
from models.message import Message

__all__ = ["get_chat_history"]

async def get_chat_history(chat_id: int) -> List[Any]:
    """
    Return last ~10 messages as LangChain Human/AI messages.
    Shared by orchestrator and get_chat_response to avoid circular imports.
    """
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
        # Keep log minimal here to avoid extra deps
        print(f"[AI-DBG] history.error :: {e}")
        return []
