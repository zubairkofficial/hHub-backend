from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from helper.tortoise_config import lifespan
from controller.controller import router as lead_router

from controller.follow_controller import router as follow_router

from controller.chat_controller import router as chat_routre
from controller.call_transcript_controller import router as transcript_router
from controller.business_post_controller import router as business_post_router
from controller.post_prompt_setting_controller import router as post_prompt_setting_router
from controller.business_post_image_generate_controller import router as generate_images_for_post_router

from controller.test_fal_ai import router as test_fal_router
from controller.post_history_controller import router as post_history_router

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
app.include_router(post_prompt_setting_router, prefix="/api")
app.include_router(post_history_router, prefix="/api", tags=["post_history"])
# generated images for post
app.include_router(generate_images_for_post_router, prefix="/api")
# test fal ai
app.include_router(test_fal_router, prefix="/api", tags=["test"])




@app.get('/')
def default_api():
    return "Hello to the world of AI"

