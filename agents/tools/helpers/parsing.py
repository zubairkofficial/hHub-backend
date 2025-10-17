import re
from typing import Optional, Dict

# ---------- Generic patterns ----------
LEAD_ID_TAIL   = re.compile(r"\b(?:lead)\s*(?:id|#)?\s*(\d{1,10})\b", re.IGNORECASE)
LEAD_ID_HEAD   = re.compile(r"\b(\d{1,10})\s*(?:lead)\b", re.IGNORECASE)

CLINIC_ID_TAIL = re.compile(r"\b(?:clinic)\s*(?:id|#)?\s*(\d{1,10})\b", re.IGNORECASE)
CLINIC_ID_HEAD = re.compile(r"\b(\d{1,10})\s*(?:clinic)\b", re.IGNORECASE)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{6,}\d")

# ---------- Clinic update command patterns ----------
# e.g. "update my clinic name Badshah"
UPDATE_CLINIC_NAME_FREEFORM = re.compile(
    r"(?:update|change|edit|set)\b.*?\bclinic\s+name\b\s*[:\-]?\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# e.g. "update clinic 3 name to X"
UPDATE_CLINIC_SIMPLE = re.compile(
    r"(?:update|change|edit|set)\s+(?:the\s+)?clinic\s*(?:id|#)?\s*(\d{1,10})\s+"
    r"(name|address|address2|country_id|state_id|city_id|zip_code|is_active|review_url|google_review_url|tw_content_sid_appt|tw_content_sid_review|tw_content_sid_nurture)"
    r"(?:\s*(?:to|=|as|with)\s*|\s+to\s+)\s*['\"]?([^'\"\n\r]+?)['\"]?\s*$",
    re.IGNORECASE,
)

# e.g. "update the clinic name to X" / "set name of clinic = X"
UPDATE_CLINIC_NAME_TO = re.compile(
    r"(?:update|change|edit|set)\s+(?:the\s+)?(?:name\s+of\s+clinic|clinic\s+name)\s*(?:to|=)\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
UPDATE_CLINIC_NAME_POSSESSIVE_TO = re.compile(
    r"(?:update|change|edit|set)\s+(?:the\s+)?(?:my\s+|our\s+)?clinic\s+name\s*(?:to|=)\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
# e.g. "rename clinic from A to B"
UPDATE_CLINIC_RENAME_FROM_TO = re.compile(
    r"(?:rename|change|update|edit)\s+(?:the\s+)?clinic.*?\bfrom\b\s*['\"]?(.+?)['\"]?\s*\bto\b\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# e.g. "Current Name: A   New Name: B"
UPDATE_CLINIC_CURRENT_NEW = re.compile(
    r"current\s*name\s*:\s*['\"]?(.+?)['\"]?\s*(?:[,;\n\r ]+)?new\s*name\s*:\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# e.g. "update the name of clinic to X"
UPDATE_CLINIC_NAME_OF_TO = re.compile(
    r"(?:update|change|edit|set)\s+(?:the\s+)?name\s+of\s+(?:the\s+)?(?:my\s+|our\s+)?clinic\s*(?:to|=)\s*['\"]?(.+?)['\"]?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# ---------- Lead update command patterns ----------
# Natural commands like:
#  - "update lead 42 status to Hot"
#  - "set phone to 03001234567 for lead 42"
#  - "change email to a@b.com for lead 77"
UPDATE_LEAD_STATUS_TO = re.compile(
    r"\b(?:update|set|change)\s+(?:lead\s+)?(?:status|stage)\s*(?:to|=|as)\s+([-\w\s/]+)\b", re.IGNORECASE)
UPDATE_LEAD_PHONE_TO = re.compile(
    r"\b(?:update|set|change)\s+(?:lead\s+)?(?:phone|contact|number)\s*(?:to|=|as)\s*([\d+\-\s()]+)", re.IGNORECASE)
UPDATE_LEAD_EMAIL_TO = re.compile(
    r"\b(?:update|set|change)\s+(?:lead\s+)?email\s*(?:to|=|as)\s*([\w.\-+]+@[\w.\-]+\.\w+)", re.IGNORECASE)
UPDATE_LEAD_NAME_TO = re.compile(
    r"\b(?:update|set|change)\s+(?:lead\s+)?name\s*(?:to|=|as)\s*([^\n,]+)", re.IGNORECASE)

def parse_lead_update_fields(msg: str) -> Dict[str, str]:
    """Extracts intended lead fields from a freeform message."""
    m: Dict[str, str] = {}
    if (g := UPDATE_LEAD_STATUS_TO.search(msg)): m["status"] = g.group(1).strip()
    if (g := UPDATE_LEAD_PHONE_TO.search(msg)):  m["contact_number"] = re.sub(r"\s+", "", g.group(1))
    if (g := UPDATE_LEAD_EMAIL_TO.search(msg)):  m["email"] = g.group(1).strip()
    if (g := UPDATE_LEAD_NAME_TO.search(msg)):
        full = g.group(1).strip()
        # naive split into first/last if space present
        parts = [p for p in full.split() if p]
        if len(parts) >= 2:
            m["first_name"], m["last_name"] = parts[0], " ".join(parts[1:])
        else:
            m["first_name"] = full
    return m

# ---------- Helpers ----------
def parse_lead_id(text: str) -> Optional[int]:
    if not text:
        return None
    m = LEAD_ID_TAIL.search(text) or LEAD_ID_HEAD.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def parse_clinic_id(text: str) -> Optional[int]:
    if not text:
        return None
    m = CLINIC_ID_TAIL.search(text) or CLINIC_ID_HEAD.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

__all__ = [
    # patterns
    "LEAD_ID_TAIL", "LEAD_ID_HEAD",
    "CLINIC_ID_TAIL", "CLINIC_ID_HEAD",
    "EMAIL_RE", "PHONE_RE",
    "UPDATE_CLINIC_NAME_FREEFORM",
    "UPDATE_CLINIC_SIMPLE",
    "UPDATE_CLINIC_NAME_TO",
    "UPDATE_CLINIC_RENAME_FROM_TO",
    "UPDATE_CLINIC_CURRENT_NEW",
    "UPDATE_CLINIC_NAME_POSSESSIVE_TO",
    "UPDATE_CLINIC_NAME_OF_TO",
    # lead update
    "UPDATE_LEAD_STATUS_TO", "UPDATE_LEAD_PHONE_TO", "UPDATE_LEAD_EMAIL_TO", "UPDATE_LEAD_NAME_TO",
    "parse_lead_update_fields",
    # helpers
    "parse_lead_id", "parse_clinic_id",
]
