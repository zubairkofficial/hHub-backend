import json
from typing import Any, Dict, List, Optional
import re
from datetime import datetime, timedelta
import difflib
# Ensure all agents register before use
import agents.defs  # noqa: F401
import httpx
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage

from agents.registry import get_agent, REGISTRY
from agents.router import pick_agent
from helper.chat_context import get_chat_history
from helper.get_data import get_client_data
# tools
from agents.tools.appointment_tools import appointment_create, appointment_update, appointment_get
from agents.tools.helpers.natural_language import parse_time_any, parse_date_any
# Services fast-path
from agents.fastpaths.services import parse_service_update
from agents.tools.service_tools import tool_service_update

from agents.tools.helpers.parsing import (
    EMAIL_RE, PHONE_RE,
    parse_lead_id, parse_clinic_id,
    UPDATE_CLINIC_NAME_TO,
    UPDATE_CLINIC_NAME_FREEFORM,
    UPDATE_CLINIC_NAME_POSSESSIVE_TO,
    UPDATE_CLINIC_NAME_OF_TO,
    UPDATE_CLINIC_RENAME_FROM_TO,
    UPDATE_CLINIC_CURRENT_NEW,
)
from agents.tools.helpers.logging import ai_dbg
from agents.tools.helpers.formatting import fmt_lead_details, fmt_clinic_details
from agents.tools.helpers.security import (
    get_client_id, enforce_client_id, remember_client_id,
    get_user_role_info, is_super_admin
)
from agents.fastpaths.leads import fastpath_fetch_lead_by_id, fastpath_search_leads, fastpath_update_lead
from agents.fastpaths.clinics import fastpath_update_clinic

# clinic HTTP tools
from agents.tools.http_clinics import clinic_get_http, clinic_search_http

# appointment tools
from agents.tools.appointment_tools import appointment_slots

def _json(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)

APP_ONLY_HINT = (
    "I can only help with Houmanity leads/clinics/services/appointments. "
    "Include an id, phone, email, or a clear command like:\n"
    "- 'list services'\n- 'my clinic details'\n- 'slots for clinic 3 today'\n- 'booked slots tomorrow'\n- 'cancel appointment 123'"
)

# ---------------- intent helpers ----------------

def _looks_like_appointment(msg: str) -> bool:
    m = (msg or "").lower()
    keys = (
        "appointment", "appointments", "book", "booking", "schedule", "reschedule", "give me available slots",
        "cancel appointment", "cancel booking", "slot", "slots", "availability", "available slots", "booked", "my clinic slots"
    )
    return any(k in m for k in keys)

def _looks_like_clinic(msg: str) -> bool:
    m = (msg or "").lower()
    if "clinic" not in m:
        return False
    # broaden triggers
    return any(k in m for k in ("my", "details", "info", "information", "address", "about", "show", "get", "my clinic"))

def _parse_slots_query(msg: str) -> Dict[str, Optional[str]]:
    """
    Extract clinic_id and date tokens from a freeform 'slots' message.
    Supports:
      - "slots for clinic 3"
      - "available slots today/tomorrow"
      - "slots for clinic 5 on 2025-11-05"
    """
    out: Dict[str, Optional[str]] = {"clinic_id": None, "date": None}
    m = re.search(r"\bclinic\s*(?:id|#)?\s*(\d{1,10})\b", msg, flags=re.I)
    if m:
        out["clinic_id"] = m.group(1)

    # natural-language date first; if nothing parseable, leave None (we'll default later)
    nl_date = parse_date_any(msg)
    if nl_date:
        out["date"] = nl_date
        return out

    ml = (msg or "").lower()
    if "today" in ml:
        out["date"] = datetime.today().isoformat()
    elif "tomorrow" in ml:
        out["date"] = (datetime.today() + timedelta(days=1)).isoformat()
    else:
        m2 = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", msg)
        if m2:
            out["date"] = m2.group(1)
    return out

def _fmt_slots_payload(payload: Dict[str, Any], *, booked_only: bool = False) -> str:
    if not payload.get("ok"):
        return _json(payload)
    slots = payload.get("slots") or {}

    def _rows(bucket_name: str):
        rows = slots.get(bucket_name, [])
        if booked_only:
            rows = [r for r in rows if r.get("has_booking")]
        return rows

    def bucket_lines(bucket_name: str) -> str:
        rows = _rows(bucket_name)
        if not rows:
            return "  (none)"
        return "\n".join([
            f"  - {r.get('from_time','?')}–{r.get('to_time','?')}{' (booked)' if r.get('has_booking') else ''}"
            for r in rows
        ])

    title = "Booked slots for" if booked_only else "Slots for"
    return (
        f"{title} {payload.get('date','—')}:\n"
        f"Morning:\n{bucket_lines('morning')}\n"
        f"Afternoon:\n{bucket_lines('afternoon')}\n"
        f"Evening:\n{bucket_lines('evening')}"
    )

# ---------- small helpers ----------

async def _autopick_single_clinic_id(client_id_val: Optional[int], user_message: Optional[str] = None) -> Optional[int]:
    """
    Try to resolve a clinic_id automatically.
    - If only one active clinic exists for this client, return it.
    - If multiple exist, attempt a fuzzy match with the clinic name from user_message.
    """
    if not client_id_val:
        return None

    try:
        args = {"client_id": int(client_id_val), "is_active": 1, "limit": 50}
        ai_dbg("clinic.search.request", {"url": "http://127.0.0.1:8080/api/clinics", "params": args})
        raw = await clinic_search_http.ainvoke(args)
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows = (data or {}).get("rows") or []

        if len(rows) == 1:
            return int(rows[0]["id"])

        # ✅ FIX: Better fuzzy matching for clinic names
        if user_message and rows:
            msg_lower = user_message.lower()
            
            # Build a mapping of clinic names to IDs
            clinic_map = {}
            for row in rows:
                name = str(row.get("name", "")).strip()
                if name:
                    clinic_map[name.lower()] = row["id"]
            
            # Try exact substring match first
            for name, cid in clinic_map.items():
                if name in msg_lower:
                    ai_dbg("clinic.autopick.substring_match", {"name": name, "id": cid})
                    return int(cid)
            
            # Fall back to fuzzy match
            matches = difflib.get_close_matches(msg_lower, clinic_map.keys(), n=1, cutoff=0.4)
            if matches:
                matched_name = matches[0]
                ai_dbg("clinic.autopick.fuzzy_match", {"match": matched_name, "id": clinic_map[matched_name]})
                return int(clinic_map[matched_name])

        ai_dbg("clinic.autopick.none", {"reason": "no match found", "total_clinics": len(rows)})
    except Exception as e:
        ai_dbg("clinic.autopick.error", repr(e))

    return None
def pick_clinic(rows, user_message):
    msg_lower = user_message.lower()
    clinic_map = {row["name"].lower(): row["id"] for row in rows if "name" in row}
    match = difflib.get_close_matches(msg_lower, clinic_map.keys(), n=1, cutoff=0.6)
    return clinic_map[match[0]] if match else None

async def _deterministic_slots_reply(user_message: str, client_id_val: Optional[int], clinic_id_req: Optional[int]) -> Optional[str]:
    """
    Build and call appointment_slots deterministically.
    Returns a formatted string if successful, else None to let the caller continue.
    """
    if client_id_val is None:
        return "I can’t get slots because this session isn’t linked to a client. Please sign in."

    booked_only = "booked" in (user_message or "").lower()
    parsed_slots = _parse_slots_query(user_message or "")
    clinic_id_fp = parsed_slots["clinic_id"] or clinic_id_req
    date_fp = parsed_slots["date"]

    if not clinic_id_fp:
        clinic_id_fp = clinic_id_req or await _autopick_single_clinic_id(client_id_val, user_message)


    # Default date to today if still empty
    if not date_fp:
        date_fp = datetime.today().isoformat()

    if not clinic_id_fp:
        ai_dbg("slots.fastpath", {"reason": "no clinic id resolved"})
        return None

    payload = {"client_id": int(client_id_val), "clinic_id": int(clinic_id_fp), "date": date_fp}
    ai_dbg("slots.fastpath.request", payload)
    try:
        raw = await appointment_slots.ainvoke(payload)
        data = json.loads(raw) if isinstance(raw, str) else raw
        ai_dbg("slots.fastpath.result", (data if isinstance(data, dict) else {}))
        # If upstream returns ok:false, surface it
        if not (isinstance(data, dict) and data.get("ok")):
            return _json(data)
        return _fmt_slots_payload(data, booked_only=booked_only)
    except Exception as e:
        return _json({"ok": False, "error": f"slots fastpath failed: {e}"})

async def _deterministic_book_reply(user_message: str, client_user_id: str, client_id_val: Optional[int], clinic_id_req: Optional[int]) -> Optional[str]:
    """
    If user asked to 'book' and did not provide a clear time, try autopicking the nearest free slot and creating an appointment
    using the current user's profile info (from get_client_data). Returns reply string on success/failure, or None to let the LLM handle it.
    """
    if client_id_val is None:
        return "I can't create appointments because this session isn't linked to a client. Please sign in."

    ml = (user_message or "").lower()
    if "book" not in ml and "create" not in ml and "schedule" not in ml:
        return None

    # Parse time and date from message
    parsed_time = parse_time_any(user_message or "")
    parsed_date = parse_date_any(user_message or "")
    
    # ✅ FIX: If user provides explicit time AND date, proceed with booking (don't return None)
    # Only return None if we can't determine what they want
    
    # Resolve clinic - try explicit ID first, then fuzzy match by name
    clinic_id_fp = clinic_id_req
    if not clinic_id_fp:
        clinic_id_fp = await _autopick_single_clinic_id(client_id_val, user_message)

    if not clinic_id_fp:
        return "I couldn't determine which clinic to book for. Please include the clinic id (e.g., 'book for clinic 1') or tell me which clinic."

    # Choose date (today if none)
    date_fp = parsed_date or datetime.today().isoformat()

    # ✅ FIX: If user provided explicit time, use it directly instead of auto-picking
    if parsed_time and parsed_date:
        # User gave us both time and date - create appointment directly
        chosen_from = parsed_time
        # Calculate end time (30 min later)
        from agents.tools.helpers.natural_language import duration_to_end
        chosen_to = duration_to_end(chosen_from, 30)
        
        # Fetch user profile
        try:
            prof = await get_client_data(int(client_user_id))
        except Exception:
            prof = None

        # Extract user details
        first_name = None
        last_name = None
        email = None
        contact_number = None
        
        if isinstance(prof, dict):
            first_name = prof.get("name") or prof.get("first_name") or None
            if first_name and " " in first_name:
                parts = first_name.split(" ", 1)
                first_name, last_name = parts[0], parts[1]
            last_name = last_name or prof.get("last_name") or prof.get("family") or last_name
            email = prof.get("email") or email
            contact_number = prof.get("mobile_number") or prof.get("contact_number") or contact_number

        # ✅ FIX: Extract patient details from message if provided
        # Look for patterns like "Patient's name is X, email Y, DOB Z, gender G"
        name_match = re.search(r"(?:patient(?:'s)?\s+name\s+is|name\s*:?)\s+([A-Za-z\s]+?)(?:,|\s+email|$)", user_message, re.I)
        email_match = re.search(r"(?:email\s*:?)\s+([^\s,]+@[^\s,]+)", user_message, re.I)
        dob_match = re.search(r"(?:dob\s*:?|date\s+of\s+birth\s*:?)\s+(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})", user_message, re.I)
        gender_match = re.search(r"(?:gender\s*:?)\s+(male|female)", user_message, re.I)
        
        if name_match:
            full_name = name_match.group(1).strip()
            parts = full_name.split(None, 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
        
        if email_match:
            email = email_match.group(1)
            
        dob = dob_match.group(1) if dob_match else None
        gender = gender_match.group(1).lower() if gender_match else "male"

        if not first_name and not email:
            return ("I can book a slot automatically, but I need at least the patient's name or email. "
                    "Please provide: name, email, or phone.")

        # Build create payload
        create_payload = {
            "client_id": int(client_id_val),
            "clinic_id": int(clinic_id_fp),
            "date": date_fp,
            "from_time": chosen_from,
            "to_time": chosen_to,
            "first_name": first_name or "Guest",
            "last_name": last_name or "",
            "email": email or "",
            "contact_number": contact_number or "",
            "gender": gender,
            "dob": dob,
            "description": f"Booked via chat by user {client_user_id}"
        }

        # Call create
        try:
            ai_dbg("book.fastpath.create.request", create_payload)
            rawc = await appointment_create.ainvoke(create_payload)
            created = json.loads(rawc) if isinstance(rawc, str) else rawc
            ai_dbg("book.fastpath.create.result", created if isinstance(created, dict) else {})
        except Exception as e:
            return _json({"ok": False, "error": f"Create failed: {e}"})
        
        if not (isinstance(created, dict) and created.get("ok")):
            return _json(created)

        return (f"✅ Done — I booked an appointment for {date_fp} {chosen_from[:-3]}–{chosen_to[:-3]} at clinic #{clinic_id_fp}. "
                f"Patient: {create_payload['first_name']} {create_payload['last_name']}, "
                f"Email: {create_payload['email'] or '—'}, Phone: {create_payload['contact_number'] or '—'}.")
    
    # If no explicit time, fetch slots and pick earliest free one
    try:
        payload = {"client_id": int(client_id_val), "clinic_id": int(clinic_id_fp), "date": date_fp}
        ai_dbg("book.fastpath.slots.request", payload)
        raw = await appointment_slots.ainvoke(payload)
        slots_payload = json.loads(raw) if isinstance(raw, str) else raw
        ai_dbg("book.fastpath.slots.result", slots_payload if isinstance(slots_payload, dict) else {})
    except Exception as e:
        return _json({"ok": False, "error": f"Slots lookup failed: {e}"})

    if not (isinstance(slots_payload, dict) and slots_payload.get("ok")):
        return _json(slots_payload)

    # Flatten free slots and pick the earliest free
    flat = []
    for bucket in ("morning", "afternoon", "evening"):
        for s in (slots_payload.get("slots") or {}).get(bucket, []):
            if not s.get("has_booking"):
                flat.append((s["from_time"], s["to_time"]))
    
    if not flat:
        return f"No free slots available on {date_fp}."

    # Pick earliest by time
    def _sec(hms): 
        parts = hms.split(":")
        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
        return h*3600 + m*60
    flat.sort(key=lambda p: _sec(p[0]))
    chosen_from, chosen_to = flat[0]
# ------------------------------------------------------

async def run_with_agent(user_message: str, chat_id: int, user_id: str) -> str:
    ai_dbg("chat.incoming", {"user_id": user_id, "chat_id": chat_id, "user_message": user_message})
    msg = (user_message or "").strip()

    # Role (for service update restriction)
    role_info = await get_user_role_info(user_id)
    ai_dbg("user.role", role_info)
    sa = await is_super_admin(user_id)

    # Detect intents
    svc_intent   = any(w in msg.lower() for w in ("service", "services"))
    appt_intent  = _looks_like_appointment(msg)
    clinic_intent = _looks_like_clinic(msg)

    # Service fast-path update (block non-SA)
    parsed = None
    if svc_intent:
        parsed = parse_service_update(msg)
    if parsed:
        if not sa:
            return "You don't have permission to update services. Only a Super Admin can perform this action."
        try:
            res = await tool_service_update.ainvoke(parsed)
            return res
        except Exception as e:
            return json.dumps({"ok": False, "error": f"Service fastpath update failed: {e}"}, ensure_ascii=False)

    # tenancy
    client_id_val = await get_client_id(user_id)
    ai_dbg("user.client_id", client_id_val)
    ai_dbg("clinic.fastpath.precheck", {"client_id_val": client_id_val, "msg": msg[:120]})
    remember_client_id(user_id, client_id_val)

    # parse hints for lead/clinic
    lead_id_req   = parse_lead_id(msg)
    clinic_id_req = parse_clinic_id(msg)
    em = EMAIL_RE.search(msg)
    ph = PHONE_RE.search(msg)
    email_hint = em.group(0) if em else None
    phone_hint = ph.group(0) if ph else None
    ai_dbg("parsed.hints", {
        "lead_id_req": lead_id_req, "clinic_id_req": clinic_id_req,
        "email_hint": email_hint, "phone_hint": phone_hint
    })

    # ---- Predeclare captures so early fallbacks can reference them safely ----
    fetched_lead: Optional[Dict[str, Any]] = None
    fetched_clinic: Optional[Dict[str, Any]] = None
    searched_rows: List[Dict[str, Any]] = []
    lead_updated_id: Optional[int] = None

    clinic_rows: List[Dict[str, Any]] = []   # may be filled later by clinic_search_http

    # Services capture
    service_rows: List[Dict[str, Any]] = []
    service_one: Optional[Dict[str, Any]] = None
    service_update_resp: Optional[Dict[str, Any]] = None

    # Appointments capture
    appt_slots: Optional[Dict[str, Any]] = None
    appt_create_resp: Optional[Dict[str, Any]] = None
    appt_update_resp: Optional[Dict[str, Any]] = None
    appt_cancel_resp: Optional[Dict[str, Any]] = None
    appt_show: Optional[Dict[str, Any]] = None
    # -------------------------------------------------------------------------

    # clinic rename special casing
    intent_rename = any((
        UPDATE_CLINIC_NAME_TO.search(msg),
        UPDATE_CLINIC_NAME_FREEFORM.search(msg),
        UPDATE_CLINIC_NAME_POSSESSIVE_TO.search(msg),
        UPDATE_CLINIC_NAME_OF_TO.search(msg),
        UPDATE_CLINIC_RENAME_FROM_TO.search(msg),
        UPDATE_CLINIC_CURRENT_NEW.search(msg),
    ))
    if client_id_val is None and intent_rename:
        return ("I can’t update your clinic because this session isn’t linked to a client. "
                "Please sign in, then try again.")
    if client_id_val is None and (lead_id_req is not None or clinic_id_req is not None or email_hint or phone_hint):
        return ("I can’t access lead or clinic data because your account isn’t linked to a client yet. "
                "Please sign in or ensure your user has a client_id assigned.")
    if intent_rename:
        clinic_id_req = None

    # 1) clinic update fast-path
    upd = await fastpath_update_clinic(msg, client_id_val)
    if upd is not None:
        ai_dbg("clinic.update.return", upd[:300].replace("\n", " | "))
        return upd

    # 1b) lead update fast-path
    upd_lead = await fastpath_update_lead(msg, client_id_val)
    if upd_lead is not None:
        ai_dbg("lead.update.return", upd_lead[:300].replace("\n", " | "))
        return upd_lead

    # --- Early deterministic SLOTS check ---
        # If user asked to book and model didn't produce tools, try deterministic booking (post-LLM we also call this)
    if appt_intent and any(k in msg.lower() for k in ("book", "create", "schedule", "make an appointment")):
        # Try booking immediately (best-effort)
        book = await _deterministic_book_reply(user_message, user_id, client_id_val, clinic_id_req)
        if book is not None:
            return book

    if appt_intent and "slot" in (user_message or "").lower():
        ai_dbg("slots.fastpath.trigger", {"phase": "pre-LLM"})
        early = await _deterministic_slots_reply(user_message, client_id_val, clinic_id_req)
        if early is not None:
            return early

    # ---------- Clinic DETAILS fast-path ----------
    if clinic_intent:
        if client_id_val is None:
            return "I can’t get clinic details because this session isn’t linked to a client. Please sign in."
        # If clinic id explicitly in message, use it; else attempt single-clinic autopick.
        clinic_for_details = clinic_id_req
        if not clinic_for_details:
            try:
                args = {"client_id": int(client_id_val), "is_active": 1, "limit": 5}
                ai_dbg("clinic.search.request", {"url": "http://127.0.0.1:8080/api/clinics", "params": args})
                raw = await clinic_search_http.ainvoke(args)
                data = json.loads(raw) if isinstance(raw, str) else raw
                rows = (data or {}).get("rows") or []
                if len(rows) == 1:
                    clinic_for_details = rows[0]["id"]
            except Exception as e:
                ai_dbg("clinic.autopick.error", repr(e))

        if clinic_for_details:
            try:
                args_c = {"client_id": int(client_id_val), "clinic_id": int(clinic_for_details)}
                rawc = await clinic_get_http.ainvoke(args_c)
                dc = json.loads(rawc) if isinstance(rawc, str) else rawc
                if dc.get("ok") and dc.get("clinic"):
                    return "Clinic details:\n" + fmt_clinic_details(dc["clinic"])
                return "Clinic not found for your account."
            except Exception as e:
                return _json({"ok": False, "error": f"clinic details fastpath failed: {e}"})
        # If user has multiple clinics, agent path will ask which one.

    # 2) fetch fast-path for lead/clinic by explicit ids/emails/phones
    async def _fastpath_fetch() -> Optional[str]:
        if client_id_val is None:
            ai_dbg("fastpath.skip", "no client_id")
            return None

        if lead_id_req is not None:
            return await fastpath_fetch_lead_by_id(client_id_val, lead_id_req, phone_hint, email_hint)

        if clinic_id_req is not None:
            try:
                args_c = {"client_id": client_id_val, "clinic_id": clinic_id_req}
                ai_dbg("fastpath.clinic_get.args", args_c)
                rawc = await clinic_get_http.ainvoke(args_c)
                ai_dbg("fastpath.clinic_get.raw", (rawc[:500] if isinstance(rawc, str) else str(rawc)[:500]))
                dc = json.loads(rawc) if isinstance(rawc, str) else rawc
            except Exception as e:
                ai_dbg("fastpath.clinic_get.error", repr(e))
                dc = {"ok": False}

            if dc.get("ok") and dc.get("clinic"):
                clinic = dc["clinic"]
                return f"Clinic #{clinic_id_req} details:\n" + fmt_clinic_details(clinic)
            return f"Clinic #{clinic_id_req} not found for your account."

        if email_hint or phone_hint:
            return await fastpath_search_leads(client_id_val, phone_hint, email_hint, lead_id_req)

        ai_dbg("fastpath.skip", "no id/email/phone hints")
        return None

    fast = await _fastpath_fetch()
    if fast is not None:
        ai_dbg("fastpath.return", fast[:300].replace("\n", " | "))
        return fast

    # 3) choose agent
    try:
        if svc_intent:
            agent_name = "ServiceAgent"
        elif appt_intent:
            agent_name = "AppointmentAgent"
        elif clinic_intent:
            agent_name = "ClinicAgent"
        elif (lead_id_req or clinic_id_req or email_hint or phone_hint):
            agent_name = "SQLReader"
        else:
            agent_name = (await pick_agent(user_message))["agent"]
    except Exception:
        if   svc_intent:   agent_name = "ServiceAgent"
        elif appt_intent:  agent_name = "AppointmentAgent"
        elif clinic_intent:agent_name = "ClinicAgent"
        else:              agent_name = "SQLReader"

    # safe fallback
    available = list(REGISTRY.keys())
    if agent_name in REGISTRY:
        spec = get_agent(agent_name)
    else:
        ai_dbg("agent.missing", {"requested": agent_name, "available": available})
        if   appt_intent and "AppointmentAgent" in REGISTRY: spec = get_agent("AppointmentAgent")
        elif clinic_intent and "ClinicAgent" in REGISTRY:    spec = get_agent("ClinicAgent")
        elif svc_intent and "ServiceAgent" in REGISTRY:      spec = get_agent("ServiceAgent")
        elif "SQLReader" in REGISTRY:                        spec = get_agent("SQLReader")
        elif available:                                      spec = REGISTRY[available[0]]
        else:
            return APP_ONLY_HINT

    ai_dbg("agent.selected", {"agent": spec.name})

    # Restrict service_update tool for non-SA
    tools_to_bind = list(spec.tools or [])
    if spec.name == "ServiceAgent" and not sa:
        tools_to_bind = [t for t in tools_to_bind if getattr(t, "name", "") != "service_update"]

    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    if getattr(spec, "allow_tool_calls", True) and tools_to_bind:
        model = model.bind_tools(tools_to_bind)
    ai_dbg("agent.tools", {"tools": [t.name for t in (tools_to_bind or [])]})

    history = await get_chat_history(chat_id)
    sys_prompt = spec.system_prompt
    if client_id_val is not None and spec.name in ("SQLReader", "LeadAgent", "ClinicAgent", "AppointmentAgent"):
        sys_prompt = f"{sys_prompt}\n[SECURITY NOTE] Current client_id={client_id_val}. All operations must include client_id={client_id_val}."

    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        MessagesPlaceholder("history"),
        ("user", "{prompt}"),
    ])
    rendered = await prompt.ainvoke({"history": history, "prompt": user_message})
    messages = rendered.to_messages()

    ai_msg = await model.ainvoke(messages)
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    ai_dbg("agent.tool_calls", {"tool_calls": tool_calls})

       # If the model chose AppointmentAgent but didn't call any tools, force deterministic slots
    if not tool_calls and spec.name == "AppointmentAgent":
        ai_dbg("slots.fastpath.trigger", {"phase": "post-LLM-no-tools"})
        # If user asked to book, try book-first
        if any(k in msg.lower() for k in ("book", "create", "schedule", "make an appointment")):
            forced_book = await _deterministic_book_reply(user_message, user_id, client_id_val, clinic_id_req)
            if forced_book is not None:
                return forced_book
        forced = await _deterministic_slots_reply(user_message, client_id_val, clinic_id_req)
        if forced is not None:
            return forced


    if not tool_calls:
        ai_dbg("agent.no_tools", "no tool calls produced; returning app-only hint")
        return APP_ONLY_HINT

    followups: List[Any] = [ai_msg]
    name_to_fn = {t.name: t for t in (tools_to_bind or [])}

    for tc in tool_calls:
        name = tc.get("name")
        args = tc.get("args", {}) or {}
        try:
            safe_args = enforce_client_id(name, args, client_id_val)
            ai_dbg("tool.call", {"name": name, "args": safe_args})

            if name not in name_to_fn:
                raise RuntimeError(f"Tool '{name}' is not available on agent '{spec.name}'")

            result = await name_to_fn[name].ainvoke(safe_args)
            ai_dbg("tool.result", (result[:500] if isinstance(result, str) else str(result)[:500]))
            data = json.loads(result) if isinstance(result, str) else result

            # lead/clinic captures
            if name in ("lead_get", "lead_get_http"):
                if isinstance(data, dict) and data.get("ok") and data.get("lead"):
                    fetched_lead = data["lead"]
            elif name in ("clinic_get", "clinic_get_http"):
                if isinstance(data, dict) and data.get("ok") and data.get("clinic"):
                    fetched_clinic = data["clinic"]
            elif name == "lead_search":
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
                    searched_rows = data["rows"]
            elif name in ("lead_update_http", "update_lead"):
                lead_updated_id = safe_args.get("lead_id") or lead_updated_id
                if isinstance(data, dict) and data.get("ok"):
                    return f"Lead #{lead_updated_id or '—'} updated successfully."
            elif name == "clinic_search_http":
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
                    clinic_rows = data["rows"]

            # services captures
            elif name == "service_list":
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
                    service_rows = data["rows"]
            elif name == "service_search":
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
                    service_rows = data["rows"]
            elif name == "service_get":
                if isinstance(data, dict) and data.get("ok") and data.get("row"):
                    service_one = data["row"]
                elif isinstance(data, dict) and data.get("ok") and data.get("service"):
                    service_one = data["service"]
            elif name == "service_update":
                service_update_resp = data if isinstance(data, dict) else None

            # appointment captures
            elif name == "appointment_slots":
                appt_slots = data if isinstance(data, dict) else None
            elif name == "appointment_create":
                appt_create_resp = data if isinstance(data, dict) else None
            elif name == "appointment_update":
                appt_update_resp = data if isinstance(data, dict) else None
            elif name == "appointment_cancel":
                appt_cancel_resp = data if isinstance(data, dict) else None
            elif name == "appointment_get":
                appt_show = data if isinstance(data, dict) else None

            result_str = _json({"ok": True, "tool": name, "args_used": safe_args, "result": data})
        except Exception as e:
            ai_dbg("tool.error", {name: repr(e)})
            result_str = _json({"ok": False, "tool": name, "error": f"{e.__class__.__name__}: {e}"})
        followups.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    # Deterministic returns

    # Appointments first
    if appt_slots:
        return _fmt_slots_payload(appt_slots)
    # In the run_with_agent function, update the "Appointments first" section as follows:

    # Appointments first
    if appt_slots:
        return _fmt_slots_payload(appt_slots)
    if appt_create_resp is not None:
        if appt_create_resp.get("ok"):
            lead = appt_create_resp.get("lead", {})
            date_str = lead.get("date", "—")
            from_time = lead.get("from_time", "—:00")[:-3] if lead.get("from_time") else "—"
            to_time = lead.get("to_time", "—:00")[:-3] if lead.get("to_time") else "—"
            first_name = lead.get("first_name", "—")
            last_name = lead.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            email = lead.get("email", "—")
            phone = lead.get("contact_number", "—")
            gender = lead.get("gender", "—").capitalize()
            dob = lead.get("dob", "—")
            clinic_id = lead.get("clinic_id", "—")

            # Format date nicely (e.g., "October 24, 2025")
            try:
                from datetime import datetime
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%B %d, %Y")
            except:
                formatted_date = date_str

            # Get clinic name if possible (optional: fetch via clinic_get_http if needed)
            clinic_name = "Happy Teeth Clinic"  # Hardcode or fetch dynamically

            response = f"""✅ Appointment booked successfully at {clinic_name}!

**Details:**
- **Date:** {formatted_date}
- **Time:** {from_time}–{to_time}
- **Patient:** {full_name} ({gender}, DOB: {dob})
- **Email:** {email}
- **Phone:** {phone}
- **Appointment ID:** #{lead.get("id", "—")}

If you need to reschedule, cancel, or add more details, just let me know!"""
            return response
        else:
            return _json(appt_create_resp)
    if appt_update_resp is not None:
        # Similarly format update response
        if appt_update_resp.get("ok"):
            lead = appt_update_resp.get("lead", {})  # Assuming it returns updated lead
            # ... similar formatting as above, but for "updated"
            return "✅ Appointment updated successfully!"  # Or detailed
        return _json(appt_update_resp)
    if appt_cancel_resp is not None:
        return _json(appt_cancel_resp)  # Or format as "Cancelled successfully"
    if appt_show is not None:
        return _json(appt_show)

# Additionally, ensure imports include:
# from datetime import datetime
    if appt_update_resp is not None:
        return _json(appt_update_resp)
    if appt_cancel_resp is not None:
        return _json(appt_cancel_resp)
    if appt_show is not None:
        return _json(appt_show)

    # Services
    if service_update_resp is not None:
        if service_update_resp.get("ok"):
            s = service_update_resp.get("service")
            if isinstance(s, dict):
                sid = s.get("id", "—")
                nm = s.get("name", "—")
                return f"Service #{sid} updated successfully.\nName: {nm}\nfor_report: {s.get('for_report','—')}\nDescription: {s.get('description','—')}"
            return "Service updated successfully."
        return _json(service_update_resp)

    if service_one:
        return (
            f"Service #{service_one.get('id','—')} details:\n"
            f"- Name: {service_one.get('name','—')}\n"
            f"- for_report: {service_one.get('for_report','—')}\n"
            f"- Description: {service_one.get('description','—')}"
        )

    # Return the service list if we have it
    if service_rows:
        lines = [f"• #{r.get('id','—')}: {(r.get('name') or '—').strip()}" for r in service_rows]
        if len(lines) > 20:
            lines = lines[:20] + [f"… and {len(service_rows)-20} more"]
        return "Services:\n" + "\n".join(lines)


  # Clinics (from clinic_search_http deterministic handling)
    if clinic_rows and "clinic" in (user_message or "").lower():
        if len(clinic_rows) == 1:
            try:
                only_id = int(clinic_rows[0]["id"])
                args_c = {"client_id": int(client_id_val), "clinic_id": only_id}
                rawc = await clinic_get_http.ainvoke(args_c)
                dc = json.loads(rawc) if isinstance(rawc, str) else rawc
                if dc.get("ok") and dc.get("clinic"):
                    return "Clinic details:\n" + fmt_clinic_details(dc["clinic"])
            except Exception:
                pass
        lines = [f"• #{r.get('id','—')}: {r.get('name','—')}" for r in clinic_rows[:10]]
        more  = f"\n… and {len(clinic_rows)-10} more" if len(clinic_rows) > 10 else ""
        return "Clinics found:\n" + "\n".join(lines) + more

    # Leads / Clinics (fetched)
    if fetched_lead:
        if phone_hint and (fetched_lead.get("contact_number") or "").strip() != (phone_hint or "").strip():
            return "No access or unauthorized for this lead."
        if email_hint and (fetched_lead.get("email") or "").strip().lower() != (email_hint or "").strip().lower():
            return "No access or unauthorized for this lead."
        return f"Lead #{fetched_lead['id']} details:\n" + fmt_lead_details(fetched_lead)

    if fetched_clinic:
        return f"Clinic details:\n" + fmt_clinic_details(fetched_clinic)

    if searched_rows:
        lines = [
            f"• #{r['id']}: {r.get('first_name','')} {r.get('last_name','')} — {r.get('email','—')} — {r.get('contact_number','—')} — {r.get('status','—')}"
            for r in searched_rows[:10]
        ]
        return "Matches:\n" + "\n".join(lines)

    if lead_updated_id:
        return f"Lead #{lead_updated_id} updated successfully."

    return APP_ONLY_HINT
