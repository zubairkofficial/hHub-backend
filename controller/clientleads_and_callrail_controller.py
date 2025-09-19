from fastapi import APIRouter, Request
from datetime import datetime
import asyncio

# Import only the new "no store" helper
from helper.transcription_helper import process_unprocessed_callrails_no_store

router = APIRouter()

@router.post("/fetch-data")
async def fetch_client_leads_and_callrail(request: Request):
    try:
        payload = await request.json()

        print("Payload from Laravel:", payload)

        # FIX: payload["data"] is already a list
        call_records = payload.get("data", [])

        print("First record type:", type(call_records[0]) if call_records else None)

        if not call_records:
            return {
                "status": "error",
                "message": "No call records provided",
                "data": []
            }

        result = await process_unprocessed_callrails_no_store(call_records)
        return {
            "status": "success",
            "message": "Task completed successfully.",
            "data": result.get("data", [])
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Failed to process client and CallRail data: {str(e)}",
            "data": []
        }
