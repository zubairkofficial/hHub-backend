# controller/score_request_controller.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import os
import logging
from logging.handlers import RotatingFileHandler

# If these are used elsewhere in your project, keep the imports:
from tortoise import Tortoise  # noqa: F401
from tortoise.exceptions import DoesNotExist  # noqa: F401
from models.post_history import PostHistory  # noqa: F401
from models.post_draft import PostDraft  # noqa: F401

from cron_job import process_single_user
from controller.job_calldata_controller import get_users_by_client


# --------------------- Robust logger setup ---------------------
LOG_DIR = "/var/log/hhub"
LOG_FILE = "cron_job_debug.log"

log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("cron_job")
logger.setLevel(logging.DEBUG)

# Avoid adding handlers multiple times if module re-imports (e.g., reload/workers)
if not logger.handlers:
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler (rotating) — write under /var/log/hhub
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, LOG_FILE),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except Exception as e:
        # If we can't write to /var/log/hhub, continue with console logging only
        logger.warning(f"File logging disabled: {e}")
# ------------------- end robust logger setup -------------------


# FastAPI router
router = APIRouter()


class ScorePayload(BaseModel):
    user_id: str


@router.post("/manually", status_code=status.HTTP_200_OK)
async def run_manual(score_payload: ScorePayload):
    """
    Manually trigger the cron-like processing for a given user_id (client context).
    Returns a summary of the processing.
    """
    try:
        logger.info("=== Starting cron job ===")
        logger.info("Fetching users and client data...")

        users_data = await get_users_by_client(score_payload.user_id)

        if not users_data or not users_data.get("data"):
            msg = "No user data returned for the provided user_id"
            logger.error(msg)
            # Return a JSON response rather than raising to keep 200 contract; change if desired
            return {"status": "no_data", "message": msg, "user_id": score_payload.user_id}

        users = users_data.get("data", [])
        logger.info(f"Successfully received data for {len(users)} users")

        results = []
        # Process sequentially (keeps logs tidy). If needed, you can run concurrently with asyncio.gather.
        for u in users:
            try:
                res = await process_single_user(u)
                results.append(res or {})
            except Exception as e:
                logger.exception(f"Error processing user entry {u}: {e}")
                results.append({"status": "error", "error": str(e)})

        completed = sum(1 for r in results if (r or {}).get("status") == "completed")
        total_processed = sum((r or {}).get("processed_count", 0) for r in results)

        summary = {
            "status": "ok",
            "user_id": score_payload.user_id,
            "users_received": len(users),
            "users_completed": completed,
            "total_records_processed": total_processed,
            "results": results,
        }

        logger.info("=== Cron job completed ===")
        logger.info(
            f"Processed {len(results)} users ({completed} successfully). "
            f"Total records processed: {total_processed}"
        )

        return summary

    except Exception as e:
        logger.exception(f"Fatal error in run_manual: {e}")
        # If you prefer a 500 response, raise HTTPException:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {e}"
        )
