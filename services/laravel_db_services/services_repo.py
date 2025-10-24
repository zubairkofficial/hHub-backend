# services/laravel_db_services/services_repo.py
from typing import List, Dict, Optional
from sqlalchemy import text
from helper.laravel_db import laravel_session

# ---- READS ----
async def service_list(limit: int = 50, offset: int = 0) -> List[Dict]:
    q = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE deleted_at IS NULL
        ORDER BY name ASC
        LIMIT :limit OFFSET :offset
    """)
    async with laravel_session() as s:
        rows = (await s.execute(q, {"limit": int(limit), "offset": int(offset)})).mappings().all()
        return [dict(r) for r in rows]

async def service_get(service_id: int) -> Optional[Dict]:
    q = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE id = :sid AND deleted_at IS NULL
        LIMIT 1
    """)
    async with laravel_session() as s:
        row = (await s.execute(q, {"sid": int(service_id)})).mappings().first()
        return dict(row) if row else None

async def service_search(qstr: str, limit: int = 25) -> List[Dict]:
    q = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE deleted_at IS NULL
          AND (name LIKE :q OR description LIKE :q)
        ORDER BY name ASC
        LIMIT :limit
    """)
    async with laravel_session() as s:
        rows = (await s.execute(q, {"q": f"%{qstr.strip()}%", "limit": int(limit)})).mappings().all()
        return [dict(r) for r in rows]

# ---- WRITE (guarded) ----
async def service_update(service_id: int, *, name: Optional[str] = None,
                         description: Optional[str] = None,
                         for_report: Optional[int] = None) -> Dict:
    """
    Updates allowed fields on services. Returns {"ok": True, "updated": <count>, "service": <row or None>}
    """
    fields = {}
    if name is not None:
        fields["name"] = name.strip()
    if description is not None:
        fields["description"] = description.strip()
    if for_report is not None:
        fields["for_report"] = int(for_report)

    if not fields:
        return {"ok": False, "error": "No fields to update"}

    set_frag = ", ".join([f"`{k}` = :{k}" for k in fields.keys()])
    params = dict(fields)
    params["sid"] = int(service_id)

    q_upd = text(f"""
        UPDATE services
        SET {set_frag}
        WHERE id = :sid AND deleted_at IS NULL
        LIMIT 1
    """)
    q_get = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE id = :sid AND deleted_at IS NULL
        LIMIT 1
    """)

    async with laravel_session() as s:
        res = await s.execute(q_upd, params)
        # rows_affected always 0/1 because of LIMIT 1 + PK
        updated = res.rowcount or 0
        row = (await s.execute(q_get, {"sid": int(service_id)})).mappings().first()
        return {"ok": updated > 0, "updated": updated, "service": (dict(row) if row else None)}
