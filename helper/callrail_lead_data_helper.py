# helper/callrail_lead_data_helper.py

import logging
from typing import List, Dict, Any
from dotenv import load_dotenv
import os

from .CallRailProcessor import CallRailProcessor  # <- correct import

logger = logging.getLogger("cron_job_logger")
load_dotenv()

api_url = os.getenv("API_URL") or ""

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "CallRailProcessor/1.0"
}

# single processor instance for batching to Laravel
callrail_processor = CallRailProcessor(api_url, headers)

async def send_data_to_laravel(data_to_send: List[Dict[str, Any]], user_id: int) -> Dict[str, Any]:
    """
    Send processed lead data to Laravel API.
    Returns Laravel's response dict: {status, created, updated, errors}
    """
    try:
        # Ensure user_id is present (controller relies on it)
        for rec in data_to_send:
            rec.setdefault("user_id", user_id)

        result = await callrail_processor._send_processed_data_to_laravel(data_to_send, user_id)
        return result or {"status": "error", "message": "Empty response from _send_processed_data_to_laravel"}
    except Exception as e:
        logger.error(f"Error in send_data_to_laravel: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
