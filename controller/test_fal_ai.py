from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from helper.business_post_helper import BusinessPostHelper
from helper.fall_ai import fall_ai_image_generator
from openai import OpenAI
from langchain_openai import ChatOpenAI
from helper.post_setting_helper import get_settings
import uuid
import os
import requests
import fal_client


router = APIRouter()
class TestRequest(BaseModel):
    prompt: Optional[str] = ""
    style: Optional[str] = ""
@router.post("/fal/ai")
async def callApi(request:TestRequest):
    print(f"Request is = {request}")
    prompt = request.prompt
    prompt = """"A square graphic with a dark blue background featuring a subtle wave pattern. At the top center (approximately 10% from the top), bold uppercase sans-serif text in white and coral reads:

INVEST IN
HEALTH
SERVICES

The text is center-aligned, large, and spaced for high readability, with each line under 15 characters. At the bottom center (around 85% from the top), a smaller, normal-weight, sans-serif sentence reads:

Make a difference with your donation.

This subtext is white, clearly legible, and also center-aligned. There are no icons, logos, images, or visible URLs. The design is clean and modern with no text shadows or strokes—focused entirely on the message.A square graphic with a dark blue background featuring a subtle wave pattern. At the top center (approximately 10% from the top), bold uppercase sans-serif text in white and coral reads:

INVEST IN
HEALTH
SERVICES

The text is center-aligned, large, and spaced for high readability, with each line under 15 characters. At the bottom center (around 85% from the top), a smaller, normal-weight, sans-serif sentence reads:

Make a difference with your donation.

This subtext is white, clearly legible, and also center-aligned. There are no icons, logos, images, or visible URLs. The design is clean and modern with no text shadows or strokes—focused entirely on the message."""
    style = request.style
    response = await fall_ai_image_generator(prompt, style)
    return response

@router.get('/openai/image')
async def callOpenAIImage(request:TestRequest):
    prompt = request.prompt
    
    try:
        settings = await get_settings()
        client = OpenAI(api_key=settings["openai_api_key"])
        response = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            size="1024x1024",
            # quality="standard",
            n=1
        )
        return {"image_url": response.data[0].url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")