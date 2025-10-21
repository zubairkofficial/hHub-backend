import asyncio
import logging
from logging.handlers import RotatingFileHandler
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG
import uuid
import os
from dotenv import load_dotenv

from controller.job_calldata_controller import get_users_by_client
# ✅ import the transcription+scoring background function
from controller.call_transcript_controller import process_clients_background

# -----------------------------------------------------------------------------
# Logging: make module import-safe (no file I/O at import time)
# -----------------------------------------------------------------------------
logger = logging.getLogger("cron_job")
logger.setLevel(logging.INFO)
# Avoid "No handler could be found" warnings when imported
logger.addHandler(logging.NullHandler())

LOG_DIR = "/var/www/hHub-backend/logs"
LOG_FILE = os.path.join(LOG_DIR, "cron_job_debug.log")

def init_logger(to_file: bool = False) -> None:
    """
    Configure logging once. Safe to call multiple times.
    If to_file=True, also attach a rotating file handler (delayed open).
    """
    # Remove NullHandler if present
    for h in list(logger.handlers):
        if isinstance(h, logging.NullHandler):
            logger.removeHandler(h)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(sh)

    if to_file and not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        # Ensure directory exists and is writable
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8", delay=True
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)

# -----------------------------------------------------------------------------
# ORM
# -----------------------------------------------------------------------------
async def init_orm():
    load_dotenv()  # ensure .env is loaded when running as script
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set; cannot init Tortoise for cron job")
    await Tortoise.init(config=TORTOISE_CONFIG)
    # In prod, rely on migrations; don't auto-generate schemas.
    # await Tortoise.generate_schemas()

async def shutdown_orm():
    await Tortoise.close_connections()

# -----------------------------------------------------------------------------
# Worker
# -----------------------------------------------------------------------------
async def process_single_user(user):
    user_id = user.get('id')
    logger.info(f"=== Processing user ID: {user_id} === {user}")

    # Your current payload seems to carry top-level client_id:
    clients = [{"client_id": user['client_id']}]

    total_processed = 0
    for c in clients:
        try:
            session_id = str(uuid.uuid4())
            logger.info(f"Processing client {c['client_id']} (user {user_id}) session={session_id}")
            # signature: (client_ids: List[str], session_id: str, user_id: int)
            result = await process_clients_background([c['client_id']], session_id, user_id)
            processed_phones = int((result or {}).get("processed_phone_numbers", 0))
            total_processed += processed_phones
        except Exception as e:
            logger.exception(f"Error processing client {c['client_id']}: {e}")

    return {"user_id": user_id, "status": "completed", "processed_count": total_processed, "client_count": len(clients)}

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
async def main():
    try:
        logger.info("=== Starting cron job ===")
        await init_orm()
        logger.info("Fetching users and client data...")
        users_data = await get_users_by_client()

        if not users_data or not users_data.get('data'):
            logger.error("No user data returned")
            return

        users = users_data.get('data', [])
        logger.info(f"Successfully received data for {len(users)} users")

        results = []
        for u in users:
            results.append(await process_single_user(u))

        completed = sum(1 for r in results if r.get('status') == 'completed')
        total_processed = sum(r.get('processed_count', 0) for r in results)

        logger.info("=== Cron job completed ===")
        logger.info(f"Processed {len(results)} users ({completed} successfully)")
        logger.info(f"Total records processed: {total_processed}")

    except Exception as e:
        logger.exception(f"Fatal error in main: {e}")
        raise
    finally:
        await shutdown_orm()

if __name__ == "__main__":
    # In dev: stdout only; In prod: set to_file=True to also write rotating file logs
    init_logger(to_file=True)
    asyncio.run(main())
