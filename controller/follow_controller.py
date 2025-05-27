from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict, Any
from models.followup_prediction import FollowupPrediction
from helper.follow_helper import get_unprocessed_callrail_dates_for_client, predict_followup_time, FollowupPredictionResponse
from helper.database import Database
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()


class FollowupPredictionRequest(BaseModel):
    client_id: int
    call_dates: List[str]  # List of dates in "YYYY-MM-DD HH:MM:SS" format

# @router.post("/predict-followup/{client_id}")
# async def predict_followup_time_endpoint(
#     client_id: int,
#     db: Database = Depends()
# ):
#     try:
#         print(f"Starting predict_followup_time_endpoint for client_id: {client_id}")
#         # 1. Fetch unprocessed CallRail data for the client (pass the db instance)
#         print("Calling get_unprocessed_callrail_dates_for_client...")
#         unprocessed_calls = await get_unprocessed_callrail_dates_for_client(db, client_id)
#         print(f"Received unprocessed_calls: {unprocessed_calls}")

#         if not unprocessed_calls:
#             print(f"No unprocessed_calls found for client_id: {client_id}. Returning message.")
#             return {"message": f"No new unprocessed CallRail data found for client_id {client_id}."}

#         # Extract call dates (they are dictionaries from db.fetch)
#         print(f"Extracting call dates from {len(unprocessed_calls)} calls...")
#         call_dates = [call['date'] for call in unprocessed_calls] # Use 'date' as per DB image
#         print(f"Extracted call_dates: {call_dates}")

#         # 2. Get follow-up time prediction from OpenAI
#         print(f"Calling predict_followup_time for client_id {client_id} with {len(call_dates)} dates...")
#         predicted_time_str = await predict_followup_time(call_dates, client_id)
#         print(f"Received predicted_time_str: {predicted_time_str}")

#         if not predicted_time_str:
#             print(f"predict_followup_time returned None for client_id: {client_id}. Raising HTTPException.")
#             raise HTTPException(status_code=500, detail="Failed to get follow-up time prediction from OpenAI.")

#         # Convert predicted time string to datetime object for saving
#         print(f"Converting predicted_time_str to datetime: {predicted_time_str}")
#         predicted_time = datetime.strptime(predicted_time_str, "%Y-%m-%d %H:%M:%S")
#         print(f"Converted predicted_time: {predicted_time}")

#         # 3. Create a NEW prediction record in the database
#         print(f"Creating FollowupPrediction record for client_id {client_id}...")
#         followup_prediction = await FollowupPrediction.create(
#             client_id=client_id, # Provide the client_id here
#             predicted_followup_time=predicted_time
#         )

#         # prints to inspect the created object (these should be reached if creation succeeds)
#         print(f"Created followup_prediction object. Type: {type(followup_prediction)}")
#         print(f"followup_prediction object: {followup_prediction.__dict__}")
#         print(f"followup_prediction.id: {getattr(followup_prediction, 'id', 'AttributeError')}")
#         print(f"followup_prediction.client_id: {getattr(followup_prediction, 'client_id', 'AttributeError')}")

#         print("Returning success response.")
#         return {
#             "id": followup_prediction.id,
#             "client_id": followup_prediction.client_id,
#             "predicted_followup_time": predicted_time.strftime("%Y-%m-%d %H:%M:%S"),
#             "status": "created"
#         }

#     except Exception as e:
#         print(f"Error in predict_followup_time_endpoint for client_id {client_id}: {e}")
#         raise HTTPException(status_code=500, detail=f"Internal server error: {e}") 
    


@router.post("/predict-followup-time-end", response_model=None)
async def predict_followup_time_end(request: FollowupPredictionRequest):
    try:
        # Convert string dates to datetime objects
        call_dates = []
        for date_str in request.call_dates:
            try:
                call_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                call_dates.append(call_date)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format: {date_str}. Expected format: YYYY-MM-DD HH:MM:SS"
                )

        # Get prediction using the helper function
        predicted_time_str = await predict_followup_time(call_dates, request.client_id)
        
        if not predicted_time_str:
            raise HTTPException(
                status_code=400,
                detail="Failed to generate a valid follow-up time prediction"
            )

        # Convert to datetime object for saving
        predicted_time = datetime.strptime(predicted_time_str, "%Y-%m-%d %H:%M:%S")

        # Save to DB
        followup_prediction = await FollowupPrediction.create(
            client_id=request.client_id,
            predicted_followup_time=predicted_time
        )

        return {
            "id": followup_prediction.id,
            "client_id": followup_prediction.client_id,
            "predicted_followup_time": predicted_time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "created"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error predicting follow-up time: {str(e)}"
        ) 
    
    