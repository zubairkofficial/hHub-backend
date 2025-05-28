from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from models.chat_history import ChatHistory
import os
from dotenv import load_dotenv
import traceback

router = APIRouter()

class ChatbotQueryRequest(BaseModel):
    user_id: str
    message: str

class ChatHistoryResponse(BaseModel):
    user_message: str
    bot_response: str
    created_at: str

@router.post("/chatbot-query")
async def chatbot_query(request: ChatbotQueryRequest):
    try:
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if db_url.startswith("mysql://"):
            db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not db_url or not openai_api_key:
            raise HTTPException(status_code=500, detail="Missing DATABASE_URL or OPENAI_API_KEY in environment.")

        db = SQLDatabase.from_uri(db_url)
        llm = ChatOpenAI(openai_api_key=openai_api_key, model="gpt-4o-mini", temperature=0)
        agent_executor = create_sql_agent(
            llm=llm,
            db=db,
            agent_type="openai-tools",
            verbose=False
        )

        # Fetch all previous messages for this user
        history = await ChatHistory.filter(user_id=request.user_id).order_by('created_at')
        context = ""
        for chat in history:
            context += f"User: {chat.user_message}\nBot: {chat.bot_response}\n"
        context += f"User: {request.message}\n"

        # Run the agent with the conversation history as a single string
        result = agent_executor.invoke({"input": context})
        answer = result["output"] if isinstance(result, dict) and "output" in result else str(result)

        # Save chat to database
        await ChatHistory.create(user_id=request.user_id, user_message=request.message, bot_response=answer)

        return {"answer": answer}
    except Exception as e:
        print("Exception occurred in chatbot_query")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chatbot error: {str(e)}")

@router.get("/chatbot-history/{user_id}", response_model=list[ChatHistoryResponse])
async def get_chat_history(user_id: str):
    try:
        history = await ChatHistory.filter(user_id=user_id).order_by('created_at')
        return [
            ChatHistoryResponse(
                user_message=chat.user_message,
                bot_response=chat.bot_response,
                created_at=chat.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ) for chat in history
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chat history: {str(e)}")





    