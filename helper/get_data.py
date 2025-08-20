import time
import httpx
from dotenv import load_dotenv
from models.lead_score import LeadScore
from models.post_draft import PostDraft
from models.business_post import BusinessPost
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
                    client_details = clinics['data'].get('clients', [])
                    client_ids_from_api = [client['id'] for client in client_details]

                    # Step 4: Fetch the LeadScore data for the extracted client_ids
                    lead_scores = await LeadScore.filter(client_id__in=client_ids_from_api).all()
                    print(f"Fetched lead scores: {lead_scores}")
                    post_drafts = await PostDraft.filter(user_id=user_id).all()
                    print(f"PostDrafts for user {user_id}: {post_drafts}")
                    
                    # Fetch BusinessPosts by user_id
                    business_posts = await BusinessPost.filter(user_id=user_id).all()
                    print(f"BusinessPosts for user {user_id}: {business_posts}")
                    # Cache the successful response
                    clinics['data']['lead_scores'] = [score.to_dict() for score in lead_scores]  # Assuming you want to convert to dict
                    clinics['data']['post_drafts'] = [draft.to_dict() for draft in post_drafts]
                    clinics['data']['business_posts'] = [post.to_dict() for post in business_posts]
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
