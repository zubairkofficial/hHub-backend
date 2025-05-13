from fastapi import FastAPI
from helper.tortoise_config import lifespan
from controller.controller import router as lead_router

app = FastAPI(lifespan=lifespan)

# Include the lead scoring router
app.include_router(lead_router, prefix="/api/v1", tags=["lead-scoring"])

@app.get('/')
def default_api():
    return "Hello to the world of AI"

