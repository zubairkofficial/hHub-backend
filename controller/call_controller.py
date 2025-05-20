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
    state: Optional[str] = None
    city: Optional[str] = None
    first_call: Optional[bool] = None

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

@router.post("/analyze-client-calls")
async def analyze_client_calls(request: ClientIdRequest):
    try:
        client_id = request.client_id
        context = await db.get_client_context_and_calls(client_id)
        calls = context['calls']
        if not calls:
            return {"status": "success", "message": "No calls found for this client.", "analysis": None}
        FIXED_ACCOUNT_ID = "562206937"
        async def transcribe_call(call):
            call_recording = call.get('call_recording')
            if not call_recording or not isinstance(call_recording, str) or not call_recording.strip():
                return None
            call_id = db.extract_call_id_from_url(call_recording)
            if not call_id:
                return None
            result = await db.processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
            return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
        transcriptions = await asyncio.gather(*[transcribe_call(call) for call in calls])
        transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
        if not transcriptions:
            return {"status": "success", "message": "No valid transcriptions.", "analysis": None}
        combined_transcription = "\n\n---\n\n".join(transcriptions)
        if not combined_transcription or not isinstance(combined_transcription, str) or not combined_transcription.strip():
            return {"status": "success", "message": "No valid transcriptions.", "analysis": None}
        # Print data sent to OpenAI for analysis summary
        print("==== DATA SENT TO OPENAI FOR ANALYSIS SUMMARY ====")
        print("Combined transcription:", repr(combined_transcription))
        print("Context:", {
            "client_type": context['client_type'],
            "service": context['service'],
            "state": calls[-1].get('state'),
            "city": calls[-1].get('city'),
            "first_call": calls[-1].get('first_call'),
            "rota_plan": context['rota_plan']
        })
        # Step 1: Get analysis summary
        summary_response = await db.scoring_service.generate_summary(
            transcription=combined_transcription,
            client_type=context['client_type'],
            service=context['service'],
            state=calls[-1].get('state'),
            city=calls[-1].get('city'),
            first_call=calls[-1].get('first_call'),
            rota_plan=context['rota_plan']
        )
        analysis_summary = summary_response['summary']
        # Print analysis summary sent to OpenAI for scoring
        print("==== ANALYSIS SUMMARY SENT TO OPENAI FOR SCORING ====")
        print("Analysis summary:", repr(analysis_summary))
        # Save or update lead_score with summary
        existing = await LeadScore.filter(client_id=client_id).first()
        if existing:
            await LeadScore.filter(id=existing.id).update(analysis_summary=analysis_summary, updated_at=datetime.now())
        else:
            await LeadScore.create(client_id=client_id, callrail_id=None, analysis_summary=analysis_summary, created_at=datetime.now(), updated_at=datetime.now())
        # Step 2: Score the summary
        scores = await db.scoring_service.score_summary(analysis_summary)
        await LeadScore.filter(client_id=client_id).update(
            intent_score=scores.intent_score,
            urgency_score=scores.urgency_score,
            overall_score=scores.overall_score,
            updated_at=datetime.now()
        )
        return {
            "status": "success",
            "message": f"Processed {len(transcriptions)} calls for client {client_id}",
            "analysis": {
                "analysis_summary": analysis_summary,
                "intent_score": scores.intent_score,
                "urgency_score": scores.urgency_score,
                "overall_score": scores.overall_score
            }
        }
    except Exception as e:
        import traceback
        print("Exception in analyze_client_calls:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
        
    
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
    
    
@router.post("/manual-lead-score")
async def manual_lead_score(request: ManualLeadScoreRequest):
    calls = request.calls
    if not calls:
        return {"status": "success", "message": "No calls provided.", "analysis": None}
    FIXED_ACCOUNT_ID = "562206937"
    async def transcribe_call(call):
        call_recording = call.call_recording
        if not call_recording or not isinstance(call_recording, str) or not call_recording.strip():
            return None
        call_id = db.extract_call_id_from_url(call_recording)
        if not call_id:
            return None
        result = await db.processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
        return result['transcription'] if result and 'transcription' in result and result['transcription'] else None
    transcriptions = await asyncio.gather(*[transcribe_call(call) for call in calls])
    transcriptions = [t for t in transcriptions if t and isinstance(t, str) and t.strip()]
    if not transcriptions:
        return {"status": "success", "message": "No valid transcriptions.", "analysis": None}
    combined_transcription = "\n\n---\n\n".join(transcriptions)
    if not combined_transcription or not isinstance(combined_transcription, str) or not combined_transcription.strip():
        return {"status": "success", "message": "No valid transcriptions.", "analysis": None}
    # Print data sent to OpenAI for analysis summary
    print("==== DATA SENT TO OPENAI FOR ANALYSIS SUMMARY (MANUAL) ====")
    print("Combined transcription:", repr(combined_transcription))
    print("Context:", {
        "client_type": request.client_type,
        "service": request.service,
        "state": calls[-1].state if calls else None,
        "city": calls[-1].city if calls else None,
        "first_call": calls[-1].first_call if calls else None,
        "rota_plan": request.rota_plan
    })
    # Step 1: Get analysis summary
    summary_response = await db.scoring_service.generate_summary(
        transcription=combined_transcription,
        client_type=request.client_type,
        service=request.service,
        state=calls[-1].state if calls else None,
        city=calls[-1].city if calls else None,
        first_call=calls[-1].first_call if calls else None,
        rota_plan=request.rota_plan
    )
    analysis_summary = summary_response['summary']
    print("==== ANALYSIS SUMMARY SENT TO OPENAI FOR SCORING (MANUAL) ====")
    print("Analysis summary:", repr(analysis_summary))
    # Step 2: Score the summary
    scores = await db.scoring_service.score_summary(analysis_summary)
    
    # Check if lead score exists for this client_id
    existing_lead_score = None
    if request.client_id:
        existing_lead_score = await LeadScore.filter(client_id=request.client_id).first()
    
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




