import asyncio
import logging
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG
import uuid
import os
from dotenv import load_dotenv

from controller.job_calldata_controller import get_users_by_client
# ✅ import the transcription+scoring background function
from controller.call_transcript_controller import process_clients_background

# logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cron_job")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

file_handler = logging.FileHandler('cron_job_debug.log', mode='w')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

async def init_orm():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set; cannot init Tortoise for cron job")
    await Tortoise.init(config=TORTOISE_CONFIG)
    # In prod, use migrations; don't regenerate on every run:
    # await Tortoise.generate_schemas()


async def shutdown_orm():
    await Tortoise.close_connections()

async def process_single_user(user):
    user_id = user.get('id')
    logger.info(f"\n=== Processing user ID: {user_id} === {user}")

    rels = user.get('client') or []
    # if not rels:
    #     logger.info(f"No client data for user {user_id}")
    #     return {"user_id": user_id, "status": "no_clients"}

    clients = [{"client_id": user['client_id']}]
    # for rel in rels:
    #     client_id = str(rel.get('client_id') or rel.get('id') or "").strip()
    #     callrail_id = (rel.get('client') or {}).get('callrail_id') if isinstance(rel.get('client'), dict) else None
    #     if client_id:
    #         clients.append({"client_id": client_id, "callrail_id": callrail_id, "name": rel.get('name') or "Unnamed Client"})

    # if not clients:
    #     logger.warning(f"No valid client relations for user {user_id}")
    #     return {"user_id": user_id, "status": "no_valid_clients"}

    total_processed = 0
    for c in clients:
        try:
            session_id = str(uuid.uuid4())
            logger.info(f"Processing client {c['client_id']} (user {user_id}) session={session_id}")
            # signature: (client_ids: List[str], session_id: str, user_id: int)
            result = await process_clients_background([c['client_id']], session_id, user_id)
            processed_phones = int((result or {}).get("processed_phone_numbers", 0))
            # logger.info(f"Done client {c['client_id']} → processed phones: {processed_phones}")
            total_processed += processed_phones
        except Exception as e:
            logger.exception(f"Error processing client {c['client_id']}: {e}")

    return {"user_id": user_id, "status": "completed", "processed_count": total_processed, "client_count": len(clients)}


async def main():
    try:
        logger.info("=== Starting cron job ===")
        await init_orm()  # <-- IMPORTANT
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

        logger.info("\n=== Cron job completed ===")
        logger.info(f"Processed {len(results)} users ({completed} successfully)")
        logger.info(f"Total records processed: {total_processed}")
        

    except Exception as e:
        logger.exception(f"Fatal error in main: {e}")
        raise
    finally:
        await shutdown_orm()  # <-- IMPORTANT


if __name__ == "__main__":
    asyncio.run(main())
