import os
import logging
import httpx
import json
from datetime import datetime, timedelta
from tortoise import Tortoise
from typing import Optional
from helper.tortoise_config import TORTOISE_CONFIG
from dotenv import load_dotenv
import asyncio


# Load environment variables from .env file
load_dotenv()

# API URL for the Laravel backend (replace with actual URL) 
apiurl = os.getenv("API_URL")

# Ensure the API URL contains a valid protocol
if not apiurl.startswith(("http://", "https://")):
    apiurl = "http://" + apiurl  # Default to HTTP if protocol is missing

# Headers for the request (you can modify these as per your need)
headers = {
    "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "Accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}

async def get_users_by_client(user_id: Optional[int] = None):
    """
    Fetch all users with their associated client data from the Laravel API.
    """
    logger = logging.getLogger("cron_job")
    logger.setLevel(logging.DEBUG)
    url = f"{apiurl}/api/get-users-by-client{f'?user_id={user_id}' if user_id else ''}"
    print(f"new url we have {url}")
    

    try:
        async with httpx.AsyncClient(timeout=60.0) as client_http:
            logger.info("Fetching users with client relationships...")
            resp = await client_http.get(url, headers=headers)
            resp.raise_for_status()
            users_data = resp.json()
            print(f"data comes {users_data}")

            # ✅ Fix 1: check the right key/shape
            status = (users_data.get("status") or "").lower()
            if status != "success":
                logger.error(f"Failed to fetch users: {users_data.get('message', 'Unknown error')}")
                return {"status": "error", "message": users_data.get("message", "Failed to fetch users")}

            # ✅ Fix 2: robustly read list of users
            raw_users = users_data.get("data") or []
            if not isinstance(raw_users, list):
                logger.error("Payload 'data' is not a list.")
                return {"status": "error", "message": "Malformed response: data is not a list"}

            formatted = {"status": "success", "data": []}

            for u in raw_users:
                # Minimal safe fields
                user_entry = {
                    "id": u.get("id"),
                    "name": u.get("name") or "",
                    "last_name": u.get("last_name") or "",
                    "email": u.get("email") or "",
                    'client_id':u.get("client_id"),
                    "status": u.get("status"),
                    "client": [],
                }

                # ✅ Fix 3: API returns 'client' (singular), not 'clients'
                client_list = u.get("client") or []
                if isinstance(client_list, list):
                    for c in client_list:
                        # source shows: {'id', 'user_id', 'client_id', ...}
                        client_rail_id = c.get('client') or {}

                        user_entry["client"].append({
                            "id": c.get("id"),
                            "user_id": c.get("user_id"),
                            # use the actual client_id from the relation row
                            "client_id": c.get("client_id"),
                            # keep placeholders for optional fields if your downstream expects them
                            "name": c.get("name") or "Unnamed Client",
                            "callrail_id": client_rail_id['callrail_id'] if client_rail_id else '',
                            "created_at": c.get("created_at"),
                            "updated_at": c.get("updated_at"),
                            "deleted_at": c.get("deleted_at"),
                        })

                formatted["data"].append(user_entry)

            # logger.info(f"Fetched {len(formatted['data'])} users with client data")
            # logger.debug(f"Users data (normalized): {json.dumps(formatted, indent=2)}")
            return formatted

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching users: {e.response.status_code} - {e.response.text}")
        return {"status": "error", "message": f"HTTP error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Error in get_users_by_client: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Main execution logic (to run the job)
if __name__ == "__main__":
    import asyncio
    asyncio.run(get_users_by_client())  # Running the async job
