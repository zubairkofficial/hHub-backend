# agents/helpers/logging.py
from __future__ import annotations
import os, time, re, json, threading
from contextlib import contextmanager
from typing import Any, Dict, Optional

# --- config ---
_AI_DEBUG = os.getenv("AI_DEBUG", "0") == "1"
_MAX_LEN  = int(os.getenv("AI_LOG_MAXLEN", "1000"))  # truncate long payloads

# --- thread-local context (non-async; works fine for FastAPI worker threads) ---
_tls = threading.local()
def _get_ctx() -> Dict[str, Any]:
    ctx = getattr(_tls, "ctx", None)
    if ctx is None:
        ctx = {}
        _tls.ctx = ctx
    return ctx

def set_log_context(**kv: Any) -> None:
    """
    set_log_context(user_id=..., chat_id=..., client_id=...)
    """
    _get_ctx().update({k: v for k, v in kv.items() if v is not None})

def clear_log_context() -> None:
    _get_ctx().clear()

# --- redaction (emails/phones) ---
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{6,}\d")
def _redact(s: str) -> str:
    s = _EMAIL_RE.sub("[redacted_email]", s)
    s = _PHONE_RE.sub("[redacted_phone]", s)
    return s

def _to_json(o: Any) -> str:
    try:
        s = json.dumps(o, ensure_ascii=False, default=str)
    except Exception:
        try:
            s = str(o)
        except Exception:
            s = "<unserializable>"
    if len(s) > _MAX_LEN:
        s = s[:_MAX_LEN] + "…[truncated]"
    return _redact(s)

def _fmt_line(level: str, tag: str, payload: Any) -> str:
    ctx = _get_ctx()
    ctx_part = f" ctx={_to_json(ctx)}" if ctx else ""
    return f"[AI-DBG] {level.upper()} {tag} :: {_to_json(payload)}{ctx_part}"

# --- public log fns ---
def ai_dbg(tag: str, payload: Any = "") -> None:
    """Debug log (prints only if AI_DEBUG=1)."""
    if not _AI_DEBUG:
        return
    try:
        print(_fmt_line("debug", tag, payload))
    except Exception:
        pass

def ai_info(tag: str, payload: Any = "") -> None:
    """Info log (always prints)."""
    try:
        print(_fmt_line("info", tag, payload))
    except Exception:
        pass

def ai_warn(tag: str, payload: Any = "") -> None:
    """Warning log (always prints)."""
    try:
        print(_fmt_line("warn", tag, payload))
    except Exception:
        pass

def ai_err(tag: str, payload: Any = "") -> None:
    """Error log (always prints)."""
    try:
        print(_fmt_line("error", tag, payload))
    except Exception:
        pass

# --- timing spans ---
@contextmanager
def ai_span(tag: str, payload: Any = ""):
    """
    with ai_span("clinic.update", {"clinic_id": 3}):
        ... code ...
    """
    start = time.perf_counter()
    ai_dbg(f"{tag}.start", payload)
    try:
        yield
        dur = (time.perf_counter() - start) * 1000.0
        ai_dbg(f"{tag}.end", {"ms": round(dur, 2)})
    except Exception as e:
        dur = (time.perf_counter() - start) * 1000.0
        ai_err(f"{tag}.error", {"ms": round(dur, 2), "exc": f"{e.__class__.__name__}: {e}"})
        raise

# --- helpers for HTTP logs (request/response) ---
def log_http_request(tag: str, url: str, method: str = "GET", params: Optional[Dict[str, Any]] = None, body: Any = None):
    ai_dbg(f"{tag}.request", {"method": method, "url": url, "params": params or {}, "body": body})

def log_http_response(tag: str, status: int, text: Optional[str] = None, json_body: Any = None):
    payload: Dict[str, Any] = {"status": status}
    if json_body is not None:
        payload["json"] = json_body
    elif text:
        payload["text"] = text[:_MAX_LEN] + ("…[truncated]" if text and len(text) > _MAX_LEN else "")
    ai_dbg(f"{tag}.response", payload)
