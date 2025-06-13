from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from models.message import Message
import httpx
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import time
from dotenv import load_dotenv
from controller.call_transcript_controller import headers

load_dotenv()

LARAVEL_API_URL  = os.getenv("API_URL")


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


prompt = ChatPromptTemplate.from_messages([
    ('system', 'You are an assistant of "Houmanity" project. Use this data to answer: {data}'),
    MessagesPlaceholder("history"),
    ("user", "{prompt}")
])
model = init_chat_model("gpt-4o-mini", model_provider="openai")
output_parser = StrOutputParser()
chain = prompt | model | output_parser

async def get_chat_history(chat_id: int) -> list:
    try:
     
        messages = await Message.filter(chat_id=chat_id).order_by('-created_at').limit(10)
        
   
        history = []
        for msg in reversed(messages):  
            if msg.user_message:
                history.append(HumanMessage(content=msg.user_message))
            if msg.bot_response:
                history.append(AIMessage(content=msg.bot_response))
        
        return history
    except Exception as e:
        return []


clinic_cache = {}
CACHE_EXPIRY_TIME = 3000  

async def get_clinics_by_client(user_id: int):
    current_time = time.time()

    if user_id in clinic_cache:
        cached_data, cached_time = clinic_cache[user_id]
        if current_time - cached_time < CACHE_EXPIRY_TIME:
            print(f"Using cached data for user {user_id}")
            return cached_data
        else:
            print(f"Cache expired for user {user_id}, removing from cache")
            del clinic_cache[user_id]

    async with httpx.AsyncClient(timeout=30.0) as client:  # Increased timeout
        try:
            url = f"{LARAVEL_API_URL}/api/clinic/{user_id}"
            print(f"Making fresh API call to: {url}")
            
            response = await client.get(url,headers=headers)
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                clinics = response.json()
                print(f"Response data: {clinics}")
                
                if clinics.get('success', False):
                    clinic_cache[user_id] = (clinics['data'], current_time)
                    print(f"Cached successful data for user {user_id}")
                    return clinics['data']
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


async def generate_ai_response(user_message: str, chat_id: str, user_id: str) -> str:
    try:
        history = await get_chat_history(int(chat_id))
        # data = await get_clinics_by_client(int(user_id))
        # print(data)
        response = await chain.ainvoke({
            "data": "No data",
            "history": history,
            "prompt": user_message
        })

        return response

    except Exception as e:
        print(f"Error while getting AI response {str(e)}")
        return "Sorry, I encountered an error. Please try again."
