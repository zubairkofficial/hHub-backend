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

# Initialize a cache dictionary
clinic_cache = {}
CACHE_EXPIRY_TIME = 600  # 10 minutes in seconds

async def get_client_data(user_id: int):
    current_time = time.time()

    # Check if the data is in the cache and not expired
    if user_id in clinic_cache:
        cached_data, cached_time = clinic_cache[user_id]
        if current_time - cached_time < CACHE_EXPIRY_TIME:
            print(f"Using cached data for user {user_id}")
            return cached_data
        else:
            print(f"Cache expired for user {user_id}, removing from cache")
            del clinic_cache[user_id]

    # If not in cache or cache expired, make a fresh API call
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            url = f"{LARAVEL_API_URL}/api/clinic/{user_id}"
            print(f"Making fresh API call to: {url}")
            
            response = await client.get(url, headers=headers)
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                clinics = response.json()
                print(f"Response data: {clinics}")
                
                if clinics.get('success', False):
                    # Cache the successful response
                    clinic_cache[user_id] = (clinics['data'], current_time)
                    return clinics['data']
                else:
                    print(f"Laravel API returned success=false: {clinics}")
                    return None
            else:
                print(f"Non-200 status code: {response.status_code}, Response: {response.text}")
                return None

        except httpx.RequestError as e:
            print(f"Request Error: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {type(e).__name__}: {str(e)}")
            return None
