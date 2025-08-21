import time
import httpx
from dotenv import load_dotenv
from models.lead_score import LeadScore
from models.post_draft import PostDraft
from models.business_post import BusinessPost
import os

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
                    print(f"get 1st client_details = {client_details}")
                    
                    # Ensure 'logged_in_user_whose_asked_questions_or_chat' exists and is not empty
                    user_client_id = clinics['data'].get('logged_in_user_whose_asked_questions_or_chat', {})
                    print(f"get 2nd client_details = {user_client_id}")
                    
                    # Safely extract the 'client_id' from the 'logged_in_user_whose_asked_questions_or_chat' object
                    if user_client_id:
                        client_id = user_client_id.get('client_id', None)
                        print(f"User client_id: {client_id}")
                    else:
                        client_id = None
                        print("No user data available for 'logged_in_user_whose_asked_questions_or_chat'.")

                    # Check if client_details list is empty
                    if client_details:
                        client_ids_from_api = [client['id'] for client in client_details if 'id' in client]
                        print(f"get 3rd client_details = {client_ids_from_api}")
                    else:
                        print("No client details found.")
                        client_ids_from_api = []

                    # Step 4: Fetch the LeadScore data for the extracted client_ids (if any)
                    lead_scores = await LeadScore.filter(client_id=client_id).all()
                    print(f"Fetched lead scores: {lead_scores}")

                    # Convert LeadScore objects into dictionaries manually
                    lead_scores_dict = [
                        {
                            "id": score.id,
                            "client_id": score.client_id,
                            "callrail_id": score.callrail_id,
                            "analysis_summary": score.analysis_summary,
                            "intent_score": score.intent_score,
                            "urgency_score": score.urgency_score,
                            "overall_score": score.overall_score,
                            "name": score.name,
                            "type": score.type,
                            "potential_score": score.potential_score
                        }
                        for score in lead_scores
                    ]
                    print(f"Lead scores converted to dict: {lead_scores_dict}")

                    # Fetch PostDraft data
                    post_drafts = await PostDraft.filter(user_id=user_id).all()
                    print(f"PostDrafts for user {user_id}: {post_drafts}")

                    # Convert PostDraft objects into dictionaries manually
                    post_drafts_dict = [
                        {
                            "id": draft.id,
                            "user_id": draft.user_id,
                            "current_step": draft.current_step,
                            "content": draft.content,
                            "title": draft.title,
                            "description": draft.description,
                            "keywords": draft.keywords,
                            "post_options": draft.post_options,
                            "selected_post_index": draft.selected_post_index,
                            "image_ids": draft.image_ids,
                            "status": draft.status,
                            "selected_image_id": draft.selected_image_id,
                            "is_complete": draft.is_complete,
                            "created_at": draft.created_at,
                            "posted_at": draft.posted_at,
                            "updated_at": draft.updated_at,
                        }
                        for draft in post_drafts
                    ]
                    print(f"PostDrafts converted to dict: {post_drafts_dict}")

                    # Fetch BusinessPosts by user_id
                    business_posts = await BusinessPost.filter(user_id=user_id).all()
                    print(f"BusinessPosts for user {user_id}: {business_posts}")

                    # Add the fetched data to the clinics dictionary
                    clinics['data']['lead_scores'] = lead_scores_dict
                    clinics['data']['post_drafts'] = post_drafts_dict
                    clinics['data']['business_posts'] = [post.to_dict() for post in business_posts]
                    
                    # Cache the successful response
                    clinic_cache[user_id] = (clinics['data'], current_time)
                    
                    # Return the updated data
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
