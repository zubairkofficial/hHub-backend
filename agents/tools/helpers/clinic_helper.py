import json
from typing import Optional, Any, Dict, List
from agents.tools.http_clinics import clinic_search_http
from agents.tools.helpers.logging import ai_dbg

def _extract_clinic_id(row: Dict[str, Any]) -> Optional[int]:
    for k in ("id", "clinic_id", "clinicId"):
        v = row.get(k)
        if isinstance(v, int) and v > 0:
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
    return None

async def _resolve_clinic_id_for_update(client_id_val: int, current_name: Optional[str]) -> Optional[int]:
    try:
        if current_name:
            q1 = {"client_id": client_id_val, "name": current_name.strip(), "limit": 5}
            ai_dbg("clinic.resolve.by_name", q1)
            raw = await clinic_search_http.ainvoke(q1)
            data = json.loads(raw) if isinstance(raw, str) else raw
            rows: List[Dict[str, Any]] = (data or {}).get("rows") or []
            exact = [r for r in rows if str(r.get("name") or "").strip().lower() == current_name.strip().lower()]
            if len(exact) == 1:
                cid = _extract_clinic_id(exact[0])
                if cid:
                    return cid
            if len(exact) > 1:
                return None
    except Exception as e:
        ai_dbg("clinic.resolve.by_name.error", repr(e))

    try:
        q2 = {"client_id": client_id_val, "limit": 2}
        ai_dbg("clinic.resolve.single", q2)
        raw = await clinic_search_http.ainvoke(q2)
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows: List[Dict[str, Any]] = (data or {}).get("rows") or []
        if len(rows) == 1:
            cid = _extract_clinic_id(rows[0])
            if cid:
                return cid
        if rows:
            sample = {k: rows[0].get(k) for k in list(rows[0].keys())[:6]}
            ai_dbg("clinic.resolve.single.sample_row", sample)
    except Exception as e:
        ai_dbg("clinic.resolve.single.error", repr(e))

    return None
