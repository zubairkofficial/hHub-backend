# agents/tools/helpers/error_handling.py
import os
import json
import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")

def _json(o):
    return json.dumps(o, ensure_ascii=False, default=str)

async def http_get(url: str, params: dict = None, timeout: float = 15.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.get(url, params=params or {})
            try:
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                return _handle_http_error(r)
        except Exception as e:
            return {"ok": False, "error": f"Unable to reach server: {e}"}

async def http_post(url: str, json_body: dict = None, timeout: float = 15.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(url, json=json_body or {})
            try:
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                return _handle_http_error(r)
        except Exception as e:
            return {"ok": False, "error": f"Connection failed: {e}"}

async def http_patch(url: str, json_body: dict = None, timeout: float = 15.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.patch(url, json=json_body or {})
            try:
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                return _handle_http_error(r)
        except Exception as e:
            return {"ok": False, "error": f"Connection failed: {e}"}

async def http_delete(url: str, timeout: float = 15.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.delete(url)
            try:
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                return _handle_http_error(r)
        except Exception as e:
            return {"ok": False, "error": f"Connection failed: {e}"}


def _handle_http_error(r: httpx.Response):
    """Return human-friendly structured error message."""
    status = r.status_code
    try:
        body = r.json()
        msg = _format_body_error(body)
    except Exception:
        msg = r.text or r.reason_phrase or f"HTTP {status}"

    # Human-readable fallbacks
    if not msg or msg.strip() == "":
        msg = {
            400: "Invalid request sent to the server.",
            401: "You are not authorized to perform this action.",
            403: "Access denied — please contact admin.",
            404: "Requested resource not found.",
            409: "Conflict: resource already exists or is locked.",
            422: "Validation failed. Please check your input data.",
            500: "Server error — please try again later.",
        }.get(status, f"Unexpected error (HTTP {status})")

    return {"ok": False, "status_code": status, "error": msg}


def _format_body_error(body):
    """Extract readable error from a JSON body."""
    if not body:
        return "Empty response body"
    if isinstance(body, dict):
        if body.get("error"):
            return str(body["error"])
        if body.get("message"):
            return str(body["message"])
        if "errors" in body:
            errs = body["errors"]
            if isinstance(errs, dict):
                for k, v in errs.items():
                    if isinstance(v, list) and v:
                        return f"{k.capitalize()}: {v[0]}"
                    elif v:
                        return f"{k.capitalize()}: {v}"
            elif isinstance(errs, list) and errs:
                return str(errs[0])
        return json.dumps(body, ensure_ascii=False)[:300]
    return str(body)
