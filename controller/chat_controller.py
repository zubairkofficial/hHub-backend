# chat_controller.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from models.chat import ChatModel as Chat
from models.message import Message
from fastapi import HTTPException, status
from datetime import datetime
from helper.get_chat_response import generate_ai_response
from dotenv import load_dotenv
import os, json
from fastapi import HTTPException, status
import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime
from services.intent import parse_actions
from services.notify import push_notification, create_reminder
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator
from openai import AsyncOpenAI

load_dotenv()

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)


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

class StreamMessageCreate(BaseModel):
    user_id: str
    chat_id: int
    user_message: str

@router.post("/messages/stream")
async def stream_message(data: StreamMessageCreate):
    if not data.user_message.strip():
        raise HTTPException(400, "Empty prompt")

    chat = await Chat.get_or_none(id=data.chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    # --- Intent check BEFORE any OpenAI call ---
    msg_lower = data.user_message.strip().lower()
    houmanity_intent = any(k in msg_lower for k in (
        "houmanity","lead","leads","crm","pipeline","status",
        "clinic","clinics","office","location",
        "update lead","change lead","edit lead",
        "rename clinic","update clinic","change clinic",
        "client id","lead id","lead#","clinic id","clinic#",
    ))

    # Update title on first real message (do this before any early returns)
    if chat.title == "New Chat" and data.user_message.strip():
        t = " ".join(data.user_message.split()[:5])
        chat.title = (t[:47] + "...") if len(t) > 50 else t
        await chat.save()

    # If out-of-scope, stream a deterministic message and exit (no model call)
    if not houmanity_intent:
        msg_row = await Message.create(
            user_id=data.user_id, chat_id=data.chat_id,
            user_message=data.user_message, bot_response=""
        )

        async def blocked_event_gen() -> AsyncGenerator[str, None]:
            yield "event: start\ndata: {}\n\n"
            text = ("I can help with Houmanity tasks only — e.g., view or update leads and clinics, "
                    "or answer questions about your account and data in Houmanity.")
            yield f"data: {json.dumps({'token': text})}\n\n"
            msg_row.bot_response = text
            await msg_row.save()
            # keep chat timestamp fresh for ordering
            chat.updated_at = datetime.now()
            await chat.save()
            yield "event: done\ndata: {\"ok\":true}\n\n"

        return EventSourceResponse(
            blocked_event_gen(),
            ping=15,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",  # <- add this back
            },
        )

    async def event_gen() -> AsyncGenerator[str, None]:
        # create blank assistant row (so final save just updates it)
        msg_row = await Message.create(
            user_id=data.user_id, chat_id=data.chat_id,
            user_message=data.user_message, bot_response=""
        )
        yield "event: start\ndata: {}\n\n"
        chunks = []
        try:
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Houmanity in-app assistant. Only assist with Houmanity-related "
                            "questions (leads, clinics, account)."
                        ),
                    },
                    {"role": "user", "content": data.user_message},
                ],
                stream=True,
                temperature=0.2,
            )

            async for ev in stream:
                delta = ev.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    yield f"data: {json.dumps({'token': delta})}\n\n"

            assistant = "".join(chunks)
            msg_row.bot_response = assistant
            await msg_row.save()
            chat.updated_at = datetime.now()
            await chat.save()
            yield "event: done\ndata: {\"ok\":true}\n\n"

        except Exception as e:
            err = str(e)
            yield f"event: error\ndata: {json.dumps({'error': err})}\n\n"

    return EventSourceResponse(
        event_gen(),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@router.post("/chats", response_model=ChatResponse)
async def create_chat(chat_data: ChatCreate):
    """Create a new chat"""
    try:
        # Attempt to create the chat
        chat = await Chat.create(
            user_id=chat_data.user_id,
            title="New Chat"
        )
        
        # Attempt to create the initial welcome message
        await Message.create(
            user_id=chat_data.user_id,
            chat_id=chat.id,
            user_message="",
            bot_response="Hello! I'm your AI assistant. How can I help you today?"
        )
        
        # Return the response if everything goes fine
        return ChatResponse(
            id=chat.id,
            user_id=chat.user_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at
        )

    except Exception as e:
        # Log the error or print the details if needed
        print(f"Error occurred: {e}")
        
        # Raise an HTTPException with an appropriate status code and error message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the chat. Please try again later."
        )


@router.get("/chats/{user_id}", response_model=List[ChatResponse])
async def get_user_chats(user_id: str):
    """Get all chats for a user"""
    chats = await Chat.filter(user_id=user_id).order_by("-updated_at")
    return [ChatResponse(
        id=chat.id,
        user_id=chat.user_id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at
    ) for chat in chats]

@router.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(chat_id: int, user_id: str):
    """Get all messages for a specific chat"""
    messages = await Message.filter(chat_id=chat_id, user_id=user_id).order_by("created_at")
    return [MessageResponse(
        id=msg.id,
        user_id=msg.user_id,
        chat_id=msg.chat_id,
        user_message=msg.user_message,
        bot_response=msg.bot_response,
        created_at=msg.created_at
    ) for msg in messages]
  

# @router.post("/messages", response_model=MessageResponse)
# async def send_message(message_data: MessageCreate):
#     try:
#         ai_response = await generate_ai_response(message_data.user_message, message_data.chat_id, message_data.user_id)

#         message = await Message.create(
#             user_id=message_data.user_id,
#             chat_id=message_data.chat_id,
#             user_message=message_data.user_message,
#             bot_response=ai_response
#         )

#         chat = await Chat.get(id=message_data.chat_id)
#         if chat.title == "New Chat" and message_data.user_message.strip():
#             title_words = message_data.user_message.split()[:5]
#             new_title = " ".join(title_words)
#             if len(new_title) > 50:
#                 new_title = new_title[:47] + "..."
#             chat.title = new_title
#         chat.updated_at = datetime.now()
#         await chat.save()

#         # 🔥 NEW: parse & execute actions
#         actions = parse_actions(message_data.user_message)
#         for a in actions:
#             if a.name == "notify":
#                 await push_notification(
#                     user_id=message_data.user_id,
#                     title=a.params.get("title", "Notification"),
#                     body=a.params.get("body", ""),
#                     data={"chat_id": message_data.chat_id, "tag": a.params.get("tag", "general")}
#                 )
#             elif a.name == "create_reminder":
#                 await create_reminder(
#                     user_id=message_data.user_id,
#                     message=a.params.get("message", ""),
#                     due_at_utc=a.params.get("when_utc"),
#                     meta={"chat_id": message_data.chat_id}
#                 )
#                 # Optional immediate ack to the user (extra message):
#                 # await Message.create(...)

#         return MessageResponse(
#             id=message.id,
#             user_id=message.user_id,
#             chat_id=message.chat_id,
#             user_message=message.user_message,
#             bot_response=message.bot_response,
#             created_at=message.created_at
#         )
#     except Exception as e:
#         print(f"Error occurred: {e}")
#         raise HTTPException(status_code=500, detail="An error occurred while sending the message. Please try again later.")
@router.post("/messages", response_model=MessageResponse)
async def send_message(message_data: MessageCreate):
    """Send a message and get AI response"""
    try:
        # Generate AI response (replace with your AI service)
        ai_response = await generate_ai_response(message_data.user_message,message_data.chat_id,message_data.user_id)
        
        # Save message to database
        message = await Message.create(
            user_id=message_data.user_id,
            chat_id=message_data.chat_id,
            user_message=message_data.user_message,
            bot_response=ai_response
        )
        
        # Update chat title if it's the first real message
        chat = await Chat.get(id=message_data.chat_id)
        if chat.title == "New Chat" and message_data.user_message.strip():
            # Use first few words of the message as title
            title_words = message_data.user_message.split()[:5]
            new_title = " ".join(title_words)
            if len(new_title) > 50:
                new_title = new_title[:47] + "..."
            chat.title = new_title
            await chat.save()     
        
        # Update chat's updated_at timestamp
        chat.updated_at = datetime.now()
        await chat.save()
        
        return MessageResponse(
            id=message.id,
            user_id=message.user_id,
            chat_id=message.chat_id,
            user_message=message.user_message,
            bot_response=message.bot_response,
            created_at=message.created_at
        )
    
    except Exception as e:
        # Log the error or print the details if needed
        print(f"Error occurred: {e}")
        
        # Raise an HTTPException with an appropriate status code and error message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending the message. Please try again later."
        )

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int):
    """Delete a chat and all its associated messages."""
    try:
        # Delete all messages associated with the chat
        await Message.filter(chat_id=chat_id).delete()

        # Delete the chat itself
        chat = await Chat.get(id=chat_id)
        if chat:
            await chat.delete()
            return {"message": "Chat and associated messages deleted successfully."}
        else:
            raise HTTPException(status_code=404, detail="Chat not found")

    except Exception as e:  
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.delete("/message/{message_id}")
async def delete_message(message_id: int):
    """Delete a messages."""
    try:
       
        message = await Message.get(id=message_id)
        if message:
            await message.delete()
            return {"message": "Message deleted successfully."}
        else:
            raise HTTPException(status_code=404, detail="Message not found")

    except Exception as e:  
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.delete("/chats/user/{user_id}")
async def delete_all_user_chats(user_id: str):
    """Delete ALL chats and messages for a user."""
    try:
        # find all chat ids for this user
        chats = await Chat.filter(user_id=user_id).all()
        chat_ids = [c.id for c in chats]

        # delete all messages for these chats
        if chat_ids:
            await Message.filter(chat_id__in=chat_ids).delete()

        # delete the chats
        await Chat.filter(user_id=user_id).delete()

        return {"message": f"Deleted {len(chat_ids)} chats for user {user_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
