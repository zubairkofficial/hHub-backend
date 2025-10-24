# agents/tools/service_tools.py
import os, json
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from services.laravel_db_services.services_repo import (
    service_list, service_get, service_search, service_update
)

def _j(o): return json.dumps(o, ensure_ascii=False, default=str)

# Writes are OFF by default — enable only when you want to update
SERVICES_ALLOW_WRITE = os.getenv("SERVICES_ALLOW_WRITE", "0") == "1"

# ---------- list ----------
class ServiceListArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

@tool("service_list", args_schema=ServiceListArgs)
async def tool_service_list(limit: int = 50, offset: int = 0) -> str:
    """List services. Args: limit:int=50, offset:int=0"""
    rows = await service_list(limit=limit, offset=offset)
    return _j({"ok": True, "rows": rows, "count": len(rows)})

# ---------- get ----------
class ServiceGetArgs(BaseModel):
    service_id: int = Field(..., ge=1)

@tool("service_get", args_schema=ServiceGetArgs)
async def tool_service_get(service_id: int) -> str:
    """Get a service by id. Args: service_id:int"""
    row = await service_get(service_id)
    if not row:
        return _j({"ok": False, "error": f"Service #{service_id} not found"})
    return _j({"ok": True, "service": row})

# ---------- search ----------
class ServiceSearchArgs(BaseModel):
    q: str = Field(..., min_length=1, max_length=120)
    limit: int = Field(default=25, ge=1, le=200)

@tool("service_search", args_schema=ServiceSearchArgs)
async def tool_service_search(q: str, limit: int = 25) -> str:
    """Search services by name/description. Args: q:str, limit:int=25"""
    rows = await service_search(q, limit=limit)
    return _j({"ok": True, "rows": rows, "count": len(rows)})

# ---------- update ----------
class ServiceUpdateArgs(BaseModel):
    service_id: int = Field(..., ge=1)
    name: Optional[str] = None
    description: Optional[str] = None
    for_report: Optional[int] = Field(None, ge=0, le=1)

@tool("service_update", args_schema=ServiceUpdateArgs)
async def tool_service_update(service_id: int,
                              name: Optional[str] = None,
                              description: Optional[str] = None,
                              for_report: Optional[int] = None) -> str:
    """
    Update a service (name/description/for_report).
    Writes are gated by SERVICES_ALLOW_WRITE=1 in Python .env.
    """
    if not SERVICES_ALLOW_WRITE:
        return _j({"ok": False, "error": "Writes disabled. Set SERVICES_ALLOW_WRITE=1 in Python .env"})
    out = await service_update(service_id, name=name, description=description, for_report=for_report)
    return _j(out)
