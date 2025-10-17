# agents/tools/sql_tools.py
from __future__ import annotations
import os
import json
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from tortoise import Tortoise

def json_dumps(o): return json.dumps(o, ensure_ascii=False, default=str)

# ---- whitelist (added client_leads) ----
READ_WHITELIST = {
    "leads": [
        "id","first_name","last_name","email","contact_number","status",
        "client_id","created_at","updated_at"
    ],
    "clients": ["id","name","email","phone","created_at","updated_at"],
    "client_leads": [
        "id","client_id","first_name","last_name","email","contact_number",
        "status","lead_source","potential_score","description","created_at","updated_at"
    ],
}

def _validate_columns(table: str, cols: Optional[List[str]]) -> List[str]:
    allowed = READ_WHITELIST[table]
    if not cols:
        return allowed[:]
    bad = [c for c in cols if c not in allowed]
    if bad:
        raise ValueError(f"Columns not allowed for {table}: {bad}")
    return cols

def _build_where(where: Optional[Dict[str, Any]], table: str) -> tuple[str, list]:
    if not where:
        return "", []
    allowed = READ_WHITELIST[table]
    clauses, params = [], []
    for k, v in where.items():
        if k not in allowed:
            raise ValueError(f"Illegal where key: {k}")
        clauses.append(f"`{k}` = %s")
        params.append(v)
    return (" WHERE " + " AND ".join(clauses), params)

# ---------- generic SELECT ----------
class SelectArgs(BaseModel):
    table: Literal[tuple(READ_WHITELIST.keys())]
    columns: Optional[List[str]] = None
    where: Optional[Dict[str, Any]] = None
    limit: int = Field(default=20, ge=1, le=200)
    order_by: Optional[str] = None

@tool("sql_select", args_schema=SelectArgs)
async def sql_select(table: str, columns: Optional[List[str]] = None,
                     where: Optional[Dict[str, Any]] = None,
                     limit: int = 20, order_by: Optional[str] = None) -> str:
    """Safe, read-only SELECT over whitelisted tables/columns. Returns JSON {ok, rows}."""
    cols = _validate_columns(table, columns)
    where_sql, params = _build_where(where, table)
    order_sql = ""
    if order_by:
        if order_by not in READ_WHITELIST[table]:
            raise ValueError(f"Illegal order_by: {order_by}")
        order_sql = f" ORDER BY `{order_by}` DESC"
    q = f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{table}`{where_sql}{order_sql} LIMIT {limit}"
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(q, params)
    return json_dumps({"ok": True, "rows": rows})

# ---------- NEW: fetch a single lead (enforces client_id) ----------
class LeadGetArgs(BaseModel):
    client_id: int
    lead_id: int
    columns: Optional[List[str]] = None

@tool("lead_get", args_schema=LeadGetArgs)
async def lead_get(client_id: int, lead_id: int, columns: Optional[List[str]] = None) -> str:
    """Fetch one row from client_leads for the given client_id and lead_id. Returns JSON {ok,lead} or {ok:false,error}."""
    table = "client_leads"
    cols = _validate_columns(table, columns)
    q = f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{table}` WHERE `client_id`=%s AND `id`=%s LIMIT 1"
    print("[AI-DBG] sql.lead_get.query:", q)
    print("[AI-DBG] sql.lead_get.params:", [client_id, lead_id])
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(q, [client_id, lead_id])
    if not rows:
        return json_dumps({"ok": False, "error": "Lead not found or not owned by client_id"})
    return json_dumps({"ok": True, "lead": rows[0]})



# ---------- NEW: search leads (enforces client_id) ----------
class LeadSearchArgs(BaseModel):
    client_id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    columns: Optional[List[str]] = None
    limit: int = Field(default=20, ge=1, le=200)

@tool("lead_search", args_schema=LeadSearchArgs)
async def lead_search(client_id: int, name: Optional[str] = None, email: Optional[str] = None,
                      phone: Optional[str] = None, columns: Optional[List[str]] = None,
                      limit: int = 20) -> str:
    """Search client_leads by name/email/phone with enforced client_id. Returns JSON {ok, rows}."""
    if not any([name, email, phone]):
        return json_dumps({"ok": False, "error": "Provide at least one of name/email/phone"})

    table = "client_leads"
    cols = _validate_columns(table, columns)

    clauses = ["`client_id` = %s"]
    params: List[Any] = [client_id]

    if email:
        clauses.append("`email` = %s")
        params.append(email)
    if phone:
        clauses.append("`contact_number` = %s")
        params.append(phone)
    if name:
        like = f"%{name}%"
        clauses.append("(`first_name` LIKE %s OR `last_name` LIKE %s)")
        params.extend([like, like])

    where_sql = " WHERE " + " AND ".join(clauses)
    q = f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{table}`{where_sql} ORDER BY `id` DESC LIMIT {limit}"

    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(q, params)
    return json_dumps({"ok": True, "rows": rows})

# ---------- (Write) UPDATE — keep as a plain function unless enabled ----------
ENABLE_SQL_UPDATE_TOOL = os.getenv("ENABLE_SQL_UPDATE_TOOL", "0") == "1"

class UpdateArgs(BaseModel):
    table: Literal["leads"]  # expand intentionally
    where_id: int
    updates: Dict[str, Any]

ALLOWED_UPDATES = {
    "leads": {"status","first_name","last_name","contact_number","email","description","lead_source","potential_score"}
}

async def _sql_update_impl(table: str, where_id: int, updates: Dict[str, Any]) -> str:
    """Restricted UPDATE on whitelisted table 'leads'. Returns JSON {ok,updated_id} or {ok:false,error}."""
    allowed = ALLOWED_UPDATES[table]
    bad = [k for k in updates.keys() if k not in allowed]
    if bad:
        return json_dumps({"ok": False, "error": f"Fields not allowed: {bad}"})
    sets = ", ".join(f"`{k}`=%s" for k in updates.keys())
    params = list(updates.values()) + [where_id]
    q = f"UPDATE `{table}` SET {sets} WHERE `id`=%s"
    conn = Tortoise.get_connection("default")
    await conn.execute_query(q, params)
    return json_dumps({"ok": True, "updated_id": where_id})

# Only expose as a LangChain tool when explicitly enabled
if ENABLE_SQL_UPDATE_TOOL:
    @tool("sql_update", args_schema=UpdateArgs)
    async def sql_update(table: str, where_id: int, updates: Dict[str, Any]) -> str:
        """Restricted UPDATE on whitelisted table 'leads'. Returns JSON {ok,updated_id} or {ok:false,error}."""
        return await _sql_update_impl(table, where_id, updates)
else:
    # keep a plain function available for your own direct calls if needed
    async def sql_update(table: str, where_id: int, updates: Dict[str, Any]) -> str:
        """(Not exposed as a tool unless ENABLE_SQL_UPDATE_TOOL=1)."""
        return await _sql_update_impl(table, where_id, updates)
