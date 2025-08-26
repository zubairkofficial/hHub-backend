import asyncio
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import httpx
import whisper
from helper.call_processor import CallProcessor
import re
from models.lead_score import LeadScore
from helper.database import Database
from datetime import datetime
from fastapi import HTTPException, Request
from typing import List, Optional, Dict, Any, Union
from fastapi import Query
from pydantic import BaseModel
import json
import uuid
from collections import defaultdict
from dotenv import load_dotenv
from datetime import datetime
from models.system_prompt import SystemPrompts
import requests
import logging
import re

load_dotenv()


router = APIRouter()
model = whisper.load_model("base")
db = Database()

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
CALLRAIL_BEARER_TOKEN = os.getenv("CALLRAIL_BEARER_TOKEN")
CALLRAIL_API_BASE = "https://api.callrail.com/v3"

if not CALLRAIL_BEARER_TOKEN:
    raise ValueError("CALLRAIL_BEARER_TOKEN not found in environment variables")

# Store active progress sessions
active_sessions: Dict[str, Dict[str, Any]] = {}

def extract_call_id_from_url(url: str):
    match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
    if match:
        return match.group(1)
    return None





logger = logging.getLogger("uvicorn.error")

FIXED_ACCOUNT_ID = "562206937"  # moved out so it's always in scope

def _truncate(s: str, n: int = 1200):
    if not isinstance(s, str):
        return s
    return s if len(s) <= n else s[:n] + "…"

def _truncate(s: str, n: int = 1200):
    if not isinstance(s, str):
        return s
    return s if len(s) <= n else s[:n] + "…"


async def process_clients_background(client_ids: List[str], session_id: str, user_id: int):
    """Background task to process clients and update progress."""
    active_sessions[session_id] = {
        "total": 0,
        "processed": 0,
        "details": [],
        "status": "processing",
    }

    try:
        # 1) Fetch transcripts from Laravel
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(f"{apiurl}/api/transcript", headers=headers)
            resp.raise_for_status()
            call_data = resp.json()

        # 2) Filter by requested client_ids (normalize to str for robust matching)
        wanted = {str(cid) for cid in client_ids}
        raw_calls: List[Dict[str, Any]] = call_data.get("data", []) or []
        filtered_calls: List[Dict[str, Any]] = [
            c for c in raw_calls if str(c.get("client_id")) in wanted
        ]

        if not filtered_calls:
            active_sessions[session_id]["status"] = "completed"
            active_sessions[session_id]["total"] = 0
            return {"status": "success", "processed_phone_numbers": 0}

        # 3) Group calls by phone; pre-check phone existence (for logging only)
        phone_groups: Dict[str, Dict[str, Any]] = {}

        async def check_phone_exists(httpc: httpx.AsyncClient, phone: str) -> bool:
            try:
                r = await httpc.get(f"{apiurl}/api/check-phone-number/{phone}")
                if r.status_code != 200:
                    return False
                data = r.json()
                return bool(data.get("exists"))
            except Exception as e:
                logger.warning("Phone existence check failed for %s: %s", phone, e)
                return False

        async with httpx.AsyncClient(timeout=15.0) as httpc:
            for call in filtered_calls:
                phone_number = call.get("phone_number")
                if not phone_number:
                    active_sessions[session_id]["details"].append({
                        "message": "Skipped call without phone_number",
                        "status": "skipped",
                    })
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

        # Progress target: total = distinct phones we’ll process
        active_sessions[session_id]["total"] = len(phone_groups)

        if not phone_groups:
            active_sessions[session_id]["status"] = "completed"
            return {"status": "success", "processed_phone_numbers": 0}

        # 4) Helper: transcribe one call
        async def transcribe_call(recording_url: str) -> Optional[str]:
            if not recording_url:
                return None
            call_id = extract_call_id_from_url(recording_url)
            if not call_id:
                return None
            try:
                result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
                tx = result.get("transcription") if isinstance(result, dict) else None
                return tx.strip() if isinstance(tx, str) and tx.strip() else None
            except Exception as e:
                logger.exception("Transcription failed for %s: %s", recording_url, e)
                return None

        processed_count = 0
        data_to_send: List[Dict[str, Any]] = []

        # 5) Process each phone group
        for phone_number, group_data in phone_groups.items():
            try:
                active_sessions[session_id]["details"].append({
                    "message": f"Processing phone number: {phone_number}",
                    "status": "processing",
                })

                # Transcribe all calls for this phone
                transcription_tasks = [
                    transcribe_call(c.get("call_recording"))
                    for c in group_data["calls"]
                    if c.get("call_recording")
                ]
                transcriptions = await asyncio.gather(*transcription_tasks, return_exceptions=False)
                valid_transcriptions = [t for t in transcriptions if t]

                cd = group_data.get("call_data") or {}
                client_id_int = _int_or_none(cd.get("client_id"))
                recent_call = group_data["calls"][-1]

                if not valid_transcriptions:
                    # No transcript → mark as miss
                    full_name = _derive_fullname(recent_call, None)
                    first_name, last_name, _ = _split_name(full_name)
                    logger.info("Derived name for %s → first=%r last=%r", phone_number, first_name, last_name)

                    data_to_send.append({
                        "client_id": client_id_int,
                        "contact_number": phone_number,
                        "type": "miss",
                        "potential_score": 0,
                        "transcription": "",
                        "description": "",
                        "callrail_id": cd.get("callrail_id"),
                        "first_name": first_name,
                        "last_name": last_name,
                        "status": cd.get("status"),
                        "is_scored": True,
                        "is_self": False,
                    
                    })

                    processed_count += 1
                    active_sessions[session_id]["processed"] = processed_count
                    active_sessions[session_id]["details"].append({
                        "message": f"No valid transcription → queued MISS for {phone_number}",
                        "status": "skipped",
                    })
                    continue

                # We have at least one transcript → receive
                combined_transcription = "\n\n---\n\n".join(valid_transcriptions)

                # Derive name AFTER we have transcript (can parse “This is …”)
                full_name = _derive_fullname(recent_call, combined_transcription)
                first_name, last_name, _ = _split_name(full_name)
                logger.info("Derived name for %s → first=%r last=%r", phone_number, first_name, last_name)

                # Create analysis summary and score
                summary_response = await db.scoring_service.generate_summary(
                    transcription=combined_transcription,
                    client_type=cd.get("client_type"),
                    service=cd.get("service"),
                    state=cd.get("state"),
                    city=cd.get("city"),
                    first_call=recent_call.get("first_call"),
                    rota_plan=cd.get("rota_plan"),
                )
                analysis_summary = (summary_response or {}).get("summary") or ""

                scores = await db.scoring_service.score_summary(analysis_summary)
                potential_score = (
                    (scores.get("potential_score") if isinstance(scores, dict) else getattr(scores, "potential_score", None))
                    or 0
                )

                # Log a compact event
                payload = {
                    "phone": phone_number,
                    "scores": scores if isinstance(scores, (dict, list, int, float, str, bool, type(None))) else str(scores),
                    "summary": analysis_summary,
                    "type": "receive",
                    "transcription": _truncate(combined_transcription, 1200),
                    "potential_score": potential_score,
                    "callrail_id": cd.get("callrail_id"),
                    "client_id": client_id_int,
                    "first_name": first_name,
                    "last_name": last_name,
                    "message": "Processed and created lead score in payload",
                }
                try:
                    logger.info("lead_score_event %s", json.dumps(payload, ensure_ascii=False, default=str))
                except Exception:
                    logger.info("lead_score_event %s", str(payload))

                # Queue for Laravel
                data_to_send.append({
                    "client_id": client_id_int,
                    "contact_number": phone_number,
                    "type": "receive",
                    "potential_score": potential_score,
                    "transcription": combined_transcription,  # RAW transcript
                    "description": analysis_summary,          # ANALYSIS summary
                    "callrail_id": cd.get("callrail_id"),
                    "first_name": first_name,
                    "last_name": last_name,
                    "status": cd.get("status") or None,
                    "is_scored": True,
                    "is_self": False,
                })

                processed_count += 1
                active_sessions[session_id]["processed"] = processed_count
                active_sessions[session_id]["details"].append({
                    "message": f"Queued RECEIVE for {phone_number}",
                    "status": "completed",
                })

            except Exception as e:
                logger.exception("Error processing phone %s: %s", phone_number, e)
                active_sessions[session_id]["details"].append({
                    "message": f"Error processing {phone_number}: {str(e)}",
                    "status": "error",
                })

        # 6) Send all queued leads to Laravel in one batch
        if data_to_send:
            try:
                result = await send_data_to_laravel(data_to_send, user_id=user_id) 

                ok = (result or {}).get("status") == "success"
                active_sessions[session_id]["details"].append({
                    "message": "Sent batch to Laravel" if ok else f"Laravel error: {(result or {}).get('body')}",
                    "status": "completed" if ok else "error",
                })
            except Exception as e:
                logger.exception("Failed sending data to Laravel: %s", e)
                active_sessions[session_id]["details"].append({
                    "message": f"Failed sending to Laravel: {str(e)}",
                    "status": "error",
                })

        # 7) Finalize progress
        active_sessions[session_id]["status"] = "completed"
        active_sessions[session_id]["processed"] = processed_count

        return {
            "status": "success",
            "processed_phone_numbers": processed_count,
        }

    except Exception as e:
        logger.exception("process_clients_background fatal error: %s", e)
        active_sessions[session_id]["status"] = "error"
        active_sessions[session_id]["error"] = str(e)
        return {"status": "error", "detail": str(e)}


HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "madam"}

def _clean_token(tok: str) -> str:
    return re.sub(r"[^\w'-]", "", tok).strip()

def _split_name(full: str | None):
    if not full:
        return None, None, None  # first, last, full
    # strip honorifics like "Dr."
    tokens = [_clean_token(t) for t in full.split() if _clean_token(t)]
    tokens = [t for t in tokens if t.lower().strip(".") not in HONORIFICS]
    if not tokens:
        return None, None, None
    if len(tokens) == 1:
        return tokens[0], None, tokens[0]
    first = tokens[0]
    last = " ".join(tokens[1:])
    return first, last, f"{first} {last}"

def _derive_fullname(call: dict, transcript: str | None) -> str | None:
    # Prefer structured fields if your source provides them
    for k in ("caller_name", "customer_name", "name", "from_name"):
        if call.get(k):
            return str(call.get(k)).strip()

    if not transcript:
        return None

    # Try common patterns in the transcript: "This is X", "I'm X", "I am X", "My name is X"
    # Allow 1-3 capitalized words to cover "Laura", "Laura Gasser", "Laura Anne Gasser"
    patterns = [
        r"\b(?:This is|I am|I'm|My name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, transcript)
        if m:
            return m.group(1).strip()

    return None

# put near top-level in your FastAPI file
ENUM_RECEIVE_DB_VALUE = "receive"  # ← IMPORTANT: match your DB's enum spelling

def _int_or_none(v):
    try:
        s = str(v).strip()
        return int(s) if s.isdigit() else None
    except Exception:
        return None

def normalize_lead_for_laravel(lead: dict) -> dict:
    # client_id -> int
    client_id = lead.get("client_id")
    try:
        client_id = int(client_id) if client_id is not None else None
    except Exception:
        client_id = None

    # required contact_number
    contact = lead.get("contact_number") or lead.get("phone_number") or ""
    contact = str(contact)[:32]

    # names: avoid NULL for NOT NULL cols
    first_name = (lead.get("first_name") or "").strip()
    last_name  = (lead.get("last_name") or "").strip()

    # type mapping
    t = ((lead.get("type") or "").strip().lower())
    if t not in ("receive", "receive", "miss"):
        t = "miss"
    if t == "receive":
        t = ENUM_RECEIVE_DB_VALUE  # map to DB spelling

    # CallRail ID: your DB column is INT → only send a number, else NULL
    callrail_id = _int_or_none(lead.get("callrail_id"))

    return {
        "client_id": client_id,
        "first_name": first_name,
        "last_name": last_name,
        "contact_number": contact,
        "email": lead.get("email") or None,
        "booking_id": lead.get("booking_id") or None,
        "callrail_id": callrail_id,
        "description": lead.get("description") or "",
        "status": (lead.get("status") or ""),
        "potential_score": lead.get("potential_score"),
        "transcription": lead.get("transcription") or "",
        "is_scored": bool(lead.get("is_scored", True)),
        "is_self": bool(lead.get("is_self", False)),
        "type": t,
    }


# helper
async def send_data_to_laravel(data, user_id: int):
    laravel_api_url = f"{apiurl}/api/save-client-lead"
    merged_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers or {}),  # if you have other headers; auth not required
    }

    if isinstance(data, list):
        payload = [normalize_lead_for_laravel(d) for d in data]
        for item in payload:
            item["user_id"] = user_id
    else:
        payload = normalize_lead_for_laravel(data)
        payload["user_id"] = user_id

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.post(laravel_api_url, json=payload, headers=merged_headers)

    logger.info("Laravel response: %s %s", response.status_code, response.text[:1000])
    if response.status_code in (200, 201, 202, 207):
        return {"status": "success", "message": "Data sent", "body": response.text}
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    return {"status": "error", "code": response.status_code, "body": body}

# Example usage of sending data after processing calls:
async def process_and_send_data():
    data = {
        "client_id": 123,
        "first_name": "John",
        "last_name": "Doe",
        "contact_number": "+123456789",
        "email": "john.doe@example.com",
        "booking_id": "abc123",
        "callrail_id": "xyz789",
        "description": "New client lead from call",
        "status": "new",
        "potential_score": 85,
        "transcription": "Client was interested in product A",
        "is_scored": True,
        "is_self": False
    }

    result = await send_data_to_laravel(data, user_id=user_id)
    print(result)


@router.post("/process-user-clients")
async def process_user_clients(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Process client scoring in background and return session ID for progress tracking"""
    try:
        # Parse JSON body
        body = await request.json()
        
        # Extract required fields
        client_ids = body.get("client_ids", [])
        session_id = body.get("session_id")
        user_id = body.get("user_id")
        
        # Validate input
        if not client_ids:
            raise HTTPException(status_code=422, detail="client_ids is required")
        
        if not session_id:
            raise HTTPException(status_code=422, detail="session_id is required")
        
        if not user_id:
            raise HTTPException(status_code=422, detail="user_id is required")
        
        print(f"Processing request: client_ids={client_ids}, session_id={session_id}, user_id={user_id}")
        
        # Start background processing
        background_tasks.add_task(
            process_clients_background,
            client_ids,
            session_id,
            user_id
        )
        
        return {
            "status": "success",
            "message": f"Started processing {len(client_ids)} clients",
            "session_id": session_id,
            "total_clients": len(client_ids)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON format: {str(e)}")
    except Exception as e:
        print(f"Error in process_user_clients: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

@router.get("/progress-stream/{session_id}")
async def progress_stream(session_id: str):
    """Server-Sent Events endpoint for real-time progress updates"""
    async def event_stream():
        try:
            while session_id in active_sessions:
                session_data = active_sessions[session_id]
                
                # Prepare progress data
                progress_data = {
                    "type": "progress",
                    "processed": session_data['processed'],
                    "total": session_data['total'],
                    "details": session_data['details'][-10:],  # Last 10 items
                    "percentage": round((session_data['processed'] / session_data['total']) * 100) if session_data['total'] > 0 else 0
                }
                
                yield f"data: {json.dumps(progress_data)}\n\n"
                
                # Check if completed or error
                if session_data['status'] == 'completed':
                    completion_data = {
                        "type": "completed",
                        "processed": session_data['processed'],
                        "total": session_data['total'],
                        "message": "Processing completed successfully",
                        "percentage":100
                    }
                    yield f"data: {json.dumps(completion_data)}\n\n"
                    # Clean up session
                    del active_sessions[session_id]
                    break
                elif session_data['status'] == 'error':
                    error_data = {
                        
                        "type": "error",
                        "message": session_data.get('error', 'Unknown error occurred')
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    # Clean up session
                    del active_sessions[session_id]
                    break
                
                # Wait before next update
                await asyncio.sleep(2)
                
        except Exception as e:
            error_data = {
                "type": "error",
                "message": f"Stream error: {str(e)}"
            }
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@router.get("/get-call-data")
async def get_call_data():
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            
            response = await client.get(f"{apiurl}/api/transcript",headers=headers)
            if response.status_code == 200:
                call_data = response.json()
                
                phone_groups = {}
                
                for call in call_data.get("data", []):
                    phone_number = call.get("phone_number") 
                    recording_url = call.get("call_recording")
                    
                    if not phone_number or not recording_url:
                        continue
                    
                    # Initialize phone group if not exists
                    if phone_number not in phone_groups:
                        phone_groups[phone_number] = {
                            "calls": [],
                            "transcriptions": [],
                            "call_data": call 
                        }
                    
                    phone_groups[phone_number]["calls"].append(call)
                
                # Process transcriptions for each phone number group
                FIXED_ACCOUNT_ID = "562206937"
                
                async def transcribe_call(recording_url):
                    call_id = extract_call_id_from_url(recording_url)
                    if not call_id:
                        return None
                    result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
                    return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
                
                # Process each phone number group
                results = []
                for phone_number, group_data in phone_groups.items():
                    print(f"Processing phone number: {phone_number} with {len(group_data['calls'])} calls")
                    
                    # Get transcriptions for all calls from this phone number
                    transcription_tasks = [
                        transcribe_call(call.get("call_recording")) 
                        for call in group_data["calls"] 
                        if call.get("call_recording")
                    ]
                    
                    transcriptions = await asyncio.gather(*transcription_tasks)
                    valid_transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
                    
                    if not valid_transcriptions:
                        print(f"No valid transcriptions for phone number: {phone_number}")
                        continue
                    
                    # Combine all transcriptions for this phone number
                    combined_transcription = "\n\n---\n\n".join(valid_transcriptions)
                    
                    # Check if lead score already exists for this phone number
                    existing_lead_score = await LeadScore.filter(phone=phone_number).first()
                    
                    # Get the most recent call data for context
                    recent_call = group_data["calls"][-1] 
                    
                    # Generate analysis summary
                    summary_response = await db.scoring_service.generate_summary(
                        transcription=combined_transcription,
                        client_type=recent_call.get("client_type"),  
                        service=recent_call.get("service"),
                        state=recent_call.get("state"),
                        city=recent_call.get("city"),
                        first_call=recent_call.get("first_call"),
                        rota_plan=recent_call.get("rota_plan"),  
                        previous_analysis=existing_lead_score.analysis_summary if existing_lead_score else None
                    )
                    analysis_summary = summary_response['summary']
                    
                    # Get scores for the analysis
                    scores = await db.scoring_service.score_summary(analysis_summary)
                    
                    # Update or create lead score record
                    if existing_lead_score:
                        # Update existing record
                        await LeadScore.filter(id=existing_lead_score.id).update(
                            analysis_summary=analysis_summary,
                            intent_score=scores.intent_score,
                            urgency_score=scores.urgency_score,
                            overall_score=scores.overall_score,
                            updated_at=datetime.now()
                        )
                        message = f"Updated existing lead score for phone {phone_number}"
                    else:
                        # Create new record
                        await LeadScore.create(
                            client_id=recent_call.get("client_id"),
                            name=recent_call.get("name"),
                            callrail_id=recent_call.get("callrail_id"),
                            
                            # callrail_id=None,

                            analysis_summary=analysis_summary,
                            phone=phone_number,
                            intent_score=scores.intent_score,
                            urgency_score=scores.urgency_score,
                            overall_score=scores.overall_score,
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        message = f"Created new lead score for phone {phone_number}"
                    
                    results.append({
                        "phone_number": phone_number,
                        "total_calls": len(group_data["calls"]),
                        "valid_transcriptions": len(valid_transcriptions),
                        "message": message,
                        "analysis": {
                            # "analysis_summary": analysis_summary,
                            "intent_score": scores.intent_score,
                            "urgency_score": scores.urgency_score,
                            "overall_score": scores.overall_score
                        }
                    })
                
                print(results)
                if results:
                    return {
                        "status": "success",
                        "processed_phone_numbers": len(results),
                        "results": results
                    }
                else:
                    return {"error": "No valid transcriptions found for any phone number."}
            else:
                error_text = response.text if hasattr(response, 'text') else str(response.status_code)
                raise HTTPException(status_code=response.status_code, detail=f"Failed to retrieve data: {error_text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Request error: {e}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/client-phone-score/")
async def get_client_phone_score(
    request: Request,
    client_ids: Optional[List[str]] = Query(None)
):
    try:
        if not client_ids:
            query_params = request.query_params
            client_ids = []
            
            i = 0
            while f"client_ids[{i}]" in query_params:
                client_ids.append(query_params[f"client_ids[{i}]"])
                i += 1
            
            if not client_ids:
                raise HTTPException(status_code=422, detail="client_ids parameter is required")

        lead_scores = await LeadScore.filter(client_id__in=client_ids).all()

        if not lead_scores:
            raise HTTPException(status_code=404, detail="Clients not found")
        
        print(lead_scores)
        return {
            "success": True,
            "message": "Lead scores retrieved successfully",
            "data": lead_scores
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "data": []
        }


@router.post("/rescore/{leadId}")
async def re_score_lead(leadId: str):
    try:
        print(f"Fetching lead with ID: {leadId}")
        lead_score = await LeadScore.filter(id=leadId).first()
        print(f"Fetching lead score shoaib: {lead_score}")
        
        
        
        if not lead_score:
            print(f"Lead score not found for ID: {leadId}")
            raise HTTPException(status_code=404, detail="Lead score not found")
        

        print(f"Generating new summary for lead ID: {leadId}")
        summary_response = await db.scoring_service.generate_summary(
            transcription=lead_score.analysis_summary,
            previous_analysis=lead_score.analysis_summary
        )

        print(f"Generated summary: {summary_response}")
        new_analysis_summary = summary_response['summary']

        print(f"Getting new scores for lead ID: {leadId}")
        updated_scores = await db.scoring_service.score_summary(new_analysis_summary)

        print(f"Updated scores: {updated_scores}")
        if not updated_scores:
            print(f"No scores returned for lead ID: {leadId}")
            raise HTTPException(status_code=500, detail="Failed to generate scores")

        print(f"Updating lead score record for ID: {leadId}")
        await LeadScore.filter(id=leadId).update(
            analysis_summary=new_analysis_summary,
            intent_score=updated_scores.intent_score,
            urgency_score=updated_scores.urgency_score,
            overall_score=updated_scores.overall_score,
            potential_score=updated_scores.potential_score,
            
            updated_at=datetime.now()
        )
        print(f"Lead score updated successfully for ID: {leadId}")

        return {
            "status": "success",
            "message": f"Lead ID {leadId} rescored successfully.",
            "data": {
                "id": leadId,
                "analysis_summary": new_analysis_summary,
                "intent_score": updated_scores.intent_score,
                "urgency_score": updated_scores.urgency_score,
                "overall_score": updated_scores.overall_score,
                "potential_score" : updated_scores.potential_score
            }
        }

    except Exception as e:
        print(f"Error rescoring lead {leadId}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to rescore lead: {str(e)}")

class SystemPrompt(BaseModel):
     system_prompt:str
     analytics_prompt:str
     summery_score:str
     hour:str
    
    
@router.post("/prompt")
async def system_prompt(prompt: SystemPrompt):
    try:
        obj = await SystemPrompts.filter().first()

        if obj:
            await obj.update_from_dict(prompt.dict(exclude_unset=True))
            await obj.save()
            return {"message": "Prompt updated successfully", "id": obj.id}
        else:
            obj = await SystemPrompts.create(**prompt.dict())
            return {"message": "Prompt created successfully", "id": obj.id}

    except Exception as e:
        print(f"Error while saving prompts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error while saving {str(e)}")
    
    
@router.get("/prompt")
async def system_prompt():
    try:
        system_prompt = await SystemPrompts.all().first()
        
        if system_prompt:
            return {"success": True, "message": "Prompt fetched successfully", "prompt": system_prompt}
        else:
            raise HTTPException(status_code=404, detail="Prompt not found")

    except Exception as e:
        print(f"Error while fetching prompt: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching prompt")
    