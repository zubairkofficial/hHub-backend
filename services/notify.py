# backend/services/notify.py
import os
import httpx
from typing import Dict, Any

LARAVEL_NOTIFY_URL   = os.getenv("LARAVEL_NOTIFY_URL", "http://127.0.0.1:8080/api/notify/push")
LARAVEL_REMINDER_URL = os.getenv("LARAVEL_REMINDER_URL", "http://127.0.0.1:8080/api/reminders")
LARAVEL_BEARER       = os.getenv("LARAVEL_NOTIFY_KEY", "")

def _headers():
    h = {"Accept": "application/json"}
    if LARAVEL_BEARER:
        h["Authorization"] = f"Bearer {LARAVEL_BEARER}"
    return h

async def push_notification(user_id: str, title: str, body: str, data: Dict[str, Any] | None = None) -> bool:
    payload = {"user_id": user_id, "title": title, "body": body, "data": data or {}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(LARAVEL_NOTIFY_URL, json=payload, headers=_headers())
        return r.status_code in (200, 201)

async def create_reminder(user_id: str, message: str, due_at_utc: str, meta: Dict[str, Any] | None = None) -> bool:
    payload = {"user_id": user_id, "message": message, "due_at_utc": due_at_utc, "meta": meta or {}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(LARAVEL_REMINDER_URL, json=payload, headers=_headers())
        return r.status_code in (200, 201)
