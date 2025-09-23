import asyncio
from datetime import datetime
from helper.database import Database
from helper.call_processor import CallProcessor
from helper.lead_scoring import LeadScoringService
from models.lead_score import LeadScore
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG
import httpx
import os
import base64
from pathlib import Path
import os
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import re
import asyncio
from fastapi import APIRouter, Request

router = APIRouter()


# Initialize helpers
db = Database()
processor = CallProcessor()
scoring_service = LeadScoringService()
API_URL = os.getenv("API_URL")

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

async def process_unprocessed_callrails():
    # Initialize Tortoise ORM
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    try:
        # 1. Fetch all call data from the API
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{API_URL}/api/transcript", headers=headers)
                response.raise_for_status()
                call_data = response.json()
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return
            except Exception as e:
                print(f"Error fetching call data: {e}")
                return
            
            rows = [row for row in call_data.get("data", []) if not row.get("is_processed")]

        if not rows:
            print(f"[{datetime.now()}] No unprocessed callrails found.")
            return

        # 2. Group by phone_number
        phone_groups = {}
        for row in rows:
            phone_number = row.get("phone_number")
            if not phone_number:
                continue
            if phone_number not in phone_groups:
                phone_groups[phone_number] = []
            phone_groups[phone_number].append(row)

        # 3. Process each phone number group
        for phone_number, calls in phone_groups.items():
            print(f"[{datetime.now()}] Processing phone number: {phone_number} with {len(calls)} calls")
            transcriptions = []
            for call in calls:
                recording_url = call.get("call_recording")
                if not recording_url:
                    continue
                # Extract call_id from URL (assumes last part is call_id)
                call_id = recording_url.split("/")[-2] if "/" in recording_url else None
                if not call_id:
                    continue
                # Replace with your actual account ID
                result = await processor.process_call(account_id="562206937", call_id=call_id)
                if result and "transcription" in result and result["transcription"]:
                    transcriptions.append(result["transcription"])
            if not transcriptions:
                print(f"[{datetime.now()}] No valid transcriptions for {phone_number}")
                continue
            combined_transcription = "\n\n---\n\n".join(transcriptions)
            # 4. Generate score
            recent_call = calls[-1]
            summary_response = await scoring_service.generate_summary(
                transcription=combined_transcription,
                client_type=recent_call.get("client_type"),
                service=recent_call.get("service"),
                state=recent_call.get("state"),
                city=recent_call.get("city"),
                first_call=recent_call.get("first_call"),
                rota_plan=recent_call.get("rota_plan"),
                previous_analysis=None,
                
            )
            analysis_summary = summary_response["summary"]
            scores = await scoring_service.score_summary(analysis_summary)
            # 5. Update or create lead_score for this phone number
            existing_lead_score = await LeadScore.filter(phone=phone_number).first()
            if existing_lead_score:
                await LeadScore.filter(id=existing_lead_score.id).update(
                    client_id=recent_call.get("client_id"),
                    callrail_id=None,
                    name=recent_call.get("name"),
                    analysis_summary=analysis_summary,
                    intent_score=scores.intent_score,
                    urgency_score=scores.urgency_score,
                    overall_score=scores.overall_score,
                    updated_at=datetime.now()
                )
                print(f"[{datetime.now()}] Updated lead score for {phone_number}")
            else:
                await LeadScore.create(
                    client_id=recent_call.get("client_id"),
                    callrail_id=None,
                    name=recent_call.get("name"),
                    analysis_summary=analysis_summary,
                    phone=phone_number,
                    intent_score=scores.intent_score,
                    urgency_score=scores.urgency_score,
                    overall_score=scores.overall_score,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                print(f"[{datetime.now()}] Created new lead score for {phone_number}")
            # 6. Mark all these calls as processed via Laravel API
            update_tasks = []
            for call in calls:
                update_url = f"{API_URL}/api/update_call/{call['id']}"
                update_tasks.append(mark_call_as_processed(update_url))

            await asyncio.gather(*update_tasks)

    finally:
        await Tortoise.close_connections()

async def mark_call_as_processed(update_url):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(update_url, headers=headers)
            response.raise_for_status()
            if response.status_code == 200:
                print(f"Marked call as processed: {update_url}")
            else:
                print(f"Unexpected status for {update_url}: {response.status_code}")
        except httpx.HTTPStatusError as e:
            print(f"Failed to mark call: {update_url}, error: {e}")
        except Exception as e:
            print(f"Error in marking call: {update_url}, error: {e}")


# shoaib code start# 

CALLRAIL_API_KEY = os.getenv("CALLRAIL_API_KEY", "")
CALLRAIL_ACCOUNT_ID = os.getenv("CALLRAIL_ACCOUNT_ID", "")  # e.g. "ACC6163...."
CALLRAIL_TIMEOUT = 60.0


# ───────────────────────── Helpers ─────────────────────────

def _guess_ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if "wav" in mime:
        return "wav"
    if "ogg" in mime:
        return "ogg"
    if "m4a" in mime or "mp4" in mime or "aac" in mime:
        return "m4a"
    return "mp3"


def _extract_call_id_from_url(url: str) -> Optional[str]:
    # Works for:
    # https://app.callrail.com/calls/CALxxxx/recording?access_key=...
    # https://api.callrail.com/v3/a/ACC.../calls/CALxxxx/recording
    m = re.search(r"/calls/(CAL[0-9a-zA-Z]+)/", url)
    return m.group(1) if m else None


async def _download_bytes(client: httpx.AsyncClient, url: str, headers: Dict[str, str]) -> Tuple[bytes, str]:
    """
    Download audio bytes from a CallRail recording URL.
    Handles:
      - Redirects
      - JSON wrappers that contain a URL
    Returns: (bytes, content_type)
    """
    r = await client.get(url, headers=headers, allow_redirects=True)
    ct = r.headers.get("content-type", "").lower()

    # JSON wrapper case (sometimes the first hop is JSON)
    if "application/json" in ct:
        try:
            data = r.json()
            # try common keys where the real file URL might be
            for k in ("url", "download_url", "href", "recording_url"):
                real = data.get(k)
                if isinstance(real, str):
                    r2 = await client.get(real, headers=headers, allow_redirects=True)
                    return (r2.content, r2.headers.get("content-type", "application/octet-stream"))
        except Exception:
            pass  # fall through

    return (r.content, r.headers.get("content-type", "application/octet-stream"))


async def _fetch_audio_b64_from_callrail(recording_url: str) -> Optional[Dict]:
    """
    Given a (public) recording URL from your DB, fetch the raw audio,
    return dict: { filename, mime, duration?, data_b64 }
    """
    if not recording_url:
        return None

    # Prefer the API URL if you can build it (requires account id + API key)
    # But using the public 'app.callrail.com/.../recording?...' works too (no auth).
    url = recording_url
    call_id = _extract_call_id_from_url(recording_url)

    # If you have both CALLRAIL_ACCOUNT_ID and API key, try API endpoint first
    # (More stable; some public pages are HTML wrappings)
    if CALLRAIL_API_KEY and CALLRAIL_ACCOUNT_ID and call_id:
        url = f"https://api.callrail.com/v3/a/{CALLRAIL_ACCOUNT_ID}/calls/{call_id}/recording"

    headers = {
        "User-Agent": "hHub-FastAPI/1.0",
        "Accept": "*/*",
    }
    if CALLRAIL_API_KEY:
        headers["Authorization"] = f"Token token={CALLRAIL_API_KEY}"

    async with httpx.AsyncClient(timeout=CALLRAIL_TIMEOUT) as client:
        audio_bytes, content_type = await _download_bytes(client, url, headers)

    if not audio_bytes:
        return None

    ext = _guess_ext_from_mime(content_type)
    filename = f"{call_id or 'call'}.{ext}"

    return {
        "filename": filename,
        "mime": content_type or "audio/mpeg",
        "data_b64": base64.b64encode(audio_bytes).decode("ascii"),
    }


# ───────────────────────── Core logic ─────────────────────────

async def process_unprocessed_callrails_no_store(call_data: List[dict]):
    """
    Your original function, extended to include a `recordings` array with Base64 audio.
    Does NOT save to any DB on the Python side.
    """
    # Init ORM if your scoring/transcription services rely on DB models.
    # If not needed, you can remove the Tortoise calls.
    await Tortoise.init(config=TORTOISE_CONFIG)            # noqa: F821
    await Tortoise.generate_schemas()                      # noqa: F821
    try:
        # Filter those that are not processed yet (same as your code)
        rows = [row for row in call_data if not row.get("is_processed")]

        if not rows:
            print(f"[{datetime.now()}] No unprocessed callrails found.")
            return {"data": []}

        # Group by phone
        phone_groups: Dict[str, List[dict]] = {}
        for row in rows:
            pn = row.get("phone_number")
            if not pn:
                continue
            phone_groups.setdefault(pn, []).append(row)

        results = []

        for phone_number, calls in phone_groups.items():
            print(f"[{datetime.now()}] Processing phone number: {phone_number} with {len(calls)} calls")
            transcriptions: List[str] = []
            recordings_out: List[dict] = []

            # Process each call in group
            for call in calls:
                recording_url = call.get("call_recording")
                if not recording_url:
                    continue

                # 1) Transcription (your existing pipeline)
                #    Keep exactly what you had; we won’t force changes to your processor.
                #    If you prefer to transcribe from our bytes, you can add that path too.
                call_id = _extract_call_id_from_url(recording_url) or "call"
                try:
                    result = await processor.process_call(  # noqa: F821
                        account_id=CALLRAIL_ACCOUNT_ID or "562206937",
                        call_id=call_id
                    )
                    if result and result.get("transcription"):
                        transcriptions.append(result["transcription"])
                except Exception as e:
                    print(f"Transcription error for {phone_number}/{call_id}: {e}")

                # 2) Raw audio for Laravel (Base64)
                try:
                    rec = await _fetch_audio_b64_from_callrail(recording_url)
                    if rec:
                        # If you keep duration in your original CallRail row:
                        dur = call.get("duration")
                        if dur is not None:
                            rec["duration"] = str(dur)
                        recordings_out.append(rec)
                except Exception as e:
                    print(f"Audio fetch error for {phone_number}: {e}")

            if not transcriptions and not recordings_out:
                print(f"[{datetime.now()}] No valid transcriptions/recordings for {phone_number}")
                continue

            combined_transcription = "\n\n---\n\n".join(transcriptions) if transcriptions else None

            # Latest call for context
            recent_call = calls[-1]

            # Build scores/summary if you have a transcript; otherwise you can still send recordings only.
            analysis_summary = None
            intent_score = urgency_score = overall_score = potential_score = None

            if combined_transcription:
                try:
                    summary_response = await scoring_service.generate_summary(  # noqa: F821
                        transcription=combined_transcription,
                        client_type=recent_call.get("client_type"),
                        service=recent_call.get("service"),
                        state=recent_call.get("state"),
                        city=recent_call.get("city"),
                        first_call=recent_call.get("first_call"),
                        rota_plan=recent_call.get("rota_plan"),
                        previous_analysis=None,
                        client_id=recent_call.get("client_id"),
                    )
                    analysis_summary = summary_response.get("summary")
                except Exception as e:
                    print(f"Summary error for {phone_number}: {e}")

                try:
                    scores = await scoring_service.score_summary(             # noqa: F821
                        analysis_summary or "",
                        client_id=recent_call.get("client_id")
                    )
                    intent_score = getattr(scores, "intent_score", None)
                    urgency_score = getattr(scores, "urgency_score", None)
                    overall_score = getattr(scores, "overall_score", None)
                    potential_score = getattr(scores, "potential_score", None)
                except Exception as e:
                    print(f"Scoring error for {phone_number}: {e}")

            results.append({
                "id": recent_call.get("id"),
                "client_id": recent_call.get("client_id"),
                "phone_number": phone_number,
                "name": recent_call.get("name"),
                "analysis_summary": analysis_summary,
                "transcription": combined_transcription,
                "intent_score": intent_score,
                "urgency_score": urgency_score,
                "overall_score": overall_score,
                "potential_score": potential_score,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                # NEW: local-ready audio payload(s)
                "recordings": recordings_out,   # [{ filename, mime, duration?, data_b64 }]
            })

        return {"data": results}

    finally:
        await Tortoise.close_connections()




