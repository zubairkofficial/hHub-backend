# E:\Shoaib\Projects\hHub\hHub-backend\helper\get_chat_widget_response.py
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
import os
from dotenv import load_dotenv

from helper.laravel_client import list_messages_widget
from helper.get_data import get_client_data
from models.system_prompt import SystemPrompts

load_dotenv()

LARAVEL_API_URL  = os.getenv("API_URL")

prompt = ChatPromptTemplate.from_messages([
    ('system', '{systemprompt}. Use this data to answer: {data}'),
    MessagesPlaceholder("history"),
    ("user", "{prompt}")
])
model = init_chat_model("gpt-4o-mini", model_provider="openai")
output_parser = StrOutputParser()
chain = prompt | model | output_parser

async def get_chat_history(chat_id: int, user_id: str) -> list:
    """
    Pull last ~10 messages from Laravel and convert to LangChain history.
    """
    try:
        rows = await list_messages_widget(chat_id=chat_id, user_id=user_id)
        # take last 10 to keep context light
        rows = rows[-10:] if len(rows) > 10 else rows

        history = []
        for msg in rows:
            user_msg = (msg.get("user_message") or "").strip()
            bot_msg  = (msg.get("bot_response") or "").strip()
            if user_msg:
                history.append(HumanMessage(content=user_msg))
            if bot_msg:
                history.append(AIMessage(content=bot_msg))
        return history
    except Exception as e:
        print(f"[get_chat_history] error: {e}")
        return []

async def generate_ai_response(user_message: str, chat_id: str, user_id: str) -> str:
    try:
        history = await get_chat_history(int(chat_id), user_id)
        response_data = await get_client_data(int(user_id))
        prompts = await get_prompts()

        if response_data:
            print(f"This data sent to AI: {response_data}")
        else:
            print("No data available to send to AI.")

        response = await chain.ainvoke({
            "systemprompt": prompts['systemprompt'],
            "data": response_data,
            "history": history,
            "prompt": user_message
        })
        return response

    except Exception as e:
        print(f"Error while getting AI response: {str(e)}")
        return "Sorry, I encountered an error. Please try again."

async def get_prompts():
    try:
        prompts = await SystemPrompts.filter().first()
        if prompts and prompts.system_prompt:
            systemprompt = prompts.system_prompt
        else:
            systemprompt = "You are an assistant of 'Houmanity' project"
        return {'systemprompt': systemprompt}
    except Exception as e:
        print(f"Error fetching prompts from database: {e}")
        return {'systemprompt': "You are an assistant of 'Houmanity' project"}
