# E:\Shoaib\Projects\hHub\hHub-backend\controller\chat_widget_controller.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List
from datetime import datetime
from dotenv import load_dotenv

from helper.get_chat_widget_response import generate_ai_response
from helper.laravel_client import (
    create_chat_widget,
    list_chat_widgets,
    list_messages_widget,
    create_message_widget,
    delete_chat_widget,
    delete_all_chats_for_user,
    delete_message_widget,
)

load_dotenv()
router = APIRouter()

# ---------------- Pydantic contracts ----------------
class ChatCreate(BaseModel):
    user_id: str

class MessageCreate(BaseModel):
    user_id: str
    chat_id: int
    user_message: str

class ChatResponse(BaseModel):
    id: int
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime

class MessageResponse(BaseModel):
    id: int
    user_id: str
    chat_id: int
    user_message: str
    bot_response: str
    created_at: datetime

class ErrorResponse(BaseModel):
    detail: str
# ----------------------------------------------------


def _parse_dt(x):
    """
    Robustly parse Laravel timestamps that may be like:
    - '2025-10-06T10:29:55.000000Z'
    - '2025-10-06 10:29:55'
    """
    if not x:
        return datetime.utcnow()
    s = str(x)
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # fallback: trim microseconds/space
        try:
            s = s.replace(" ", "T")
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.utcnow()


@router.post("/chats", response_model=ChatResponse)
async def create_chat(chat_data: ChatCreate):
    """Create a new chat (persisted in Laravel)"""
    try:
        res = await create_chat_widget(chat_data.user_id, title="New Chat")
        return ChatResponse(
            id=res["id"],
            user_id=res["user_id"],
            title=res.get("title", "New Chat"),
            created_at=_parse_dt(res.get("created_at")),
            updated_at=_parse_dt(res.get("updated_at")),
        )
    except Exception as e:
        print(f"[create_chat] error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the chat. Please try again later."
        )


@router.get("/chats/{user_id}", response_model=List[ChatResponse])
async def get_user_chats(user_id: str):
    """Get all chats for a user (from Laravel)"""
    try:
        rows = await list_chat_widgets(user_id)
        out: List[ChatResponse] = []
        for c in rows:
            out.append(ChatResponse(
                id=c["id"],
                user_id=c["user_id"],
                title=c.get("title", "New Chat"),
                created_at=_parse_dt(c.get("created_at")),
                updated_at=_parse_dt(c.get("updated_at")),
            ))
        return out
    except Exception as e:
        print(f"[get_user_chats] error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch chats.")


@router.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(chat_id: int, user_id: str):
    """Get all messages for a specific chat (from Laravel)"""
    try:
        rows = await list_messages_widget(chat_id, user_id=user_id)
        out: List[MessageResponse] = []
        for m in rows:
            out.append(MessageResponse(
                id=m["id"],
                user_id=m["user_id"],
                chat_id=m["chat_id"],
                user_message=m.get("user_message", "") or "",
                bot_response=m.get("bot_response", "") or "",
                created_at=_parse_dt(m.get("created_at")),
            ))
        return out
    except Exception as e:
        print(f"[get_chat_messages] error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch messages.")


@router.post("/messages", response_model=MessageResponse)
async def send_message(message_data: MessageCreate):
    """Send a message, get AI response, and persist both to Laravel"""
    try:
        ai_response = await generate_ai_response(
            user_message=message_data.user_message,
            chat_id=message_data.chat_id,
            user_id=message_data.user_id
        )

        saved = await create_message_widget(
            user_id=message_data.user_id,
            chat_id=message_data.chat_id,
            user_message=message_data.user_message,
            bot_response=ai_response
        )

        return MessageResponse(
            id=saved["id"],
            user_id=saved["user_id"],
            chat_id=saved["chat_id"],
            user_message=saved.get("user_message", "") or "",
            bot_response=saved.get("bot_response", "") or "",
            created_at=_parse_dt(saved.get("created_at")),
        )

    except Exception as e:
        print(f"[send_message] error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending the message. Please try again later."
        )


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int):
    """Delete a chat and its messages (in Laravel)"""
    try:
        res = await delete_chat_widget(chat_id)
        return res
    except Exception as e:
        print(f"[delete_chat] error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@router.delete("/message/{message_id}")
async def delete_message(message_id: int):
    """Delete a single message (in Laravel)"""
    try:
        res = await delete_message_widget(message_id)
        return res
    except Exception as e:
        print(f"[delete_message] error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# Optional: clear-all to match your Livewire "clearAllChats"
@router.delete("/chats/user/{user_id}")
async def delete_user_chats(user_id: str):
    try:
        res = await delete_all_chats_for_user(user_id)
        return res
    except Exception as e:
        print(f"[delete_user_chats] error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
