import os
import httpx
from datetime import datetime, timedelta
from tortoise import Tortoise
from helper.tortoise_config import TORTOISE_CONFIG
from dotenv import load_dotenv
import asyncio
from helper.callrail_lead_data_helper import process_clients_background  # Import the helper function for processing

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
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}

async def get_users_by_client():
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    
    try:
        # Make the GET request to the Laravel API
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{apiurl}/api/get-users-by-client", headers=headers)

        # If the response from Laravel API is successful
        if response.status_code == 200:
            data = response.json()  # Get the JSON data from the response
            
            # Loop through the data['data'] and check if the 'client' array is not null or empty
            for user in data['data']:
                if user.get('client'):  # Check if 'client' array is not empty
                    client_ids = [str(client['client_id']) for client in user['client']]  # Extract client ids
                    
                    user_id = user['id']  # Example user_id, replace it with the actual user id from your logic
                    
                    # Call the process_clients_background function for each valid user
                    print(f"Processing clients for user {user['name']} with client ids {client_ids}")
                    await process_clients_background(client_ids, user_id)
                else:
                    print(f"No valid client data for user {user['name']}")

        # If Laravel API returned a non-200 status code, print the error
        else:
            print(f"Failed to fetch data from Laravel. Status Code: {response.status_code}")
            print(f"Response: {response.text}")

    except httpx.RequestError as e:
        # If there’s a request error (e.g. network issue, invalid URL)
        print(f"Request failed: {e}")

    except Exception as e:
        # Catch any other errors
        print(f"Internal server error: {e}")
    
    finally:
        # Ensure that the database connection is closed properly
        await Tortoise.close_connections()
        print("Tortoise connections closed.")

# Main execution logic (to run the job)
if __name__ == "__main__":
    import asyncio
    asyncio.run(get_users_by_client())  # Running the async job
