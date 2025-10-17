from __future__ import annotations
import os, json, re, asyncio
from typing import Optional, Dict, Any, Callable, Awaitable
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
LARAVEL_API_BASE = os.getenv("LARAVEL_API_BASE", f"{API_URL.rstrip('/')}/api")
AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"

def dlog(tag: str, payload: Dict[str, Any]):
    if AI_DEBUG:
        try:
            print(f"[AI-DBG] {tag} :: {json.dumps(payload, ensure_ascii=False, default=str)}")
        except Exception:
            print(f"[AI-DBG] {tag} :: {payload}")

# -------------------- helpers --------------------
def _normalize_phone(p: Optional[str]) -> Optional[str]:
    if not p:
        return p
    p = p.strip()
    if p.startswith("+"):
        return "+" + re.sub(r"\D", "", p[1:])
    return re.sub(r"\D", "", p)

async def _request_with_retries(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = 3,
    backoff_base: float = 0.5,
) -> httpx.Response:
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retries + 1):
            try:
                if method == "GET":
                    r = await client.get(url, params=params, headers=headers)
                elif method == "PATCH":
                    r = await client.patch(url, json=json_body, headers=headers)
                elif method == "POST":
                    r = await client.post(url, json=json_body, headers=headers)
                else:
                    raise ValueError(f"Unsupported method {method}")
                return r
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                dlog("http.retry.timeout", {"url": url, "attempt": attempt, "err": repr(e)})
                if attempt == retries:
                    raise
                await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))
            except httpx.HTTPError as e:
                dlog("http.retry.other", {"url": url, "attempt": attempt, "err": repr(e)})
                if attempt == retries:
                    raise
                await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))

def _safe_body(r: httpx.Response) -> Dict[str, Any]:
    try:
        return r.json()
    except Exception:
        return {"text": r.text[:1000]}

def _safe_json(r: httpx.Response) -> Dict[str, Any]:
    try:
        data = r.json()
        if isinstance(data, dict):
            if "ok" not in data:
                data["ok"] = (200 <= r.status_code < 300)
            return data
        return {"ok": (200 <= r.status_code < 300), "lead": data}
    except Exception:
        return {"ok": (200 <= r.status_code < 300), "raw": r.text[:2000], "status": r.status_code}

# -------------------- args_schemas --------------------
class LeadGetArgs(BaseModel):
    client_id: int
    lead_id: int

class LeadLookupArgs(BaseModel):
    client_id: int
    phone: Optional[str] = None
    email: Optional[str] = None
    limit: Optional[int] = 10

class LeadUpdateArgs(BaseModel):
    client_id: int
    lead_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    lead_source: Optional[str] = None
    description: Optional[str] = None
    potential_score: Optional[int] = Field(None, ge=0, le=100)

# -------------------- async impls --------------------
async def _lead_get_http_impl(*, client_id: int, lead_id: int) -> str:
    """
    GET /api/leads/{id}?client_id=10
    Returns {ok:true, lead:{...}} or {ok:false,error}
    """
    url = f"{LARAVEL_API_BASE}/leads/{lead_id}"
    params = {"client_id": client_id}
    dlog("lead.get.request", {"url": url, "params": params})
    try:
        r = await _request_with_retries("GET", url, params=params, headers={"Accept": "application/json"})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"http_error:{e.__class__.__name__}:{repr(e)}"}, ensure_ascii=False)

    if r.status_code >= 400:
        body = _safe_body(r)
        return json.dumps({"ok": False, "error": f"http_{r.status_code}", "body": body}, ensure_ascii=False)

    data = _safe_json(r)
    return json.dumps(data if isinstance(data, dict) else {"ok": True, "lead": data}, ensure_ascii=False)

async def _lead_lookup_http_impl(*, client_id: int, phone: Optional[str] = None, email: Optional[str] = None, limit: int = 10) -> str:
    """
    GET /api/leads/lookup?client_id=10&phone=...&email=...&limit=10
    Returns {ok:true, rows:[...]} or {ok:true, lead:{...}}
    """
    url = f"{LARAVEL_API_BASE}/leads/lookup"
    params: Dict[str, Any] = {"client_id": client_id, "limit": max(1, min(50, limit))}
    if phone:
        params["phone"] = _normalize_phone(phone)
    if email:
        params["email"] = email.strip()

    dlog("lead.lookup.request", {"url": url, "params": params})
    try:
        r = await _request_with_retries("GET", url, params=params, headers={"Accept": "application/json"})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"http_error:{e.__class__.__name__}:{repr(e)}"}, ensure_ascii=False)

    if r.status_code >= 400:
        body = _safe_body(r)
        return json.dumps({"ok": False, "error": f"http_{r.status_code}", "body": body}, ensure_ascii=False)

    data = _safe_json(r)
    if isinstance(data, dict) and ("rows" in data or "lead" in data or "ok" in data):
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, list):
        return json.dumps({"ok": True, "rows": data}, ensure_ascii=False)
    return json.dumps({"ok": True, "lead": data}, ensure_ascii=False)

async def _lead_update_http_impl(
    *,
    client_id: int,
    lead_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    contact_number: Optional[str] = None,
    email: Optional[str] = None,
    status: Optional[str] = None,
    lead_source: Optional[str] = None,
    description: Optional[str] = None,
    potential_score: Optional[int] = None,
) -> str:
    """
    PATCH /api/leads/{id}
    Fallback: POST with _method=PATCH if PATCH fails.
    Returns {ok:true, lead:{...}} or {ok:false,error}
    """
    url = f"{LARAVEL_API_BASE}/leads/{lead_id}"
    payload: Dict[str, Any] = {
        k: v for k, v in dict(
            first_name=first_name,
            last_name=last_name,
            contact_number=_normalize_phone(contact_number) if contact_number else None,
            email=email.strip() if email else None,
            status=status,
            lead_source=lead_source,
            description=description,
            potential_score=potential_score,
            client_id=client_id,
        ).items() if v is not None
    }
    if not payload:
        return json.dumps({"ok": False, "error": "no_fields"}, ensure_ascii=False)

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    dlog("lead.update.request", {"url": url, "payload": payload})
    try:
        r = await _request_with_retries("PATCH", url, json_body=payload, headers=headers)
        if r.status_code >= 500:
            raise httpx.HTTPError(f"server_{r.status_code}")
    except Exception:
        try:
            spoof = {"_method": "PATCH", **payload}
            r = await _request_with_retries("POST", url, json_body=spoof, headers=headers)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"http_error:{e.__class__.__name__}:{repr(e)}"}, ensure_ascii=False)

    data = _safe_json(r)
    return json.dumps(data, ensure_ascii=False)

# -------------------- build tools (no decorators) --------------------
def _mk_tool(
    name: str,
    schema: type[BaseModel],
    func: Callable[..., Awaitable[str]],
    description: str,
) -> StructuredTool:
    return StructuredTool.from_function(
        name=name,
        args_schema=schema,
        description=description,
        func=func,        # async ok
        coroutine=func,   # explicit for older versions
    )

lead_get_http = _mk_tool(
    "lead_get_http",
    LeadGetArgs,
    _lead_get_http_impl,
    "Fetch a lead by ID. GET /api/leads/{id}?client_id=... → {ok, lead}",
)

lead_lookup_http = _mk_tool(
    "lead_lookup_http",
    LeadLookupArgs,
    _lead_lookup_http_impl,
    "Lookup leads by phone/email. GET /api/leads/lookup → {ok, rows|lead}",
)

lead_update_http = _mk_tool(
    "lead_update_http",
    LeadUpdateArgs,
    _lead_update_http_impl,
    "Update a lead fields by ID. PATCH /api/leads/{id} (Laravel) → {ok,...}",
)
