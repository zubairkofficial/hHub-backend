# E:\Shoaib\Projects\hHub\hHub-backend\helper\laravel_client.py
import os
import httpx
from typing import Any, Dict, List, Optional

LARAVEL_API_URL = os.getenv("API_URL", "http://127.0.0.1:8080").rstrip("/")
WIDGET_BASE = f"{LARAVEL_API_URL}/api/widget"

API_HEADERS = {
    # Add auth if you secure the routes:
    # "Authorization": f"Bearer {os.getenv('LARAVEL_TOKEN','')}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

async def create_chat_widget(user_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"user_id": user_id}
    if title:
        payload["title"] = title
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{WIDGET_BASE}/chats", headers=API_HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def list_chat_widgets(user_id: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{WIDGET_BASE}/chats/{user_id}", headers=API_HEADERS)
        r.raise_for_status()
        return r.json()

async def delete_chat_widget(chat_id: int) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.delete(f"{WIDGET_BASE}/chats/{chat_id}", headers=API_HEADERS)
        r.raise_for_status()
        return r.json()

async def delete_all_chats_for_user(user_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.delete(f"{WIDGET_BASE}/chats/user/{user_id}", headers=API_HEADERS)
        r.raise_for_status()
        return r.json()

async def list_messages_widget(chat_id: int, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if user_id:
        params["user_id"] = user_id
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{WIDGET_BASE}/chats/{chat_id}/messages", headers=API_HEADERS, params=params)
        r.raise_for_status()
        return r.json()

async def create_message_widget(user_id: str, chat_id: int, user_message: Optional[str], bot_response: Optional[str]) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "user_message": user_message,
        "bot_response": bot_response,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{WIDGET_BASE}/messages", headers=API_HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def delete_message_widget(message_id: int) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.delete(f"{WIDGET_BASE}/message/{message_id}", headers=API_HEADERS)
        r.raise_for_status()
        return r.json()
