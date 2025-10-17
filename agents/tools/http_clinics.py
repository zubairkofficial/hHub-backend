# agents/tools/http_clinics.py
from __future__ import annotations
import os, json
from typing import Optional, Dict, Any, List
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

# -------------------- Args Schemas (define FIRST) --------------------
class ClinicGetArgs(BaseModel):
    client_id: int
    clinic_id: int

class ClinicSearchArgs(BaseModel):
    client_id: int
    name: Optional[str] = None
    city_id: Optional[int] = None
    state_id: Optional[int] = None
    is_active: Optional[bool] = None
    limit: int = Field(default=20, ge=1, le=200)

class ClinicUpdateArgs(BaseModel):
    client_id: int
    clinic_id: int
    # updatable fields
    name: Optional[str] = None
    address: Optional[str] = None
    address2: Optional[str] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    zip_code: Optional[str] = None
    is_active: Optional[bool] = None
    review_url: Optional[str] = None
    tw_content_sid_appt: Optional[str] = None
    tw_content_sid_review: Optional[str] = None
    tw_content_sid_nurture: Optional[str] = None
    google_review_url: Optional[str] = None

# -------------------- Tools --------------------
@tool("clinic_get_http", args_schema=ClinicGetArgs)
async def clinic_get_http(client_id: int, clinic_id: int) -> str:
    """
    Fetch a single clinic by id for a given client_id via Laravel API.
    Returns JSON {ok, clinic} or {ok:false,error}.
    """
    url = f"{LARAVEL_API_BASE}/clinics/{clinic_id}"
    dlog("clinic.get.request", {"url": url, "params": {"client_id": client_id}})
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(url, params={"client_id": client_id}, headers={"Accept": "application/json"})
        except Exception as e:
            return json.dumps({"ok": False, "error": f"http_error:{e.__class__.__name__}:{repr(e)}"}, ensure_ascii=False)

    if r.status_code == 404:
        return json.dumps({"ok": False, "error": "not_found"}, ensure_ascii=False)
    if r.status_code >= 400:
        return json.dumps({"ok": False, "error": f"http_{r.status_code}", "body": r.text[:1000]}, ensure_ascii=False)

    try:
        data = r.json()
    except Exception:
        return json.dumps({"ok": False, "error": "bad_json", "body": r.text[:1000]}, ensure_ascii=False)

    if isinstance(data, dict) and ("ok" in data or "clinic" in data):
        return json.dumps(data, ensure_ascii=False)
    return json.dumps({"ok": True, "clinic": data}, ensure_ascii=False)

@tool("clinic_search_http", args_schema=ClinicSearchArgs)
async def clinic_search_http(client_id: int,
                             name: Optional[str] = None,
                             city_id: Optional[int] = None,
                             state_id: Optional[int] = None,
                             is_active: Optional[bool] = None,
                             limit: int = 20) -> str:
    """
    Search clinics for a client_id (by optional name/city/state/is_active). Returns {ok, rows}.
    """
    url = f"{LARAVEL_API_BASE}/clinics"
    params: Dict[str, Any] = {"client_id": client_id, "limit": limit}
    if name: params["name"] = name
    if city_id is not None: params["city_id"] = city_id
    if state_id is not None: params["state_id"] = state_id
    if is_active is not None: params["is_active"] = int(bool(is_active))

    dlog("clinic.search.request", {"url": url, "params": params})
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(url, params=params, headers={"Accept": "application/json"})
        except Exception as e:
            return json.dumps({"ok": False, "error": f"http_error:{e.__class__.__name__}:{repr(e)}"}, ensure_ascii=False)

    if r.status_code >= 400:
        return json.dumps({"ok": False, "error": f"http_{r.status_code}", "body": r.text[:1000]}, ensure_ascii=False)

    try:
        data = r.json()
    except Exception:
        return json.dumps({"ok": False, "error": "bad_json", "body": r.text[:1000]}, ensure_ascii=False)

    # ---- Normalize to rows (handles {ok:true, rows:[…]} from your Laravel controller) ----
    rows: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        if "rows" in data and isinstance(data["rows"], list):
            rows = data["rows"]
        elif "data" in data and isinstance(data["data"], list):
            rows = data["data"]
        elif "clinic" in data and isinstance(data["clinic"], dict):
            rows = [data["clinic"]]
        else:
            rows = [data]
    elif isinstance(data, list):
        rows = data
    else:
        rows = [data]

    # ---- Ensure every row has an 'id' (fallbacks: clinic_id, clinicId) ----
    norm_rows: List[Dict[str, Any]] = []
    for r in rows:
        if isinstance(r, dict) and "id" not in r:
            if "clinic_id" in r:
                r["id"] = r["clinic_id"]
            elif "clinicId" in r:
                r["id"] = r["clinicId"]
        norm_rows.append(r)

    return json.dumps({"ok": True, "rows": norm_rows}, ensure_ascii=False)

def _build_clinic_update_payload(a: ClinicUpdateArgs) -> Dict[str, Any]:
    p: Dict[str, Any] = {}
    for fld in ("name","address","address2","country_id","state_id","city_id","zip_code",
                "review_url","tw_content_sid_appt","tw_content_sid_review","tw_content_sid_nurture",
                "google_review_url"):
        val = getattr(a, fld)
        if val is not None:
            p[fld] = val
    if a.is_active is not None:
        p["is_active"] = int(bool(a.is_active))  # many Laravel setups store 0/1
    return p

async def _patch_or_spoof(url: str, payload: Dict[str, Any]) -> httpx.Response:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=40.0) as client:
        try:
            dlog("clinic.update.patch.request", {"url": url, "payload": payload})
            r = await client.patch(url, json=payload, headers=headers)
            dlog("clinic.update.patch.response", {"status": r.status_code, "text": r.text[:1000]})
            return r
        except Exception as e:
            dlog("clinic.update.patch.exception", {"type": e.__class__.__name__, "repr": repr(e)})
        try:
            spoof = {"_method": "PATCH", **payload}
            dlog("clinic.update.spoof.request", {"url": url, "payload": spoof})
            r = await client.post(url, json=spoof, headers=headers)
            dlog("clinic.update.spoof.response", {"status": r.status_code, "text": r.text[:1000]})
            return r
        except Exception as e:
            dlog("clinic.update.spoof.exception", {"type": e.__class__.__name__, "repr": repr(e)})
            raise

@tool("clinic_update", args_schema=ClinicUpdateArgs)
async def clinic_update(client_id: int, clinic_id: int, **updates) -> str:
    """
    Update a Clinic (PATCH) for a given client_id/clinic_id. Only provided fields are updated.
    Returns 'CLINIC_UPDATE:OK:{...}' or 'CLINIC_UPDATE:FAIL:...'.
    """
    args = ClinicUpdateArgs(client_id=client_id, clinic_id=clinic_id, **updates)
    payload = _build_clinic_update_payload(args)
    if not payload:
        return "CLINIC_UPDATE:FAIL:No fields to update"

    # ✅ include client_id in query string for Laravel controller
    url = f"{LARAVEL_API_BASE}/clinics/{args.clinic_id}?client_id={args.client_id}"

    try:
        r = await _patch_or_spoof(url, payload)
        ok = 200 <= r.status_code < 300
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:1000]}
        return f"CLINIC_UPDATE:{'OK' if ok else 'FAIL'}:{json.dumps(data, ensure_ascii=False)}"
    except Exception as e:
        return f"CLINIC_UPDATE:FAIL:exception:{e.__class__.__name__}:{repr(e)}"
