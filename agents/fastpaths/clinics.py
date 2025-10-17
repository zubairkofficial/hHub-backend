# agents/fastpaths/clinics.py
from __future__ import annotations
import json
from typing import Optional, Dict, Any, List

from agents.tools.http_clinics import clinic_search_http, clinic_update, clinic_get_http
from agents.tools.helpers.parsing import (
    UPDATE_CLINIC_NAME_OF_TO,
    UPDATE_CLINIC_SIMPLE,
    UPDATE_CLINIC_NAME_TO,
    UPDATE_CLINIC_RENAME_FROM_TO,
    UPDATE_CLINIC_CURRENT_NEW,
    UPDATE_CLINIC_NAME_FREEFORM,
    UPDATE_CLINIC_NAME_POSSESSIVE_TO,
)
import re

from agents.tools.helpers.clinic_helper import _resolve_clinic_id_for_update
from agents.tools.helpers.logging import ai_dbg

def _coerce_boolish(v: str) -> bool:
    s = str(v).strip().lower()
    if s in {"1","true","yes","y"}: return True
    if s in {"0","false","no","n"}: return False
    try: return bool(int(s))
    except Exception:
        return bool(s)

def _coerce_field(field: str, value_raw: str):
    f = field.lower().strip()
    if f in {"country_id","state_id","city_id"}:
        try: return int(value_raw)
        except Exception: return value_raw
    if f == "is_active":
        return _coerce_boolish(value_raw)
    return value_raw

def _fmt_clinic_details(c: Dict[str, Any]) -> str:
    return (
        f"- Name: {c.get('name') or '—'}\n"
        f"- Address: {c.get('address') or '—'} {c.get('address2') or ''}\n"
        f"- City/State/Country IDs: {c.get('city_id')} / {c.get('state_id')} / {c.get('country_id')}\n"
        f"- Zip: {c.get('zip_code') or '—'}\n"
        f"- Active: {c.get('is_active')}\n"
        f"- Review URL: {c.get('review_url') or '—'}\n"
        f"- Google Review URL: {c.get('google_review_url') or '—'}\n"
        f"- TW SIDs: appt={c.get('tw_content_sid_appt') or '—'}, review={c.get('tw_content_sid_review') or '—'}, nurture={c.get('tw_content_sid_nurture') or '—'}\n"
        f"- Created: {c.get('created_at')}\n"
        f"- Updated: {c.get('updated_at')}"
    )

async def _post_update_fetch(client_id_val: int, clinic_id: int) -> Optional[str]:
    try:
        g = await clinic_get_http.ainvoke({"client_id": client_id_val, "clinic_id": clinic_id})
        d = json.loads(g) if isinstance(g, str) else g
        if isinstance(d, dict) and d.get("ok") and d.get("clinic"):
            return f"Clinic #{clinic_id} updated.\n" + _fmt_clinic_details(d["clinic"])
    except Exception as e:
        ai_dbg("clinic.update.fetch_after.error", repr(e))
    return f"Clinic #{clinic_id} updated."

async def _update_and_confirm(client_id_val: int, clinic_id: int, updates: Dict[str, Any]) -> str:
    args = {"client_id": client_id_val, "clinic_id": clinic_id, **updates}
    ai_dbg("clinic.update.args", args)
    try:
        res = await clinic_update.ainvoke(args)
        ai_dbg("clinic.update.raw", (res[:500] if isinstance(res, str) else str(res)[:500]))
        # clinic_update returns "CLINIC_UPDATE:OK:{json}" or "CLINIC_UPDATE:FAIL:..."
        if isinstance(res, str) and res.startswith("CLINIC_UPDATE:OK:"):
            return await _post_update_fetch(client_id_val, clinic_id)
        # attempt to parse json if provided
        if isinstance(res, str) and res.startswith("CLINIC_UPDATE:FAIL:"):
            return f"Clinic update failed: {res.split('CLINIC_UPDATE:FAIL:',1)[-1]}"
        # fallthrough: treat as dict {ok:..., ...} if the tool ever changes
        data = json.loads(res) if isinstance(res, str) else res
        if isinstance(data, dict) and data.get("ok"):
            return await _post_update_fetch(client_id_val, clinic_id)
        return "Clinic update failed: unknown_error"
    except Exception as e:
        ai_dbg("clinic.update.error", repr(e))
        return f"Clinic update failed: {e.__class__.__name__}"

def _extract_clinic_id(row: Dict[str, Any]) -> Optional[int]:
    for k in ("id", "clinic_id", "clinicId"):
        v = row.get(k)
        if isinstance(v, int) and v > 0:
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
    return None

async def _list_or_disambiguate(client_id_val: int) -> str:
    try:
        raw = await clinic_search_http.ainvoke({"client_id": client_id_val, "limit": 5})
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows: List[Dict[str, Any]] = (data or {}).get("rows") or []
    except Exception as e:
        ai_dbg("clinic.update.intent.lookup.error", repr(e))
        rows = []

    if not rows:
        return "I can update your clinic name, but I can't find any clinics on your account. Please create a clinic first."

    if len(rows) == 1:
        cid = _extract_clinic_id(rows[0])
        cname = rows[0].get("name") or "—"
        if cid:
            return (
                "Got it — I can update your clinic name.\n\n"
                f"Detected a single clinic on your account: **#{cid} {cname}**.\n"
                "Please tell me the **new name** you want, e.g.\n"
                f"`update clinic {cid} name to New Name` or simply `set clinic name to New Name`."
            )

    lines: List[str] = []
    for c in rows:
        cid = _extract_clinic_id(c) or "?"
        lines.append(f"• #{cid}: {c.get('name') or '—'}")
    return (
        "You have multiple clinics. Please specify which clinic to rename by **id** (or current name), "
        "and the new name. For example:\n"
        "- `update clinic 3 name to New Name`\n"
        "- `rename clinic from Old Name to New Name`\n\n"
        "Your clinics:\n" + "\n".join(lines)
    )

async def fastpath_update_clinic(msg: str, client_id_val: Optional[int]) -> Optional[str]:
    """
    Deterministic clinic-update handler.
    Returns a user-facing string if it handled the request, or None to let the rest of the pipeline proceed.
    """
    ai_dbg("clinic.fastpath.enter", {"client_id": client_id_val, "msg": msg})

    
    if client_id_val is None:
        return None

    text = (msg or "").strip()

    # Debug: check which patterns match
    ai_dbg("clinic.patterns.debug", {
        "text": text,
        "NAME_TO": bool(UPDATE_CLINIC_NAME_TO.search(text)),
        "NAME_POSSESSIVE": bool(UPDATE_CLINIC_NAME_POSSESSIVE_TO.search(text)),
        "NAME_OF_TO": bool(UPDATE_CLINIC_NAME_OF_TO.search(text)),
        "FREEFORM": bool(UPDATE_CLINIC_NAME_FREEFORM.search(text)),
    })

    # 1) Explicit: "update clinic <id> <field> to <value>"
    m = UPDATE_CLINIC_SIMPLE.search(text)
    if m:
        clinic_id = int(m.group(1))
        field     = m.group(2).lower().strip()
        value_raw = (m.group(3) or "").strip().strip('"\'')
        value     = _coerce_field(field, value_raw)
        return await _update_and_confirm(client_id_val, clinic_id, {field: value})

    # 2) Name-only: variations like "update the/my/our clinic name to X"
    # Check each pattern individually and extract the new name
    new_name = None
    
    if UPDATE_CLINIC_NAME_TO.search(text):
        new_name = UPDATE_CLINIC_NAME_TO.search(text).group(1).strip().strip('"\'')
    elif UPDATE_CLINIC_NAME_POSSESSIVE_TO.search(text):
        new_name = UPDATE_CLINIC_NAME_POSSESSIVE_TO.search(text).group(1).strip().strip('"\'')
    elif UPDATE_CLINIC_NAME_OF_TO.search(text):
        new_name = UPDATE_CLINIC_NAME_OF_TO.search(text).group(1).strip().strip('"\'')
    elif UPDATE_CLINIC_NAME_FREEFORM.search(text):
        new_name = UPDATE_CLINIC_NAME_FREEFORM.search(text).group(1).strip().strip('"\'')

    if new_name:
        # If free-form captured "to X" or "= X", strip the marker
        new_name = re.sub(r'^(?:to|=)\s+', '', new_name, flags=re.IGNORECASE)
        
        clinic_id = await _resolve_clinic_id_for_update(client_id_val, current_name=None)
        if clinic_id is None:
            return await _list_or_disambiguate(client_id_val)
        return await _update_and_confirm(client_id_val, clinic_id, {"name": new_name})

    # 3) Rename from→to: "rename clinic from A to B"
    m3 = UPDATE_CLINIC_RENAME_FROM_TO.search(text)
    if m3:
        current_name = m3.group(1).strip().strip('"\'')
        new_name     = m3.group(2).strip().strip('"\'')
        clinic_id = await _resolve_clinic_id_for_update(client_id_val, current_name=current_name)
        if clinic_id is None:
            # try to help disambiguate by listing matches of current name
            try:
                raw = await clinic_search_http.ainvoke({"client_id": client_id_val, "name": current_name, "limit": 5})
                data = json.loads(raw) if isinstance(raw, str) else raw
                rows = (data or {}).get("rows") or []
                if not rows:
                    return f"No clinic found with name '{current_name}'."
                if len(rows) > 1:
                    lines = [f"• #{c.get('id')}: {c.get('name') or '—'}" for c in rows]
                    return "Multiple clinics match that name. Please specify the clinic id:\n" + "\n".join(lines)
            except Exception:
                pass
            return "Clinic update failed: unable to resolve clinic."
        return await _update_and_confirm(client_id_val, clinic_id, {"name": new_name})

    # 4) Current/New pair: "Current Name: A  New Name: B"
    m4 = UPDATE_CLINIC_CURRENT_NEW.search(text)
    if m4:
        current_name = m4.group(1).strip().strip('"\'')
        new_name     = m4.group(2).strip().strip('"\'')
        clinic_id = await _resolve_clinic_id_for_update(client_id_val, current_name=current_name)
        if clinic_id is None:
            try:
                raw = await clinic_search_http.ainvoke({"client_id": client_id_val, "name": current_name, "limit": 5})
                data = json.loads(raw) if isinstance(raw, str) else raw
                rows = (data or {}).get("rows") or []
                if not rows:
                    return f"No clinic found with name '{current_name}'."
                if len(rows) > 1:
                    lines = [f"• #{c.get('id')}: {c.get('name') or '—'}" for c in rows]
                    return "Multiple clinics match that current name. Please specify a clinic id:\n" + "\n".join(lines)
            except Exception:
                pass
            return "Clinic update failed: unable to resolve clinic."
        return await _update_and_confirm(client_id_val, clinic_id, {"name": new_name})

    # 5) Intent detected but no value: e.g. "can you update the clinic name?"
    #    This is the case you hit — give a helpful, deterministic prompt.
    #    We detect intent by a loose read of "clinic name" + update verbs, but with no captured value.
    lowered = text.lower()
    if ("clinic name" in lowered) and any(v in lowered for v in ("update", "change", "edit", "set", "rename")):
        return await _list_or_disambiguate(client_id_val)

    return None