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
    message: str

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

        # Set up LangChain SQLDatabase and agent
        db = SQLDatabase.from_uri(db_url)
        llm = ChatOpenAI(openai_api_key=openai_api_key, model="gpt-4o-mini", temperature=0)
        agent_executor = create_sql_agent(
            llm=llm,
            db=db,
            agent_type="openai-tools",
            verbose=False
        )

        result = agent_executor.invoke({"input": request.message})
        answer = result["output"] if isinstance(result, dict) and "output" in result else str(result)

        await ChatHistory.create(user_message=request.message, bot_response=answer)

        return {"answer": answer}
    except Exception as e:
        print("DEBUG: Exception occurred in chatbot_query")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chatbot error: {str(e)}") 