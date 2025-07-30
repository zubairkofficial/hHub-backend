from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from helper.tortoise_config import lifespan
from controller.controller import router as lead_router

from controller.follow_controller import router as follow_router

from controller.chat_controller import router as chat_routre
from controller.call_transcript_controller import router as transcript_router
from controller.business_post_controller import router as business_post_router
from controller.test_fal_ai import router as test_fal_router


app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


app.include_router(follow_router, prefix="/api", tags=["followup-prediction"])
app.include_router(chat_routre, prefix="/api", tags=["chat"])
app.include_router(transcript_router, prefix="/api", tags=["transcript"])
app.include_router(business_post_router, prefix="/api", tags=["business-post"])
# test fal ai
app.include_router(test_fal_router, prefix="/api", tags=["test"])



@app.get('/')
def default_api():
    return "Hello to the world of AI"

