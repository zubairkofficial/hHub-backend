from __future__ import annotations
import json
from typing import Optional, Dict, Any, List

from agents.tools.http_leads import lead_get_http, lead_lookup_http, lead_update_http
from agents.tools.helpers.logging import ai_dbg
from agents.tools.helpers.parsing import parse_lead_id, parse_lead_update_fields

def _yesno(v) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if v in (0, 1, "0", "1"):
        return "Yes" if str(v) == "1" else "No"
    return "—" if v is None else str(v)

def _preview(val, maxlen: int = 140) -> str:
    import json as _json
    if val is None:
        return "—"
    if isinstance(val, (dict, list)):
        try:
            s = _json.dumps(val, ensure_ascii=False)
        except Exception:
            s = str(val)
    else:
        s = str(val)
    s = s.strip()
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _fmt_lead_details(lead: Dict[str, Any]) -> str:
    lead_id      = lead.get("id", "—")
    client_id    = lead.get("client_id", "—")
    clinic_id    = lead.get("clinic_id", "—")
    first_name   = lead.get("first_name", "") or ""
    last_name    = lead.get("last_name", "") or ""
    full_name    = (first_name + " " + last_name).strip() or "—"
    email        = lead.get("email", "—")
    phone        = lead.get("contact_number", "—")
    status       = lead.get("status", "—")
    type_        = lead.get("type", "—")
    source_type  = lead.get("source_type", "—")
    lead_source  = lead.get("lead_source", "—")
    date         = lead.get("date", "—")
    from_time    = lead.get("from_time", "—")
    to_time      = lead.get("to_time", "—")
    booking_for  = lead.get("booking_for", "—")
    booking_id   = lead.get("booking_id", "—")
    dob          = lead.get("dob", "—")
    gender       = lead.get("gender", "—")
    potential    = lead.get("potential_score", "—")
    value        = lead.get("value", "—")
    is_scored    = _yesno(lead.get("is_scored"))
    is_self      = _yesno(lead.get("is_self"))
    is_convert   = _yesno(lead.get("is_convert"))
    description  = _preview(lead.get("description"))
    message      = _preview(lead.get("message"))
    transcription = _preview(lead.get("transcription"))
    transcription_audio = _preview(lead.get("transcription_audio"))
    callrail_id  = lead.get("callrail_id", "—")
    created_at   = lead.get("created_at", "—")
    updated_at   = lead.get("updated_at", "—")

    lines = []
    lines.append(f"**Lead #{lead_id}**")
    lines.append(f"- Client ID / Clinic ID: {client_id} / {clinic_id}")
    lines.append(f"- Name: {full_name}")
    lines.append(f"- Email / Phone: {email} / {phone}")
    lines.append(f"- Status / Type: {status} / {type_}")
    lines.append(f"- Source: {source_type} (lead_source: {lead_source})")

    if any(x not in (None, "", "—") for x in (date, from_time, to_time, booking_for, booking_id)):
        lines.append("")
        lines.append("**Booking / Schedule**")
        lines.append(f"- Date / Window: {date} | {from_time} → {to_time}")
        lines.append(f"- Booking For / ID: {booking_for} / {booking_id}")

    if any(x not in (None, "", "—") for x in (dob, gender)):
        lines.append("")
        lines.append("**Person**")
        lines.append(f"- DOB / Gender: {dob} / {gender}")

    if any(x not in (None, "", "—") for x in (potential, value, is_scored, is_self, is_convert)):
        lines.append("")
        lines.append("**Scores & Value**")
        lines.append(f"- Potential Score / Value: {potential} / {value}")
        lines.append(f"- Scored? {is_scored} | Self? {is_self} | Converted? {is_convert}")

    if callrail_id not in (None, "", "—"):
        lines.append("")
        lines.append("**CallRail**")
        lines.append(f"- CallRail ID: {callrail_id}")

    if any(x != "—" for x in (description, message, transcription, transcription_audio)):
        lines.append("")
        lines.append("**Notes / Content**")
        if description != "—":
            lines.append(f"- Description: {description}")
        if message != "—":
            lines.append(f"- Message (JSON): {message}")
        if transcription != "—":
            lines.append(f"- Transcription: {transcription}")
        if transcription_audio != "—":
            lines.append(f"- Transcription Audio (JSON): {transcription_audio}")

    lines.append("")
    lines.append("**Timestamps**")
    lines.append(f"- Created: {created_at}")
    lines.append(f"- Updated: {updated_at}")

    return "\n".join(lines)

async def fastpath_fetch_lead_by_id(client_id: int, lead_id: int,
                                    phone_hint: Optional[str], email_hint: Optional[str]) -> str:
    args = {"client_id": client_id, "lead_id": lead_id}
    ai_dbg("fastpath.lead_get.args", args)
    raw = await lead_get_http.ainvoke(args)
    ai_dbg("fastpath.lead_get.raw", (raw[:500] if isinstance(raw, str) else str(raw)[:500]))
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return "Lead fetch failed: bad_json"
    if not isinstance(data, dict) or not data.get("ok"):
        return f"Lead fetch failed: {data.get('error','unknown_error') if isinstance(data, dict) else 'unknown_error'}"

    lead = data.get("lead") or {}
    if phone_hint and (lead.get("contact_number") or "").strip() != (phone_hint or "").strip():
        return "No access or unauthorized for this lead."
    if email_hint and (lead.get("email") or "").strip().lower() != (email_hint or "").strip().lower():
        return "No access or unauthorized for this lead."

    return f"Lead #{lead.get('id','?')} details:\n{_fmt_lead_details(lead)}"

async def fastpath_search_leads(client_id: int, phone_hint: Optional[str], email_hint: Optional[str],
                                lead_id_req: Optional[int]) -> Optional[str]:
    args = {"client_id": client_id, "phone": phone_hint, "email": email_hint, "limit": 10}
    ai_dbg("fastpath.search.args", args)
    raw = await lead_lookup_http.ainvoke(args)
    ai_dbg("fastpath.search.raw", (raw[:500] if isinstance(raw, str) else str(raw)[:500]))
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        # parsing failed → let orchestrator continue to agent/tools
        return None

    # If the HTTP layer timed out or errored, do NOT block the flow. Return None.
    if isinstance(data, dict) and not data.get("ok"):
        err = str(data.get("error", "")).lower()
        if "timeout" in err or "http_error" in err or err.startswith("http_"):
            return None
        # other non-timeout errors can still bubble as a short message if you prefer:
        return f"Search error: {data.get('error','unknown')}"

    if "lead" in data and isinstance(data["lead"], dict):
        lead = data["lead"]
        return f"Lead #{lead.get('id','?')} details:\n{_fmt_lead_details(lead)}"

    rows: List[Dict[str, Any]] = data.get("rows") or []
    if not rows:
        return "No matches."

    lines = [
        f"• #{r.get('id','?')}: {r.get('first_name','')} {r.get('last_name','')} — {r.get('email','—')} — {r.get('contact_number','—')} — {r.get('status','—')}"
        for r in rows[:10]
    ]
    return "Matches:\n" + "\n".join(lines)

async def fastpath_update_lead(msg: str, client_id_val: Optional[int]) -> Optional[str]:
    """
    Parse update intent + fields; if present and we have client_id + lead_id, execute update immediately.
    Returns a user message on success/failure, or None if no update intent was detected.
    """
    fields = parse_lead_update_fields(msg)
    if not fields:
        return None

    if client_id_val is None:
        return ("I can’t update that lead because this session isn’t linked to a client. "
                "Please sign in, then try again.")

    lead_id = parse_lead_id(msg)
    if lead_id is None:
        return "Please specify the lead ID (e.g., 'update lead 123 status to Hot')."

    args = {"client_id": client_id_val, "lead_id": lead_id, **fields}
    ai_dbg("fastpath.lead_update.args", args)
    raw = await lead_update_http.ainvoke(args)
    ai_dbg("fastpath.lead_update.raw", (raw[:500] if isinstance(raw, str) else str(raw)[:500]))

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return f"Lead #{lead_id} update failed: bad_json"

    ok = bool(data.get("ok"))
    return f"Lead #{lead_id} updated successfully." if ok else f"Lead #{lead_id} update failed."
