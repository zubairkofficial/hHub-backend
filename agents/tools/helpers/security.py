# agents/tools/helpers/security.py
import json
from typing import Any, Dict, Optional
from helper.get_data import get_client_data

# Sticky caches
_CLIENT_ID_CACHE: Dict[str, int] = {}
_ROLE_CACHE: Dict[str, Dict[str, Any]] = {}


def json_dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)


def remember_client_id(user_id: str, client_id: Optional[int]) -> None:
    """Allow callers to seed/override the cache for this user."""
    if client_id is not None:
        _CLIENT_ID_CACHE[str(user_id)] = int(client_id)


async def get_client_id(user_id: str) -> Optional[int]:
    """
    Resolve client_id for the given user:
    1) Return from in-memory cache if present.
    2) Ask get_client_data(user_id) and probe common paths.
    NOTE: get_client_data() returns clinics['data'] (already the inner data),
    so we probe both non-prefixed and 'data'-prefixed paths.
    """
    # 1) cache
    if str(user_id) in _CLIENT_ID_CACHE:
        print(f"[AI-DBG] client_id.source :: {json.dumps({'user_id': user_id, 'from': 'cache', 'client_id': _CLIENT_ID_CACHE[str(user_id)]})}")
        return _CLIENT_ID_CACHE[str(user_id)]

    try:
        raw = await get_client_data(int(user_id))
        data = raw if isinstance(raw, dict) else {}
        print(f"[AI-DBG] client_id.source :: {json.dumps({'user_id': user_id, 'from': 'get_client_data', 'type': type(raw).__name__})}")

        # helper to walk dict/list by path
        def deep_get(d: Any, path: tuple) -> Optional[Any]:
            cur = d
            for k in path:
                if isinstance(k, int):
                    if isinstance(cur, list) and 0 <= k < len(cur):
                        cur = cur[k]
                    else:
                        return None
                else:
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(k)
                if cur is None:
                    return None
            return cur

        # Because get_client_data returns clinics['data'], FIRST check non-prefixed paths.
        candidate_paths = [
            # primary (your real structure)
            ("logged_in_user_whose_asked_questions_or_chat", "client_id"),
            # fallback to first client id in the list
            ("clients", 0, "id"),

            # Other common shapes (non-prefixed)
            ("client_id",),
            ("client", "client_id"),
            ("client", "id"),
            ("user", "client_id"),
            ("user", "client", "id"),
            ("profile", "client_id"),
            ("session", "client_id"),
            ("auth", "client_id"),
            ("clientId",),
            ("user", "clientId"),

            # Prefixed variants
            ("data", "logged_in_user_whose_asked_questions_or_chat", "client_id"),
            ("data", "clients", 0, "id"),
            ("data", "client_id"),
            ("data", "client", "client_id"),
            ("data", "client", "id"),
            ("data", "user", "client_id"),
            ("data", "user", "client", "id"),
            ("data", "clientId"),
        ]

        for p in candidate_paths:
            v = deep_get(data, p)
            if isinstance(v, int) and v > 0:
                print(f"[AI-DBG] client_id.found :: {json.dumps({'user_id': user_id, 'path': '→'.join(map(str, p)), 'client_id': v})}")
                _CLIENT_ID_CACHE[str(user_id)] = int(v)
                return int(v)

        print(f"[AI-DBG] client_id.missing :: {json.dumps({'user_id': user_id, 'reason': 'no known path contained client_id'})}")
        return None

    except Exception as e:
        print(f"[AI-DBG] client_id.error :: {json.dumps({'user_id': user_id, 'error': repr(e)})}")
        return None


# ---------- Role helpers (NEW) ----------
def _normalize_role(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    # common variants
    if s in ("super admin", "super_admin", "superadmin", "admin-super", "sa"):
        return "super_admin"
    if s in ("admin", "administrator"):
        return "admin"
    if s in ("client", "customer", "user"):
        return "client"
    return s


async def get_user_role_info(user_id: str) -> Dict[str, Any]:
    """
    Returns a dict like {"role": <normalized string or None>, "is_super_admin": <bool or None>, "raw": <original dict>}.
    Cached per user_id.
    """
    uid = str(user_id)
    if uid in _ROLE_CACHE:
        return _ROLE_CACHE[uid]

    try:
        raw = await get_client_data(int(user_id))
        data = raw if isinstance(raw, dict) else {}

        def deep_get(d: Any, path: tuple) -> Optional[Any]:
            cur = d
            for k in path:
                if isinstance(k, int):
                    if isinstance(cur, list) and 0 <= k < len(cur):
                        cur = cur[k]
                    else:
                        return None
                else:
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(k)
                if cur is None:
                    return None
            return cur

        # likely locations for role/is_super_admin
        role_paths = [
            ("logged_in_user_whose_asked_questions_or_chat", "role"),
            ("user", "role"),
            ("profile", "role"),
            ("role",),
            ("data", "logged_in_user_whose_asked_questions_or_chat", "role"),
            ("data", "user", "role"),
            ("data", "role"),
        ]
        flag_paths = [
            ("logged_in_user_whose_asked_questions_or_chat", "is_super_admin"),
            ("user", "is_super_admin"),
            ("is_super_admin",),
            ("data", "logged_in_user_whose_asked_questions_or_chat", "is_super_admin"),
            ("data", "user", "is_super_admin"),
            ("data", "is_super_admin"),
        ]

        role_val = None
        for p in role_paths:
            v = deep_get(data, p)
            if v is not None:
                role_val = v
                break

        flag_val = None
        for p in flag_paths:
            v = deep_get(data, p)
            if v is not None:
                flag_val = v
                break

        norm_role = _normalize_role(role_val)
        is_sa = None

        # resolve boolean super admin flag from either explicit flag or role text
        if isinstance(flag_val, bool):
            is_sa = flag_val
        elif isinstance(flag_val, (int, str)):
            is_sa = str(flag_val).strip().lower() in ("1", "true", "yes", "y")

        if is_sa is None:
            is_sa = (norm_role == "super_admin")

        info = {"role": norm_role, "is_super_admin": bool(is_sa), "raw": {"role": role_val, "flag": flag_val}}
        _ROLE_CACHE[uid] = info
        return info

    except Exception as e:
        print(f"[AI-DBG] role.error :: {json.dumps({'user_id': user_id, 'error': repr(e)})}")
        info = {"role": None, "is_super_admin": False, "raw": {}}
        _ROLE_CACHE[uid] = info
        return info


async def is_super_admin(user_id: str) -> bool:
    info = await get_user_role_info(user_id)
    return bool(info.get("is_super_admin"))


def enforce_client_id(tool_name: str, args: Dict[str, Any], client_id_val: Optional[int]) -> Dict[str, Any]:
    a = dict(args or {})

    if tool_name in (
        "lead_get","lead_search","update_lead","lead_get_http","lead_lookup_http",
        "clinic_get_http","clinic_search_http","clinic_update","appointment_slots","appointment_create"  # both need client_id in the args
    ):
        if client_id_val is None:
            raise ValueError("Missing client_id for secure operation.")
        a["client_id"] = int(client_id_val)

    elif tool_name == "sql_select" and a.get("table") in ("client_leads", "clinics"):
        where = dict(a.get("where") or {})
        if client_id_val is None:
            raise ValueError("Missing client_id for secure query.")
        where["client_id"] = int(client_id_val)
        a["where"] = where

    # NOTE: we don't enforce role here because we don't have user_id in this function.
    # Role checks for service updates are performed in the orchestrator and (optionally) in the tool implementation.

    return a
