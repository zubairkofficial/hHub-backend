import asyncio
from datetime import datetime
from helper.database import Database
from helper.call_processor import CallProcessor
from helper.lead_scoring import LeadScoringService
from models.lead_score import LeadScore
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG

# Initialize helpers
db = Database()
processor = CallProcessor()
scoring_service = LeadScoringService()

async def process_unprocessed_callrails():
    # Initialize Tortoise ORM
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    try:
        # 1. Get all unprocessed callrails rows
        rows = await db.fetch("SELECT * FROM callrails WHERE is_processed = FALSE")
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
                previous_analysis=None
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
            # 6. Mark all these calls as processed
            call_ids = [call["id"] for call in calls]
            await db.execute(
                f"UPDATE callrails SET is_processed = TRUE WHERE id IN ({','.join(['%s']*len(call_ids))})",
                tuple(call_ids)
            )
            print(f"[{datetime.now()}] Marked calls as processed for phone number: {phone_number}")
    finally:
        await Tortoise.close_connections() 