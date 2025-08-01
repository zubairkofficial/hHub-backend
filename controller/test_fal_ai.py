from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from helper.business_post_helper import BusinessPostHelper
from helper.fall_ai import fall_ai_image_generator
from openai import OpenAI
from langchain_openai import ChatOpenAI

from helper.post_setting_helper import get_settings
from helper.helper import get_image_path,image_to_base64
import uuid
import base64
import os
import requests
import fal_client


router = APIRouter()
class BusinessPostHelper:
    def __init__(self):
        # Initialize without API key, will be set in async methods
        self.llm = None
        self.client = None
        
    async def _get_api_key(self):
            settings = await get_settings()
            return settings["openai_api_key"]

    async def _init_clients(self):
            if self.llm is None:
                api_key = await self._get_api_key()
                self.llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=1.2,
                    api_key=api_key
                )
                self.client = OpenAI(api_key=api_key)
                print(f"key: {api_key}")
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
async def callOpenAIImage():
    settings = await get_settings()
    
    client = OpenAI(api_key=settings["openai_api_key"])
    image_path = get_image_path("reference_images", "ref_16_1754035087_86115fd7.jpeg")

    b64 = image_to_base64(image_path)
    print(f"image b64 {b64}")

    prompt = f"Only replace the text with 'Invest in Health Services' while preserving style... and exclude any url,icon,png and adjust {'Make a difference with your donation.'}"

    try:
        response = client.responses.create(
            model="gpt-4.1",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"{b64}"}
                ]
            }],
            tools=[{"type": "image_generation"}]
        )

        image_calls = [o for o in response.output if o.type=="image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")
        result_b64 = image_calls[0].result
        # result is base64 string without "data:image/…"

        # Create folder and save PNG
        os.makedirs("temp_images", exist_ok=True)
        image_id = str(uuid.uuid4())
        filename = f"{image_id}.png"
        filepath = os.path.join("temp_images", filename)

        # Ensure base64 has no prefix
        data = result_b64.split(",", 1)[-1] if "," in result_b64 else result_b64
        try:
            img_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Invalid base64 data: {e}")

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        return {"image_id": image_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get('/openai/replace_images_preserve_text')
async def replace_visual_content_only():
    settings = await get_settings()
    client = OpenAI(api_key=settings["openai_api_key"])
    
    # Step 1: Load and base64 encode reference image
    image_path = get_image_path("reference_images", "ref_16_1753704112_4cba951d.png")
    b64 = image_to_base64(image_path)
    title = "Invest in Health Services"
    description = "Make a difference with your donation."

    # Step 2: Prompt — only replace image/icon areas and their labels
    prompt = (
        f"Analyze the reference image. If it contains any text (title, heading, description, or labels), "
        f"generate a new version of the image that excludes all text. "
        f"Instead, add icons or images that visually represent the following:\n\n"
        f"Title context: '{title}'\n"
        f"Description context: '{description}'\n\n"
        f"Match the visual style of the reference — whether it's cartoon, flat, photorealistic, etc. "
        f"Maintain the same background, layout, color palette, and font style (if fonts are present as graphics). "
        f"Do not add any textual elements, logos, or URLs. Keep the design clean, modern, and visually meaningful."
    )



    try:
        response = client.responses.create(
            model="gpt-4.1",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": b64}
                ]
            }],
            tools=[{"type": "image_generation"}]
        )

        # Step 3: Extract image generation result
        image_calls = [o for o in response.output if o.type == "image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")

        result_b64 = image_calls[0].result
        data = result_b64.split(",", 1)[-1] if "," in result_b64 else result_b64

        # Step 4: Save result to local folder with UUID
        os.makedirs("temp_images", exist_ok=True)
        image_id = str(uuid.uuid4())
        filename = f"{image_id}.png"
        filepath = os.path.join("temp_images", filename)

        try:
            img_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Base64 decode failed: {e}")

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        return {"image_id": image_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/openai/replace_text_and_visuals')
async def replace_text_and_visuals():
    settings = await get_settings()
    client = OpenAI(api_key=settings["openai_api_key"])
    
    # Step 1: Reference image and encoded base64
    image_path = get_image_path("reference_images", "ref_16_1753704131_f6aa38cf.png")
    b64 = image_to_base64(image_path)

    # Step 2: New content to replace (title & description)
    title = "Invest in Health Services"
    description = "Make a difference with your donation."

    # Step 3: Enhanced prompt — change both text and visual elements
    prompt = (
    f"Analyze the reference image and generate a new version that replaces both the text and visual elements with new content.\n\n"
    f"1. Replace the existing title and description with:\n"
    f"   - Title: '{title}'\n"
    f"   - Description: '{description}'\n\n"
    f"2. Replace any existing icons, images, or illustrations with new ones that are visually relevant to the new text.\n\n"
    f"The new image should preserve the original design's layout, background, color palette, typography, font size, and spacing. "
    f"The new title and description should be clearly visible and integrated into the image as styled text, just like in the original.\n"
    f"Do not add logos, QR codes, URLs, or unrelated decorative elements."
)



    try:
        response = client.responses.create(
            model="gpt-4.1",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": b64}
                ]
            }],
            tools=[{"type": "image_generation"}]
        )

        # Step 4: Handle result
        image_calls = [o for o in response.output if o.type == "image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")

        result_b64 = image_calls[0].result
        data = result_b64.split(",", 1)[-1] if "," in result_b64 else result_b64

        # Step 5: Save result locally
        os.makedirs("temp_images", exist_ok=True)
        image_id = str(uuid.uuid4())
        filename = f"{image_id}.png"
        filepath = os.path.join("temp_images", filename)

        try:
            img_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Base64 decode failed: {e}")

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        return {"image_id": image_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
