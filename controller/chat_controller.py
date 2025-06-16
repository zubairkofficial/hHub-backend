from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import httpx
from datetime import datetime
from models.chat import ChatModel as Chat
from models.message import Message
from fastapi import HTTPException, status
from datetime import datetime
from helper.get_chat_response import generate_ai_response
from dotenv import load_dotenv
import os
from fastapi import HTTPException, status
import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime
load_dotenv()

router= APIRouter()


LARAVEL_API_URL  = os.getenv("API_URL")

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



  