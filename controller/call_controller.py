from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from helper.call_processor import CallProcessor
from helper.database import Database
from helper.lead_scoring import LeadScoringService
from models.lead_score import LeadScore
from tortoise.expressions import Q
from datetime import datetime
from fastapi import Body
import re
import asyncio

router = APIRouter()
db = Database()

class CallRecordingRequest(BaseModel):
    audio_url: str
    call_id: Optional[str] = None

class CallRecordingResponse(BaseModel):
    status: str
    transcription: Optional[str] = None
    language: Optional[str] = None
    error: Optional[str] = None
    processed_at: Optional[str] = None

class ClientSyncRequest(BaseModel):
    client_id: str

class ClientRequest(BaseModel):
    client_id: str

class CallRecording(BaseModel):
    callrail_id: str
    call_recording: str
    name: Optional[str] = None
    date: Optional[datetime] = None
    source_type: Optional[str] = None
    phone_number: Optional[str] = None
    duration: Optional[int] = None
    country: Optional[str] = None
    answer: Optional[int] = None
    lead_status: Optional[int] = None
    call_highlight: Optional[int] = None

class ClientIdRequest(BaseModel):
    client_id: str

class ManualCallRecording(BaseModel):
    call_recording: str
    callrail_id: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    first_call: Optional[int] = 0

class ManualLeadScoreRequest(BaseModel):
    client_id: Optional[str] = None  # can be null
    client_type: Optional[str] = None
    rota_plan: Optional[str] = None
    service: Optional[str] = None
    calls: List[ManualCallRecording]

def extract_call_id_from_url(url: str):
    match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
    if match:
        return match.group(1)
    return None

# @router.post("/analyze-client-calls")
# async def analyze_client_calls():
#     try:
#         # Get all client IDs with calls
#         client_ids = await db.get_all_client_ids_with_calls()
        
#         if not client_ids:
#             return {"status": "success", "message": "No clients with calls found to analyze.", "analysis": None}
        
#         results = {}
        
#         for client_id in client_ids:
#             print(f"==== Starting analysis for client: {client_id} ====")
#             try:
#                 context = await db.get_client_context_and_calls(client_id)
#                 calls = context['calls']
                
#                 if not calls:
#                     print(f"No calls found for client {client_id}. Skipping analysis.")
#                     results[client_id] = {"status": "skipped", "message": "No calls found for this client.", "analysis": None}
#                     continue
                
#                 # Get existing lead score if any
#                 existing_lead_score = await LeadScore.filter(client_id=client_id).first()
                
#                 FIXED_ACCOUNT_ID = "562206937"
#                 async def transcribe_call(call):
#                     call_recording = call.get('call_recording')
#                     if not call_recording or not isinstance(call_recording, str) or not call_recording.strip():
#                         return None
#                     call_id = extract_call_id_from_url(call_recording)
#                     if not call_id:
#                         return None
#                     result = await db.processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
#                     return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
                
#                 transcriptions = await asyncio.gather(*[transcribe_call(call) for call in calls])
#                 transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
                
#                 if not transcriptions:
#                     print(f"No valid transcriptions for client {client_id}. Skipping analysis.")
#                     results[client_id] = {"status": "skipped", "message": "No valid transcriptions.", "analysis": None}
#                     continue
                
#                 combined_transcription = "\n\n---\n\n".join(transcriptions)
#                 if not combined_transcription or not isinstance(combined_transcription, str) or not combined_transcription.strip():
#                      print(f"Combined transcription is empty for client {client_id}. Skipping analysis.")
#                      results[client_id] = {"status": "skipped", "message": "Combined transcription is empty.", "analysis": None}
#                      continue

#                 # Print data sent to OpenAI for analysis summary
#                 print(f"==== DATA SENT TO OPENAI FOR ANALYSIS SUMMARY for client {client_id} ====")
#                 print("New transcriptions:", repr(combined_transcription))
#                 if existing_lead_score:
#                     print("Previous analysis:", repr(existing_lead_score.analysis_summary))
#                 print("Context:", {
#                     "client_type": context['client_type'],
#                     "service": context['service'],
#                     "state": calls[-1].get('state'),
#                     "city": calls[-1].get('city'),
#                     "first_call": calls[-1].get('first_call'),
#                     "rota_plan": context['rota_plan']
#                 })

#                 # Step 1: Get analysis summary
#                 summary_response = await db.scoring_service.generate_summary(
#                     transcription=combined_transcription,
#                     client_type=context['client_type'],
#                     service=context['service'],
#                     state=calls[-1].get('state'),
#                     city=calls[-1].get('city'),
#                     first_call=calls[-1].get('first_call'),
#                     rota_plan=context['rota_plan'],
#                     previous_analysis=existing_lead_score.analysis_summary if existing_lead_score else None
#                 )
#                 analysis_summary = summary_response['summary']

#                 # Print analysis summary sent to OpenAI for scoring
#                 print(f"==== ANALYSIS SUMMARY SENT TO OPENAI FOR SCORING for client {client_id} ====")
#                 print("Analysis summary:", repr(analysis_summary))

#                 # Step 2: Score the summary
#                 scores = await db.scoring_service.score_summary(analysis_summary)

#                 if existing_lead_score:
#                     # Update existing record
#                     await LeadScore.filter(client_id=client_id).update(
#                         analysis_summary=analysis_summary,
#                         intent_score=scores.intent_score,
#                         urgency_score=scores.urgency_score,
#                         overall_score=scores.overall_score,
#                         updated_at=datetime.now()
#                     )
#                     message = f"Updated existing lead score for client {client_id}"
#                 else:
#                     # Create new record
#                     await LeadScore.create(
#                         client_id=client_id,
#                         callrail_id=None, # Assuming callrail_id for the lead_score record itself might not be applicable when aggregating
#                         analysis_summary=analysis_summary,
#                         intent_score=scores.intent_score,
#                         urgency_score=scores.urgency_score,
#                         overall_score=scores.overall_score,
#                         created_at=datetime.now(),
#                         updated_at=datetime.now()
#                     )
#                     message = f"Created new lead score for client {client_id}"
                
#                 results[client_id] = {
#                     "status": "success",
#                     "message": message,
#                     "analysis": {
#                         "analysis_summary": analysis_summary,
#                         "intent_score": scores.intent_score,
#                         "urgency_score": scores.urgency_score,
#                         "overall_score": scores.overall_score
#                     }
#                 }
#                 print(f"==== Finished analysis for client: {client_id} ====")

#             except Exception as client_e:
#                 print(f"Exception processing client {client_id}: {client_e}")
#                 import traceback
#                 traceback.print_exc()
#                 results[client_id] = {"status": "error", "message": str(client_e), "analysis": None}
        
#         return {"status": "completed", "message": f"Processed analysis for {len(client_ids)} clients.", "results": results}

#     except Exception as e:
#         import traceback
#         print("Exception in analyze_client_calls endpoint:", e)
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=str(e))

@router.post("/manual-lead-score")
async def manual_lead_score(request: ManualLeadScoreRequest):
    # Early return if no calls
    if not request.calls:
        return {"status": "success", "message": "No calls provided.", "analysis": None}
    
    # Get existing lead score if client_id provided
    existing_lead_score = None
    if request.client_id:
        existing_lead_score = await LeadScore.filter(client_id=request.client_id).first()
    
    # Process call transcriptions
    FIXED_ACCOUNT_ID = "562206937"
    async def transcribe_call(call):
        if not call.call_recording or not isinstance(call.call_recording, str) or not call.call_recording.strip():
            return None
        call_id = extract_call_id_from_url(call.call_recording)
        if not call_id:
            return None
        result = await db.processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
        return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
    
    # Get all valid transcriptions
    transcriptions = await asyncio.gather(*[transcribe_call(call) for call in request.calls])
    transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
    if not transcriptions:
        return {"status": "success", "message": "No valid transcriptions.", "analysis": None}
    
    # Combine transcriptions
    combined_transcription = "\n\n---\n\n".join(transcriptions)
    if not combined_transcription or not isinstance(combined_transcription, str) or not combined_transcription.strip():
        return {"status": "success", "message": "No valid transcriptions.", "analysis": None}

    # Log data being sent to OpenAI
    print("==== DATA SENT TO OPENAI FOR ANALYSIS SUMMARY ====")
    if existing_lead_score:
        print("Previous analysis:", repr(existing_lead_score.analysis_summary))
    print("Context:", {
        "client_type": request.client_type,
        "service": request.service,
        "state": request.calls[-1].state if request.calls else None,
        "city": request.calls[-1].city if request.calls else None,
        "first_call": request.calls[-1].first_call if request.calls else None,
        "rota_plan": request.rota_plan
    })

    # Generate new analysis summary
    summary_response = await db.scoring_service.generate_summary(
        transcription=combined_transcription,
        client_type=request.client_type,
        service=request.service,
        state=request.calls[-1].state if request.calls else None,
        city=request.calls[-1].city if request.calls else None,
        first_call=request.calls[-1].first_call if request.calls else None,
        rota_plan=request.rota_plan,
        previous_analysis=existing_lead_score.analysis_summary if existing_lead_score else None
    )
    analysis_summary = summary_response['summary']

    # Log analysis summary
    print("==== ANALYSIS SUMMARY SENT TO OPENAI FOR SCORING ====")

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
        message = f"Updated existing lead score for client {request.client_id}"
    else:
        # Create new record
        await LeadScore.create(
            client_id=request.client_id,
            callrail_id=None,
            analysis_summary=analysis_summary,
            intent_score=scores.intent_score,
            urgency_score=scores.urgency_score,
            overall_score=scores.overall_score,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        message = f"Created new lead score for client {request.client_id}"

    # Return response
    return {
        "status": "success",
        "message": message,
        "analysis": {
            "analysis_summary": analysis_summary,
            "intent_score": scores.intent_score,
            "urgency_score": scores.urgency_score,
            "overall_score": scores.overall_score
        }
    }


@router.get("/lead-score/sorted")
async def get_lead_scores_sorted():
    try:
        rows = await LeadScore.all().order_by('-overall_score')
        # Sort rows by overall_score in descending order
        rows = [dict(row) for row in rows]
        for position, row in enumerate(rows, 1):
            row['position'] = position
        return {
            "status": "success",
            "data": rows
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }


