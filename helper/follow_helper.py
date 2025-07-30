import openai
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from dotenv import load_dotenv
import os
from datetime import datetime
from helper.database import Database
from openai import OpenAI
from helper.post_setting_helper import get_settings

load_dotenv()

class FollowupPredictionResponse(BaseModel):
    predicted_followup_time: str

    class Config:
        schema_extra = {
            "example": {
                "predicted_followup_time": "YYYY-MM-DD HH:MM:SS"
            }
        }

async def get_unprocessed_callrail_dates_for_client(db: Database, client_id: int) -> List[Dict[str, Any]]:
    """Fetches unprocessed CallRail records for a client and marks them as processed."""
    query = "SELECT id, client_id, date FROM callrails WHERE client_id = %s AND processed_for_followup = FALSE"
    unprocessed_calls = await db.fetch(query, (client_id,))

    if unprocessed_calls:
        call_ids = [call['id'] for call in unprocessed_calls if 'id' in call]
        if call_ids:
            update_query = "UPDATE callrails SET processed_for_followup = TRUE WHERE id IN ({})".format(','.join(['%s'] * len(call_ids)))
            await db.execute(update_query, tuple(call_ids))

    return unprocessed_calls

async def predict_followup_time(call_dates: List[datetime], client_id: int) -> Optional[str]:
    """Predicts the best follow-up time based on a list of call dates."""
    if not call_dates:
        return None

    # Format call dates for the prompt
    formatted_dates = [date.strftime("%Y-%m-%d %H:%M:%S") for date in call_dates]
    call_history_str = "\n".join(formatted_dates)

    current_dt = datetime.now()
    current_date_str = current_dt.strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"""
    Today is {current_date_str}.
    Analyze the following call history for client ID {client_id} and predict the single best date and time for a follow-up call.
    The predicted time MUST be:
    1. At least 24 hours in the future from today
    2. Only on weekdays (Monday to Friday)
    3. During business hours (9 AM to 5 PM)
    Provide the output ONLY as a single date and time string in 'YYYY-MM-DD HH:MM:SS' format.

    Call History:
    {call_history_str}

    Predicted Follow-up Time:
    """

    try:
        settings = await get_settings()
        client = OpenAI(api_key=settings["openai_api_key"])
        if not client.api_key:
            raise ValueError("OpenAI API key not found in settings or environment variables")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are an AI assistant that analyzes call history to predict the best time for a follow-up call. Always predict a time that is in the current year ({datetime.now().year}) and at least 24 hours in the future. Respond ONLY with the predicted date and time in 'YYYY-MM-DD HH:MM:SS' format."}, 
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        prediction_text = response.choices[0].message.content.strip()

        # Validate prediction is at least 24 hours in the future and on a weekday
        try:
            # Try parsing with seconds first, if that fails try without seconds
            try:
                predicted_dt = datetime.strptime(prediction_text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    predicted_dt = datetime.strptime(prediction_text, "%Y-%m-%d %H:%M")
                except ValueError:
                    print(f"Warning: OpenAI returned invalid date format: {prediction_text}")
                    return None
                
            current_dt = datetime.now()
            
            # Check if the year is correct
            if predicted_dt.year != current_dt.year:
                print(f"Warning: Predicted follow-up time {prediction_text} is not in the current year {current_dt.year}")
                return None
            
            # Check if it's a weekend (5 is Saturday, 6 is Sunday)
            if predicted_dt.weekday() >= 5:
                print(f"Warning: Predicted follow-up time {prediction_text} is on a weekend.")
                return None
                
            # Check if it's in the future (comparing full datetime)
            if predicted_dt <= current_dt:
                print(f"Warning: Predicted follow-up time {prediction_text} is not in the future. Current time is {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                return None
                
            # Check if it's during business hours (9 AM to 5 PM)
            if predicted_dt.hour < 9 or predicted_dt.hour >= 17:
                print(f"Warning: Predicted follow-up time {prediction_text} is outside business hours (9 AM to 5 PM).")
                return None
                
            # Return in consistent format with seconds
            return predicted_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Error processing date: {str(e)}")
            return None

    except Exception as e:
        print(f"Error calling OpenAI for followup prediction: {e}")
        return None 