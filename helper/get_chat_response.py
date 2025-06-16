from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from models.message import Message
import os
from dotenv import load_dotenv
from dotenv import load_dotenv
from controller.call_transcript_controller import headers
from helper.get_data import get_client_data
load_dotenv()

LARAVEL_API_URL  = os.getenv("API_URL")

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


async def generate_ai_response(user_message: str, chat_id: str, user_id: str) -> str:
    try:
        history = await get_chat_history(int(chat_id))
        response_data = await get_client_data(int(user_id))

      
        actual_data = response_data.get("data", {}) if response_data.get("success") else None
        print(f"this data send to ai {actual_data}")
        
        response = await chain.ainvoke({
            "data": actual_data,  
            "history": history,
            "prompt": user_message
        })

        return response

    except Exception as e:
        print(f"Error while getting AI response: {str(e)}")
        return "Sorry, I encountered an error. Please try again."

