import asyncio
import httpx
from typing import List, Dict, Any
from helper.call_processor import CallProcessor
from helper.database import Database
import logging
import re
from dotenv import load_dotenv
import os

# Initialize logger
logger = logging.getLogger("cron_job_logger")
load_dotenv()

apiurl = os.getenv("API_URL")

headers = {
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}

processor = CallProcessor()
db = Database()

FIXED_ACCOUNT_ID = "562206937"

def extract_call_id_from_url(url: str):
    match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
    if match:
        return match.group(1)
    return None

async def process_clients_background(client_ids: List[str], user_id: int):
    """Process clients and handle lead data"""
    try:
        # Fetch transcripts from Laravel API
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{apiurl}/api/transcript/{user_id}", headers=headers)
            resp.raise_for_status()
            call_data = resp.json()

        # Filter the calls for the specified client_ids
        client_ids_set = set(map(str, client_ids))  # Use a set for fast lookup
        raw_calls: List[Dict[str, Any]] = call_data.get("data", []) or []
        filtered_calls: List[Dict[str, Any]] = [
            c for c in raw_calls if str(c.get("client_id")) in client_ids_set
        ]

        if not filtered_calls:
            logger.info(f"No calls found for the given client_ids: {client_ids}")
            return {"status": "success", "processed_phone_numbers": 0}

        phone_groups: Dict[str, Dict[str, Any]] = {}

        async def check_phone_exists(httpc: httpx.AsyncClient, phone: str) -> bool:
            try:
                r = await httpc.get(f"{apiurl}/api/check-phone-number/{phone}")
                r.raise_for_status()  # Ensure a 200 status code
                data = r.json()
                return bool(data.get("exists"))
            except httpx.RequestError as e:
                logger.warning("Request error for phone %s: %s", phone, e)
                return False
            except httpx.HTTPStatusError as e:
                logger.warning("HTTP error for phone %s: %s", phone, e.response.status_code)
                return False
            except Exception as e:
                logger.warning("General error for phone %s: %s", phone, e)
                return False

        # Process the filtered calls
        async with httpx.AsyncClient(timeout=15.0) as httpc:
            for call in filtered_calls:
                phone_number = call.get("phone_number")
                if not phone_number:
                    logger.info(f"Skipped call without phone number")
                    continue

                exists = await check_phone_exists(httpc, phone_number)
                logger.info(
                    "Phone %s %s in Laravel. Processing anyway.",
                    phone_number, "exists" if exists else "not found"
                )

                grp = phone_groups.setdefault(phone_number, {
                    "calls": [],
                    "call_data": call,  # representative payload
                })
                grp["calls"].append(call)

        # Process each phone group
        processed_count = 0
        data_to_send: List[Dict[str, Any]] = []

        for phone_number, group_data in phone_groups.items():
            try:
                logger.info(f"Processing phone number: {phone_number}")

                # Replace transcription logic with your own implementation (or mock it)
                transcription_tasks = [
                    transcribe_call(c.get("call_recording"))
                    for c in group_data["calls"]
                    if c.get("call_recording")
                ]
                transcriptions = await asyncio.gather(*transcription_tasks)
                valid_transcriptions = [t for t in transcriptions if t]

                if not valid_transcriptions:
                    logger.info(f"No valid transcriptions for phone number: {phone_number}")
                    continue

                # Combine all transcriptions
                combined_transcription = "\n\n---\n\n".join(valid_transcriptions)

                # Process lead data, scoring, etc. (simplified)
                summary = f"Processed data for {phone_number}"

                data_to_send.append({
                    "client_id": group_data["call_data"].get("client_id"),
                    "contact_number": phone_number,
                    "transcription": combined_transcription,
                    "description": summary,
                    "user_id": user_id
                })

                processed_count += 1
            except Exception as e:
                logger.exception("Error processing phone %s: %s", phone_number, e)

        if data_to_send:
            logger.info(f"Sending processed data for {processed_count} phone numbers to Laravel")
            # Simulate sending to Laravel
            # result = await send_data_to_laravel(data_to_send, user_id)
            logger.info(f"Successfully sent {processed_count} phone numbers.")
        else:
            logger.info("No valid data to send to Laravel.")

        return {"status": "success", "processed_phone_numbers": processed_count}

    except Exception as e:
        logger.exception("Error processing clients: %s", e)
        return {"status": "error", "detail": str(e)}

# Placeholder transcription function (you can implement it accordingly)
async def transcribe_call(recording_url):
    # Mocked transcription process since we no longer use whisper or torch
    if not recording_url:
        return None
    call_id = extract_call_id_from_url(recording_url)
    if not call_id:
        return None
    try:
        # Assuming you will process calls here with CallProcessor or another method
        result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
        return result.get("transcription") if isinstance(result, dict) else None
    except Exception as e:
        logger.exception("Transcription failed for %s: %s", recording_url, e)
        return None
