from fastapi import FastAPI
from helper.tortoise_config import lifespan
from controller.controller import router as lead_router
from controller.call_controller import router as call_router
from controller.follow_controller import router as follow_router
from controller.chatbot_controller import router as chatbot_router


app = FastAPI(lifespan=lifespan)

# Include the routers
app.include_router(lead_router, prefix="/api/v1", tags=["lead-scoring"])
app.include_router(call_router, prefix="/api/v1", tags=["call-analysis"])
app.include_router(follow_router, prefix="/api/v1", tags=["followup-prediction"])
app.include_router(chatbot_router, prefix="/api/v1", tags=["chatbot"])

@app.get('/')
def default_api():
    return "Hello to the world of AI"

