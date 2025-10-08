# helper/ai_tools.py
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

LARAVEL_NOTIFY_URL   = os.getenv("LARAVEL_NOTIFY_URL")
LARAVEL_REMINDER_URL = os.getenv("LARAVEL_REMINDER_URL")
LARAVEL_NOTIFY_KEY   = os.getenv("LARAVEL_NOTIFY_KEY")  # optional bearer/sanctum

def _headers():
    h = {"Content-Type": "application/json"}
    if LARAVEL_NOTIFY_KEY:
        h["Authorization"] = f"Bearer {LARAVEL_NOTIFY_KEY}"
    return h

async def push_notification(user_id: str, title: str, body: str, data: dict | None = None) -> dict:
    """
    Ask Laravel to push an immediate Firebase notification to all devices of user_id.
    """
    payload = {"user_id": user_id, "title": title, "body": body, "data": data or {}}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(LARAVEL_NOTIFY_URL, json=payload, headers=_headers())
        return {"ok": r.is_success, "status": r.status_code, "body": r.text}

async def create_reminder(user_id: str, message: str, when_iso: str, meta: dict | None = None) -> dict:
    """
    Ask Laravel to create a reminder for cron to deliver later.
    when_iso: ISO8601 timestamp (UTC or with tz).
    """
    payload = {"user_id": user_id, "message": message, "when": when_iso, "meta": meta or {}}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(LARAVEL_REMINDER_URL, json=payload, headers=_headers())
        return {"ok": r.is_success, "status": r.status_code, "body": r.text}
