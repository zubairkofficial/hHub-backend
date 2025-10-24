# agents/fastpaths/appointments.py

import json
import re
from datetime import date
from typing import Optional, Dict, List, Tuple

from agents.tools.helpers.logging import ai_dbg
from agents.tools.helpers.natural_language import (
    parse_time_any,
    parse_date_any,
    find_name_for_reschedule,
    duration_to_end,
)

# Tools we call in this fast-path
from agents.tools.http_clinics import clinic_search_http
from agents.tools.appointment_tools import appointment_slots, appointment_update
from agents.tools.lead_tools import lead_search  # name-based lookup

# -------- Intent + extractors

RE_SLOTS   = re.compile(r"\b(slots?|availability|available\s+times?)\b", re.I)
RE_CREATE  = re.compile(r"\b(book|create|make)\s+(?:an?\s+)?appointment\b", re.I)
RE_UPDATE  = re.compile(r"\b(update|reschedule|change|move)\s+(?:the\s+)?appointment\b", re.I)
RE_CANCEL  = re.compile(r"\b(cancel)\s+(?:the\s+)?appointment\b", re.I)

# Accept "appointment id 123" / "lead id 123" / "appointment #123"
RE_ID = re.compile(r"\b(?:appointment|lead)\s*(?:id|#)?\s*(\d{1,10})\b", re.I)


def parse_appt_intent(msg: str) -> str:
    m = msg or ""
    if RE_CANCEL.search(m): return "cancel"
    if RE_UPDATE.search(m): return "update"
    if RE_CREATE.search(m): return "create"
    if RE_SLOTS.search(m):  return "slots"
    return "none"


def extract_id(msg: str) -> Optional[int]:
    m = RE_ID.search(msg or "")
    return int(m.group(1)) if m else None


# -------- internal helpers

def _flatten_free_slots(slots_payload: Dict[str, any]) -> List[Tuple[str, str]]:
    """
    Return a flat list of (from_time, to_time) for all FREE slots in morning/afternoon/evening.
    """
    flat: List[Tuple[str, str]] = []
    if not isinstance(slots_payload, dict):
        return flat
    slots = slots_payload.get("slots") or {}
    for bucket in ("morning", "afternoon", "evening"):
        for s in slots.get(bucket, []):
            if not s.get("has_booking"):
                ft = s.get("from_time")
                tt = s.get("to_time")
                if ft and tt:
                    flat.append((ft, tt))
    return flat


def _hms_to_seconds(hms: str) -> int:
    h, m, s = [int(x) for x in hms.split(":")]
    return h * 3600 + m * 60 + s


def _closest_n(to_time_hms: str, free_pairs: List[Tuple[str, str]], n: int = 3) -> List[Tuple[str, str]]:
    return sorted(free_pairs, key=lambda pair: abs(_hms_sec(pair[0]) - _hms_sec(to_time_hms)))[:n]


def _hms_sec(hms: str) -> int:
    h, m, s = [int(x) for x in hms.split(":")]
    return h * 3600 + m * 60 + s


# -------- main fast-path: RESCHEDULE / CHANGE APPOINTMENT

async def fastpath_handle(msg: str, client_id_val: Optional[int]) -> Optional[str]:
    """
    Handle appointment-related fast-paths.
    Currently implements RESCHEDULE (update) flow with availability check.
    Returns a user-facing string if handled, else None to let the orchestrator continue.
    """
    if not msg:
        return None

    intent = parse_appt_intent(msg)
    if intent != "update":
        # Only reschedule handled here; other intents fall back to orchestrator/agents.
        return None

    if client_id_val is None:
        return "I can’t change appointments because this session isn’t linked to a client. Please sign in."

    # 1) Parse target time/date/name (natural language)
    who_name  = find_name_for_reschedule(msg)         # e.g., "Linda Monroe"
    new_time  = parse_time_any(msg)                   # -> "14:30:00"
    new_date  = parse_date_any(msg) or date.today().isoformat()  # -> "YYYY-MM-DD"

    if not new_time:
        return "I couldn’t understand the time you want. Please say something like “2:30 pm today” or “14:00 tomorrow”."

    from_time = new_time
    to_time   = duration_to_end(from_time)            # default window length (e.g., 30 minutes)

    # 2) Resolve clinic — auto-pick if tenant has exactly one active clinic
    clinic_id_fp: Optional[int] = None
    try:
        args = {"client_id": int(client_id_val), "is_active": 1, "limit": 5}
        ai_dbg("clinic.search.request", {"url": "http://127.0.0.1:8080/api/clinics", "params": args})
        raw = await clinic_search_http.ainvoke(args)
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows = (data or {}).get("rows") or []
        if len(rows) == 1:
            clinic_id_fp = int(rows[0]["id"])
    except Exception as e:
        ai_dbg("clinic.autopick.error", repr(e))

    if not clinic_id_fp:
        return "I couldn’t determine which clinic to use. Please include the clinic id (e.g., “reschedule for clinic 1”)."

    # 3) Slot availability for requested date/clinic
    try:
        req = {"client_id": int(client_id_val), "clinic_id": int(clinic_id_fp), "date": new_date}
        raw = await appointment_slots.ainvoke(req)
        slots_payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Slots lookup failed: {e}"}, ensure_ascii=False)

    if not (isinstance(slots_payload, dict) and slots_payload.get("ok")):
        return json.dumps({"ok": False, "error": "Could not retrieve slots"}, ensure_ascii=False)

    # Does exact slot exist and is it free?
    def _slot_present_and_free(ft: str, tt: str) -> bool:
        for bucket in ("morning", "afternoon", "evening"):
            for s in (slots_payload.get("slots") or {}).get(bucket, []):
                if s.get("from_time") == ft and s.get("to_time") == tt:
                    return not s.get("has_booking")
        return False

    slot_ok = _slot_present_and_free(from_time, to_time)
    if not slot_ok:
        # Suggest the 3 nearest free options
        free_list = _flatten_free_slots(slots_payload)
        if not free_list:
            return f"That time isn’t available on {new_date} and there are no free alternatives that day."
        free_list.sort(key=lambda pair: abs(_hms_sec(pair[0]) - _hms_sec(from_time)))
        suggestions = "\n".join([f"- {a}–{b}" for a, b in free_list[:3]])
        return (
            f"That time isn’t available on {new_date}. "
            f"Here are the closest free options:\n{suggestions}"
        )

    # 4) Identify which appointment to update
    #    Option A: explicit id in the message
    lead_id_target = extract_id(msg)

    #    Option B: name-based search (if not provided as id)
    if not lead_id_target and who_name:
        try:
            q = {"client_id": int(client_id_val), "query": who_name}
            raw = await lead_search.ainvoke(q)
            data = json.loads(raw) if isinstance(raw, str) else raw
            rows = (data or {}).get("rows") or []
            if rows:
                # Heuristic: pick the first row; you can refine by upcoming date/status, etc.
                lead_id_target = int(rows[0]["id"])
        except Exception as e:
            ai_dbg("lead.search.error", repr(e))

    if not lead_id_target:
        return ("I couldn’t find that patient’s appointment. "
                "Please provide the lead/appointment id or confirm the patient’s full name and I’ll try again.")

    # 5) Perform the update
    try:
        upd_req = {
            "client_id": int(client_id_val),
            "lead_id": int(lead_id_target),
            "clinic_id": int(clinic_id_fp),
            "date": new_date,
            "from_time": from_time,
            "to_time": to_time
        }
        upd_raw = await appointment_update.ainvoke(upd_req)
        upd = json.loads(upd_raw) if isinstance(upd_raw, str) else upd
        if isinstance(upd, dict) and upd.get("ok"):
            who_disp = who_name or f"Appointment #{lead_id_target}"
            # show HH:MM only
            ft = from_time[:-3]
            tt = to_time[:-3]
            return f"✅ Updated! {who_disp} is now scheduled for {new_date} {ft}–{tt}."
        return json.dumps(upd, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Update failed: {e}"}, ensure_ascii=False)
