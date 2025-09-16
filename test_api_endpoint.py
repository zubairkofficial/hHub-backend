"""
Test script to verify the Laravel API endpoint
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

async def test_api_endpoint():
    """Test the Laravel API endpoint"""
    # Load environment variables
    load_dotenv()
    
    # Get API URL from environment or use default
    api_url = os.getenv("API_URL", "http://localhost:8000")
    user_id = 16  # Jenny's user ID
    
    # Headers
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Test endpoint
    url = f"{api_url}/api/transcript/{user_id}"
    
    print(f"Testing API endpoint: {url}")
    
    try:
        async with httpx.AsyncClient() as client:
            # First, try without any parameters
            print("\nTesting with no parameters:")
            response = await client.get(url, headers=headers)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text[:500]}...")  # Print first 500 chars
            
            # Then try with client_ids
            print("\nTesting with client_ids [2, 3]:")
            params = {
                'client_ids': '2,3',
                'include_processed': 'true'
            }
            response = await client.get(url, params=params, headers=headers)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text[:500]}...")  # Print first 500 chars
            
    except Exception as e:
        print(f"Error during API test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api_endpoint())
