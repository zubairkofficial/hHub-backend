from fastapi import APIRouter, HTTPException, status
from tortoise import Tortoise
from tortoise.exceptions import DoesNotExist
from models.post_history import PostHistory
from models.post_draft import PostDraft
from pydantic import BaseModel
from typing import List, Dict
from enum import Enum
import asyncio
import logging
from cron_job import process_single_user
from controller.job_calldata_controller import get_users_by_client



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
# FastAPI app instance
router = APIRouter()
class ScorePayload(BaseModel):
    user_id: str
@router.post("/manually")
async def main(score_payload:ScorePayload):
    
    try:
        logger.info("=== Starting cron job ===")
        logger.info("Fetching users and client data...")
        users_data = await get_users_by_client(score_payload.user_id)

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
