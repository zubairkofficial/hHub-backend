import time
import httpx
from dotenv import load_dotenv
import os
import json

load_dotenv()

LARAVEL_API_URL = os.getenv("API_URL")

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

async def get_client_data(user_id: int):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Always make a fresh API call by skipping cache logic
            url = f"{LARAVEL_API_URL}/api/clinic/{user_id}"
            print(f"Making fresh API call to: {url}")
            
            response = await client.get(url, headers=headers)
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                clinics = response.json()
                print(f"Response data: {clinics}")
                
                if clinics.get('success', False):
                    # Process and format the data into the desired structure
                    formatted_data = format_client_data(clinics['data'])
                    return formatted_data
                else:
                    print(f"Laravel API returned success=false: {clinics}")
                    return None
            else:
                print(f"Non-200 status code: {response.status_code}, Response: {response.text}")
                return None

        except httpx.ConnectError as e:
            print(f"Connection Error - Laravel server might not be running: {str(e)}")
            return None
        except httpx.TimeoutException as e:
            print(f"Timeout Error - Laravel server taking too long: {str(e)}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"HTTP Status Error: {e.response.status_code}, {e.response.text}")
            return None
        except httpx.RequestError as e:
            print(f"Request Error (general): {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {type(e).__name__}: {str(e)}")
            return None

def format_client_data(data):
    formatted_data = {}

    # List of tables to format the data
    tables = [
        "automation_templates", "bookings", "clinics",
        "client_service_history", "clients", "client_types", 
        "requests", "request_types", "dynamic_schedule_booking"
    ]

    for table in tables:
        table_data = data.get(table, [])
        if table_data:
            formatted_data[table] = []
            for entry in table_data:
                row = {key: entry[key] for key in entry.keys()}
                formatted_data[table].append(row)

    # Convert to JSON formatted string with indentation
    formatted_json = json.dumps(formatted_data, indent=4)
    return formatted_json
