# helper/laravel_db.py
import os
from typing import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

_L_HOST = os.getenv("LARAVEL_DB_HOST", "127.0.0.1")
_L_PORT = int(os.getenv("LARAVEL_DB_PORT", "3306"))
_L_NAME = os.getenv("LARAVEL_DB_NAME", "")
_L_USER = os.getenv("LARAVEL_DB_USER", "")
_L_PASS = os.getenv("LARAVEL_DB_PASSWORD", "")

_DSN = f"mysql+aiomysql://{_L_USER}:{_L_PASS}@{_L_HOST}:{_L_PORT}/{_L_NAME}?charset=utf8mb4"

_engine = create_async_engine(
    _DSN,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
    isolation_level="AUTOCOMMIT",
)

_Session = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)

@asynccontextmanager
async def laravel_session() -> AsyncIterator[AsyncSession]:
    async with _Session() as session:
        yield session

# --- graceful shutdown to avoid "Event loop is closed" on Windows ---
async def shutdown():
    try:
        await _engine.dispose()
    except Exception:
        pass

# ---------------- queries ----------------
async def fetch_services(limit: int = 50, offset: int = 0):
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

async def fetch_service_by_id(service_id: int):
    q = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE id = :sid AND deleted_at IS NULL
        LIMIT 1
    """)
    async with laravel_session() as s:
        row = (await s.execute(q, {"sid": int(service_id)})).mappings().first()
        return dict(row) if row else None

async def search_services(query: str, limit: int = 25):
    q = text("""
        SELECT id, name, description, for_report
        FROM services
        WHERE deleted_at IS NULL
          AND (name LIKE :q OR description LIKE :q)
        ORDER BY name ASC
        LIMIT :limit
    """)
    async with laravel_session() as s:
        rows = (await s.execute(q, {"q": f"%{query.strip()}%", "limit": int(limit)})).mappings().all()
        return [dict(r) for r in rows]
