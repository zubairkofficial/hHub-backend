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
from typing import List, Optional, Dict, Any
from fastapi import Query
from pydantic import BaseModel
import json
import uuid
from collections import defaultdict
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()


router = APIRouter()
model = whisper.load_model("base")
db = Database()

apiurl = os.getenv("API_URL")


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

async def process_clients_background(client_ids: List[str], session_id: str, user_id: int):
    """Background task to process clients and update progress"""
    try:
        # Initialize session tracking
        active_sessions[session_id] = {
            'total': len(client_ids),
            'processed': 0,
            'details': [],
            'status': 'processing'
        }
        
        # Fetch call data for the specific client IDs
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{apiurl}/api/transcript")
            if response.status_code != 200:
                raise Exception(f"Failed to fetch call data: {response.status_code}")
            
            call_data = response.json()
            
            # Filter calls by client_ids
            filtered_calls = [
                call for call in call_data.get("data", [])
                if call.get("client_id") in client_ids
            ]
            
            # Group calls by phone number
            phone_groups = {}
            for call in filtered_calls:
                phone_number = call.get("phone_number")
                recording_url = call.get("call_recording")
                
                if not phone_number or not recording_url:
                    continue
                
                if phone_number not in phone_groups:
                    phone_groups[phone_number] = {
                        "calls": [],
                        "transcriptions": [],
                        "call_data": call
                    }
                
                phone_groups[phone_number]["calls"].append(call)
            
            # Process each phone number group
            FIXED_ACCOUNT_ID = "562206937"
            processed_count = 0
            
            async def transcribe_call(recording_url):
                call_id = extract_call_id_from_url(recording_url)
                if not call_id:
                    return None
                result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
                return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
            
            for phone_number, group_data in phone_groups.items():
                try:
                    # Update progress
                    active_sessions[session_id]['details'].append({
                        'message': f'Processing phone number: {phone_number}',
                        'status': 'processing'
                    })
                    
                    # Get transcriptions for all calls from this phone number
                    transcription_tasks = [
                        transcribe_call(call.get("call_recording"))
                        for call in group_data["calls"]
                        if call.get("call_recording")
                    ]
                    
                    transcriptions = await asyncio.gather(*transcription_tasks)
                    valid_transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
                    
                    if not valid_transcriptions:
                        active_sessions[session_id]['details'].append({
                            'message': f'No valid transcriptions for {phone_number}',
                            'status': 'skipped'
                        })
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
                        await LeadScore.filter(id=existing_lead_score.id).update(
                            analysis_summary=analysis_summary,
                            intent_score=scores.intent_score,
                            urgency_score=scores.urgency_score,
                            overall_score=scores.overall_score,
                            updated_at=datetime.now()
                        )
                        message = f"Updated lead score for {phone_number}"
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
                        message = f"Created lead score for {phone_number}"
                    
                    processed_count += 1
                    
                    # Update progress
                    active_sessions[session_id]['processed'] = processed_count
                    active_sessions[session_id]['details'].append({
                        'message': message,
                        'status': 'completed'
                    })
                    
                except Exception as e:
                    active_sessions[session_id]['details'].append({
                        'message': f'Error processing {phone_number}: {str(e)}',
                        'status': 'error'
                    })
            
            # Mark as completed
            active_sessions[session_id]['status'] = 'completed'
            active_sessions[session_id]['processed'] = len(phone_groups)
            
    except Exception as e:
        # Mark as error
        active_sessions[session_id]['status'] = 'error'
        active_sessions[session_id]['error'] = str(e)

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
            response = await client.get(f"{apiurl}/api/transcript")
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
                            callrail_id=None,
                            name = recent_call.get("name"),
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
        
        
           
        
        
        
        
        
        
        
        
        
        
        
        