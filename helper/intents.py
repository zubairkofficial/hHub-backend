# helper/intents.py
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict

class Intent(BaseModel):
    action: Literal[
        "NONE",              # normal answer only
        "CREATE_REMINDER",   # schedule something for later
        "PUSH_NOTIFICATION"  # send immediate notification
    ] = "NONE"

    # Common
    title: Optional[str] = None
    body: Optional[str] = None

    # Reminder-specific
    when_iso: Optional[str] = None  # ISO8601, e.g. 2025-10-10T09:30:00Z

    # Optional extra payload (will be stringified by Laravel pusher)
    data: Optional[Dict[str, str]] = Field(default=None)

INTENT_SYSTEM = (
    "You are an intent classifier for an AI assistant. "
    "Read the user's message and determine if the AI should perform an ACTION.\n\n"
    "Actions:\n"
    "- NONE: No side-effect. Just answer normally.\n"
    "- CREATE_REMINDER: The user asked to remind them later. Fill when_iso (ISO8601).\n"
    "- PUSH_NOTIFICATION: The user wants an immediate actionable notification "
    "(e.g., 'Notify me now', 'Alert me about new leads', 'Send confirmations now').\n\n"
    "If the user mentions counts like 'You have two new leads—follow up', set action=PUSH_NOTIFICATION and "
    "create a concise title/body. Use data to include semantic keys: e.g., {'type':'leads','count':'2'}.\n"
    "If they say 'remind me tomorrow at 9am to call leads', set action=CREATE_REMINDER with when_iso parsed.\n"
    "Be strict: if time is ambiguous, choose NONE.\n"
)
