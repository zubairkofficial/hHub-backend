from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from helper.call_processor import CallProcessor
from helper.database import Database
from helper.lead_scoring import LeadScoringService
from models.lead_score import LeadScore
from tortoise.expressions import Q
import re
import tempfile
import aiohttp
from datetime import datetime

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

# Fixed account_id for all requests
FIXED_ACCOUNT_ID = "562206937"

def extract_call_id_from_url(url: str):
    # Regex for CallRail link
    match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
    if match:
        return match.group(1)
    return None

@router.get("/process-call-recording")
async def process_call_recording(recording_url: str = Query(...)):
    try:
        call_id = extract_call_id_from_url(recording_url)
        if not call_id:
            raise HTTPException(status_code=400, detail="Could not extract call_id from the link.")
        
        # Check if already processed in lead_score
        existing_record = await db.first('lead_score', {'call_id': call_id})
        if existing_record:
            return {
                'status': 'success',
                'transcription': existing_record['transcription'],
                'processed_at': existing_record.get('processed_at').isoformat() if existing_record.get('processed_at') else None
            }

        processor = CallProcessor()
        result = await processor.process_call(account_id=FIXED_ACCOUNT_ID, call_id=call_id)
        
        if result.get('status') == 'error' or 'error' in result:
            raise HTTPException(status_code=500, detail=result.get('error'))

        # Store in lead_score table (only valid columns)
        lead_score_data = {
            'call_id': call_id,
            'transcription': result.get('transcription'),
            'created_at': datetime.now()
        }
        
        await db.insert('lead_score', lead_score_data)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/lead-score")
async def get_lead_scores(limit: int = 100):
    """
    Get all lead scores with their transcriptions
    """
    try:
        data = await db.get_table_data('lead_score', limit)
        # Ensure transcription is included in the response
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-lead-scores")
async def sync_lead_scores():
    """
    Sync data from callrails to lead_score table
    """
    try:
        await db.create_lead_score_table()
        await db.sync_callrail_to_lead_score()
        return {
            "status": "success",
            "message": "Lead scores synchronized successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/lead-score/batch-transcribe")
async def batch_transcribe_lead_score():
    try:
        await db.batch_transcribe_lead_score()
        return {"status": "success", "message": "Batch transcription completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calculate_priority_and_level(overall_score):
    if overall_score is None:
        return "Very Low", 0
    if overall_score >= 90:
        return "Critical", 4
    elif overall_score >= 80:
        return "High", 3
    elif overall_score >= 70:
        return "Medium", 2
    elif overall_score >= 60:
        return "Low", 1
    else:
        return "Very Low", 0

@router.get("/lead-score/sync-transcribe-score")
async def sync_transcribe_score():
    try:
        print("[sync-transcribe-score] Syncing new data from callrails to lead_score...")
        new_rows_count = await db.sync_callrail_to_lead_score()
        print(f"[sync-transcribe-score] Synced {new_rows_count} new rows.")

        print("[sync-transcribe-score] Transcribing rows with null transcription...")
        transcribed_count = await db.batch_transcribe_lead_score()
        print(f"[sync-transcribe-score] Transcribed {transcribed_count} rows.")

        print("[sync-transcribe-score] Scoring/prioritizing rows as needed...")
        scoring_service = LeadScoringService()
        rows = await LeadScore.all()
        scored_count = 0
        prioritized_count = 0

        for row in rows:
            update_data = {}
            needs_score = (
                row.tone_score is None or
                row.intent_score is None or
                row.urgency_score is None or
                row.overall_score is None
            )
            needs_priority = (row.priority is None or row.priority_level is None)

            if not row.transcription:
                print(f"[sync-transcribe-score] Skipping scoring/prioritizing for row {getattr(row, 'id', 'unknown')}: no transcription.")
                continue

            if needs_score:
                try:
                    analysis = await scoring_service.analyze_transcription(row.transcription)
                    update_data.update(
                        tone_score=analysis.tone_score,
                        intent_score=analysis.intent_score,
                        urgency_score=analysis.urgency_score,
                        overall_score=analysis.overall_score,
                    )
                    prio, prio_lvl = getattr(analysis, 'priority', None), getattr(analysis, 'priority_level', None)
                    if prio is None or prio_lvl is None:
                        prio, prio_lvl = calculate_priority_and_level(analysis.overall_score)
                    update_data.update(priority=prio, priority_level=prio_lvl)
                    scored_count += 1
                    prioritized_count += 1
                except Exception as score_exc:
                    print(f"[sync-transcribe-score] Error scoring row {row.id}: {score_exc}. Setting scores and priority to default.")
                    update_data.update(
                        tone_score=0,
                        intent_score=0,
                        urgency_score=0,
                        overall_score=0,
                        priority="Very Low",
                        priority_level=0
                    )
                    scored_count += 1
                    prioritized_count += 1
            elif needs_priority:
                prio, prio_lvl = calculate_priority_and_level(row.overall_score)
                update_data.update(priority=prio, priority_level=prio_lvl)
                prioritized_count += 1

            if update_data:
                await LeadScore.filter(id=row.id).update(**update_data)

        print(f"[sync-transcribe-score] Scored {scored_count} rows, prioritized {prioritized_count} rows.")

        if new_rows_count == 0 and transcribed_count == 0 and scored_count == 0 and prioritized_count == 0:
            return {
                "status": "success",
                "message": "No new data to sync, transcribe, score, or prioritize."
            }
        return {
            "status": "success",
            "message": f"Sync, transcription, scoring, and prioritization completed. New rows: {new_rows_count}, Transcribed: {transcribed_count}, Scored: {scored_count}, Prioritized: {prioritized_count}"
        }
    except Exception as e:
        print(f"[sync-transcribe-score] Unhandled error: {e}")
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }


@router.get("/tables/{table_name}/data")
async def get_table_data(table_name: str, limit: int = 100):
    """
    Get data from a specific table with optional limit
    """
    try:
        data = await db.get_table_data(table_name, limit)
        return {
            "table_name": table_name,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

