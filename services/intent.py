# backend/services/intent.py
from dataclasses import dataclass
from typing import List, Dict, Any
import re
from datetime import datetime, timedelta
import os
import json

AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

@dataclass
class Action:
    name: str
    params: Dict[str, Any]

def parse_actions(text: str) -> List[Action]:
    """Return actions ONLY for explicit slash-commands."""
    t = (text or "").strip()
    actions: List[Action] = []

    # /notify <message>
    m = re.match(r"^/notify\s+(.+)$", t, re.I)
    if m:
        actions.append(Action("notify", {
            "title": "Notification",
            "body": m.group(1).strip(),
            "tag": "custom"
        }))

    # /remind in 2h <message>  OR  /remind in 30m <message>
    m = re.match(r"^/remind\s+in\s+(\d+)([hm])\s+(.+)$", t, re.I)
    if m:
        qty = int(m.group(1))
        unit = m.group(2).lower()
        msg  = m.group(3).strip()
        delta = timedelta(hours=qty) if unit == "h" else timedelta(minutes=qty)
        when_utc = (datetime.utcnow() + delta).isoformat()
        actions.append(Action("create_reminder", {"when_utc": when_utc, "message": msg}))

    dlog("intent.actions", {"text": t, "actions": [a.name for a in actions]})
    return actions
