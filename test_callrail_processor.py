"""
Test script for CallRailProcessor
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import the module
from helper.callrail_lead_data_helper import process_clients_background

async def test_process_clients():
    """Test the process_clients_background function"""
    # Test with a specific user and client IDs
    user_id = 16  # Jenny's user ID
    client_ids = ['2', '3']  # Client IDs that have CallRail data
    
    print(f"Testing CallRail processing for user_id={user_id}, client_ids={client_ids}")
    
    try:
        result = await process_clients_background(client_ids, user_id)
        print("\nTest Results:")
        print(f"Status: {result.get('status')}")
        print(f"Message: {result.get('detail', 'No details provided')}")
        print(f"Processed Count: {result.get('processed_count', 0)}")
        
        if 'created_leads' in result:
            print(f"Created Leads: {len(result['created_leads'])}")
        if 'updated_leads' in result:
            print(f"Updated Leads: {len(result['updated_leads'])}")
            
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Run the test
    asyncio.run(test_process_clients())
