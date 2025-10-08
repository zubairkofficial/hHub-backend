from __future__ import annotations
import json
from typing import Optional, Dict, Any
import os
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import tool

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
LARAVEL_API_BASE = os.getenv("LARAVEL_API_BASE", f"{API_URL.rstrip('/')}/api")
AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

class UpdateLeadArgs(BaseModel):
    """Arguments for updating a lead in Laravel CRM."""
    # Identify the lead
    lead_id: Optional[int] = None
    client_id: Optional[int] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    name_hint: Optional[str] = None

    # Fields to update (only provided ones will be sent)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_number: Optional[str] = None
    email_new: Optional[str] = None
    status: Optional[str] = None          # e.g., new|open|won|lost
    lead_source: Optional[str] = None
    description: Optional[str] = None
    potential_score: Optional[int] = Field(None, ge=0, le=100)

async def _lookup_lead_id(
    client: httpx.AsyncClient,
    client_id: int,
    phone: Optional[str],
    email: Optional[str],
    name_hint: Optional[str],
) -> Optional[int]:
    """Try to find a lead id via Laravel lookup endpoint."""
    params: Dict[str, Any] = {"client_id": client_id}
    if phone:     params["phone"] = phone
    if email:     params["email"] = email
    if name_hint: params["name"]  = name_hint

    url = f"{LARAVEL_API_BASE}/leads/lookup"
    dlog("lead.lookup.request", {"url": url, "params": params})

    r = await client.get(url, params=params, headers={"Accept": "application/json"}, timeout=30.0)
    dlog("lead.lookup.response", {"status": r.status_code, "text": r.text[:2000]})

    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
        data = r.json() or {}
        if data.get("ok") and data.get("lead"):
            try:
                return int(data["lead"]["id"])
            except Exception:
                return None
    return None

def _build_update_payload(args: UpdateLeadArgs) -> Dict[str, Any]:
    """Build PATCH payload with only provided fields."""
    payload: Dict[str, Any] = {}
    if args.first_name is not None:      payload["first_name"] = args.first_name
    if args.last_name is not None:       payload["last_name"]  = args.last_name
    if args.contact_number is not None:  payload["contact_number"] = args.contact_number
    if args.email_new is not None:       payload["email"] = args.email_new
    if args.status is not None:          payload["status"] = args.status
    if args.lead_source is not None:     payload["lead_source"] = args.lead_source
    if args.description is not None:     payload["description"] = args.description
    if args.potential_score is not None: payload["potential_score"] = args.potential_score
    return payload

async def _patch_with_fallback(client: httpx.AsyncClient, url: str, json_payload: Dict[str, Any]) -> httpx.Response:
    """Try PATCH; on network/method issues, fallback to POST + _method=PATCH."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # 1) try PATCH
    try:
        dlog("tool.update_lead.patch.request", {"url": url, "payload": json_payload})
        resp = await client.patch(url, json=json_payload, headers=headers, timeout=40.0)
        dlog("tool.update_lead.patch.response", {"status": resp.status_code, "text": resp.text[:2000]})
        return resp
    except Exception as e:
        dlog("tool.update_lead.patch.exception", {"type": e.__class__.__name__, "repr": repr(e)})

    # 2) try POST + _method=PATCH (Laravel method spoof)
    try:
        spoof_payload = {"_method": "PATCH", **json_payload}
        dlog("tool.update_lead.spoof.request", {"url": url, "payload": spoof_payload})
        resp = await client.post(url, json=spoof_payload, headers=headers, timeout=40.0)
        dlog("tool.update_lead.spoof.response", {"status": resp.status_code, "text": resp.text[:2000]})
        return resp
    except Exception as e:
        dlog("tool.update_lead.spoof.exception", {"type": e.__class__.__name__, "repr": repr(e)})
        # Raise so caller reports FAIL with proper message
        raise

@tool("update_lead", args_schema=UpdateLeadArgs)
async def update_lead(
    lead_id: Optional[int] = None,
    client_id: Optional[int] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    name_hint: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    contact_number: Optional[str] = None,
    email_new: Optional[str] = None,
    status: Optional[str] = None,
    lead_source: Optional[str] = None,
    description: Optional[str] = None,
    potential_score: Optional[int] = None,
) -> str:
    """
    Update a Laravel CRM lead.

    Identification:
      - Provide `lead_id`, OR
      - Provide `client_id` plus one of: `phone`, `email`, or `name_hint`.

    Updates only the fields you pass (first_name, last_name, contact_number, email_new, status,
    lead_source, description, potential_score). Returns a short status string:
    'UPDATE:OK:{...}' on success or 'UPDATE:FAIL:...' on failure.
    """
    dlog("tool.update_lead.args", {
        "lead_id": lead_id, "client_id": client_id, "phone": phone, "email": email, "name_hint": name_hint,
        "first_name": first_name, "last_name": last_name, "contact_number": contact_number, "email_new": email_new,
        "status": status, "lead_source": lead_source, "description": description, "potential_score": potential_score
    })

    if not lead_id and not client_id:
        return "UPDATE:FAIL:Need lead_id or client_id + one of phone/email/name_hint"

    async with httpx.AsyncClient() as client:
        lid = lead_id
        if lid is None:
            try:
                lid = await _lookup_lead_id(client, int(client_id), phone, email, name_hint)
            except Exception as e:
                dlog("tool.update_lead.lookup.exception", {"type": e.__class__.__name__, "repr": repr(e)})
                lid = None
            if lid is None:
                return "UPDATE:FAIL:Lead not found with given criteria"

        payload = _build_update_payload(UpdateLeadArgs(
            first_name=first_name, last_name=last_name, contact_number=contact_number,
            email_new=email_new, status=status, lead_source=lead_source,
            description=description, potential_score=potential_score
        ))
        if not payload:
            return "UPDATE:FAIL:No fields to update"

        url = f"{LARAVEL_API_BASE}/leads/{lid}"
        try:
            r = await _patch_with_fallback(client, url, payload)
            ok = 200 <= r.status_code < 300
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text}
            return f"UPDATE:{'OK' if ok else 'FAIL'}:{json.dumps(data, ensure_ascii=False)}"
        except Exception as e:
            return f"UPDATE:FAIL:exception:{e.__class__.__name__}:{repr(e)}"
