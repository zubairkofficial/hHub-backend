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


# @router.post("/lead-score/analysis")
# async def sync_transcribe_score():
#     try:
#         print("[sync-transcribe-score] Syncing new data from callrails to lead_score...")
#         new_rows_count = await db.sync_callrail_to_lead_score()
#         print(f"[sync-transcribe-score] Synced {new_rows_count} new rows.")

#         print("[sync-transcribe-score] Transcribing rows with null transcription...")
#         transcribed_count = await db.batch_transcribe_lead_score()
#         print(f"[sync-transcribe-score] Transcribed {transcribed_count} rows.")

#         print("[sync-transcribe-score] Scoring rows with null scores...")
#         scoring_service = LeadScoringService()
#         rows = await LeadScore.filter(
#             Q(tone_score__isnull=True) |
#             Q(intent_score__isnull=True) |
#             Q(urgency_score__isnull=True) |
#             Q(overall_score__isnull=True)
#         ).all()
#         scored_count = 0
#         for row in rows:
#             if not row.transcription:
#                 print(f"[sync-transcribe-score] Skipping scoring for row {getattr(row, 'id', 'unknown')}: no transcription.")
#                 continue
#             try:
#                 analysis = await scoring_service.analyze_transcription(row.transcription)
#                 await LeadScore.filter(id=row.id).update(
#                     tone_score=analysis.tone_score,
#                     intent_score=analysis.intent_score,
#                     urgency_score=analysis.urgency_score,
#                     overall_score=analysis.overall_score
#                 )
#                 scored_count += 1
#             except Exception as score_exc:
#                 print(f"[sync-transcribe-score] Error scoring row {getattr(row, 'id', 'unknown')}: {score_exc}. Setting scores to 0.")
#                 await LeadScore.filter(id=row.id).update(
#                     tone_score=0,
#                     intent_score=0,
#                     urgency_score=0,
#                     overall_score=0
#                 )
#                 scored_count += 1
#                 continue
#         print(f"[sync-transcribe-score] Scored {scored_count} rows.")

#         total_rows = await LeadScore.all().count()
#         print(f"[sync-transcribe-score] Total rows in lead_score: {total_rows}")

#         if new_rows_count == 0 and transcribed_count == 0 and scored_count == 0:
#             return {
#                 "status": "success",
#                 "message": "No new data to sync, transcribe, or score."
#             }
#         return {
#             "status": "success",
#             "message": f"Sync, transcription, and scoring completed. New rows: {new_rows_count}, Transcribed: {transcribed_count}, Scored: {scored_count}, Total rows: {total_rows}"
#         }
#     except Exception as e:
#         print(f"[sync-transcribe-score] Unhandled error: {e}")
#         return {
#             "status": "error",
#             "message": f"An error occurred: {str(e)}"
#         }
@router.post("/process-client-calls")
async def process_client_calls(request: ClientRequest):
    """
    Process all calls for a specific client:
    1. Get all call recordings from callrails for this client
    2. Process each recording to get transcription and analysis
    3. Calculate aggregate scores
    4. Update or create lead_score record
    """
    try:
        result = await db.process_client_calls(request.client_id)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/lead-score/sorted")
async def get_lead_scores_sorted():
    try:
        rows = await LeadScore.all()
        # Sort rows by overall_score in descending order
        rows = [dict(row) for row in rows]
        for position, row in enumerate(rows, 1):
            row['position'] = position

        print(f"[lead-score/sorted] Total rows: {len(rows)}")
        for idx, row in enumerate(rows, 1):
            print(f"{idx}. ID: {row['id']}, Overall Score: {row['overall_score']}")
        
        return {
            "status": "success",
            "data": rows
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }

def extract_call_id_from_url(url: str):
    match = re.search(r'/calls/([A-Za-z0-9]+)/', url)
    if match:
        return match.group(1)
    return None

# @router.post("/lead-score/manual-analysis")
# async def manual_analysis(payload: List[Dict[str, Any]] = Body(...)):
#     try:
#         processor = CallProcessor()
#         scoring_service = LeadScoringService()
#         results = []
#         FIXED_ACCOUNT_ID = "562206937"
#         for item in payload:
#             call_recording = item.get("call_recording")
#             if not call_recording:
#                 results.append({"status": "error", "message": "No call_recording URL provided", "item": item})
#                 continue

#             call_id = extract_call_id_from_url(call_recording)
#             if not call_id:
#                 results.append({"status": "error", "message": "Could not extract call_id from call_recording URL", "item": item})
#                 continue

#             # Transcribe using process_call (which uses account_id, call_id, and token from env)
#             transcription_result = await processor.process_call(
#                 account_id=FIXED_ACCOUNT_ID,
#                 call_id=call_id
#             )
#             transcription = transcription_result.get("transcription")
#             if not transcription:
#                 results.append({"status": "error", "message": "Transcription failed", "item": item})
#                 continue

#             # Score
#             try:
#                 analysis = await scoring_service.analyze_transcription(transcription)
#                 # Save to lead_score, using all fields from item if present, else None
#                 await LeadScore.create(
#                     callrail_id=item.get("callrail_id"),
#                     call_recording=call_recording,
#                     name=item.get("name"),
#                     phone_number=item.get("phone_number"),
#                     date=item.get("date"),
#                     source_type=item.get("source_type"),
#                     duration=item.get("duration"),
#                     country=item.get("country"),
#                     state=item.get("state"),
#                     city=item.get("city"),
#                     answer=item.get("answer"),
#                     first_call=item.get("first_call"),
#                     lead_status=item.get("lead_status"),
#                     call_highlight=item.get("call_highlight"),
#                     transcription=transcription,
#                     tone_score=analysis.tone_score,
#                     intent_score=analysis.intent_score,
#                     urgency_score=analysis.urgency_score,
#                     overall_score=analysis.overall_score,
#                     callrail_record_id=None  # Explicitly set to None for manual entries
#                 )
#                 results.append({"status": "success", "item": item, "scores": {
#                     "tone_score": analysis.tone_score,
#                     "intent_score": analysis.intent_score,
#                     "urgency_score": analysis.urgency_score,
#                     "overall_score": analysis.overall_score,
#                 }})
#             except Exception as score_exc:
#                 results.append({"status": "error", "message": f"Scoring failed: {score_exc}", "item": item})
#         return {"status": "completed", "results": results}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}



