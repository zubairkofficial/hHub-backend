# agents/tools/helpers/natural_language.py
from dateutil import parser as dtparse
from datetime import datetime, timedelta  # Fix: import datetime, not date
import calendar
import re
from typing import Optional

# Default appointment duration (minutes)
DEFAULT_APPT_MINUTES = 30

# Map weekday names → index (Monday=0)
WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}


# ------------------ Internal helpers ------------------
def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _parse_rel_date(text: str) -> Optional[datetime]:
    """
    Detect relative expressions like 'today', 'tomorrow', 'next Monday', etc.
    """
    t = (text or "").lower()
    today = datetime.today()  # This should work now with datetime import
    if "today" in t:
        return today
    if "tomorrow" in t:
        return today + timedelta(days=1)

    # weekdays: e.g. "next monday" or "on friday"
    for wd, idx in WEEKDAYS.items():
        if wd in t:
            days_ahead = (idx - today.weekday()) % 7
            if "next" in t and days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
    return None


# ------------------ Public helpers ------------------
def parse_date_any(text: str) -> Optional[str]:
    """
    Public: Parse any natural-language date into YYYY-MM-DD.
    Handles 'today', 'tomorrow', weekdays, or explicit formats like 10/23/2025.
    """
    text = _normalize_whitespace(text)
    
    # First, try to extract explicit YYYY-MM-DD patterns
    ymd_pattern = r'\b(\d{4}-\d{2}-\d{2})\b'
    match = re.search(ymd_pattern, text)
    if match:
        date_str = match.group(1)
        try:
            # Validate it's a real date
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            pass  # Invalid date like 2025-20-24

    # Relative tokens next
    rd = _parse_rel_date(text)
    if rd:
        return rd.strftime("%Y-%m-%d")

    # Explicit formats with dateutil
    try:
        d = dtparse.parse(text, fuzzy=True, default=datetime.today())
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_time_any(text: str) -> Optional[str]:
    """
    Public: Parse any natural-language time into HH:MM:SS.
    Handles '2pm', '2 30 pm', '14:30', '2:30pm', etc.
    """
    cleaned = _normalize_whitespace(text)
    # Insert a colon if "2 30 pm"
    m = re.search(r"\b(\d{1,2})\s+(\d{2})\s*(am|pm)?\b", cleaned, re.I)
    if m and ":" not in cleaned:
        hh, mm, ap = m.groups()
        cleaned = cleaned.replace(m.group(0), f"{hh}:{mm}{(' '+ap) if ap else ''}")

    try:
        t = dtparse.parse(cleaned, fuzzy=True, default=datetime(2000, 1, 1, 9, 0, 0))
        return t.strftime("%H:%M:%S")
    except Exception:
        return None


def find_name_for_reschedule(msg: str) -> Optional[str]:
    """
    Public: Extract probable name from phrases like
    'reschedule the appointment of <NAME> to ...'
    """
    m = re.search(r"(?:appointment\s+of|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})", msg, re.I)
    if m:
        return _normalize_whitespace(m.group(1))

    # fallback: take everything before 'to' if it looks like a name phrase
    m2 = re.search(r"appointment\s+of\s+(.+?)\s+to\b", msg, re.I)
    if m2:
        candidate = _normalize_whitespace(m2.group(1))
        if re.match(r"^[a-z\s\-']{2,}$", candidate, re.I):
            return candidate
    return None


def duration_to_end(from_time: str, minutes: int = DEFAULT_APPT_MINUTES) -> str:
    """
    Given a start time HH:MM:SS, returns end time after the specified minutes.
    """
    hh, mm, ss = from_time.split(":")
    dt0 = datetime(2000, 1, 1, int(hh), int(mm), int(ss))
    dt1 = dt0 + timedelta(minutes=minutes)
    return dt1.strftime("%H:%M:%S")


# ------------------ Explicit exports ------------------
__all__ = [
    "parse_date_any",
    "parse_time_any",
    "find_name_for_reschedule",
    "duration_to_end",
    "DEFAULT_APPT_MINUTES",
]