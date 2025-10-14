from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import os
import logging
from helper.business_post_helper import BusinessPostHelper
from helper.image_generator_helper import (
    get_focus_area_instruction,
    get_background_instruction,
    get_mood_instruction,
    get_lighting_instruction,
)
from helper.prompts_helper import analyse_refference_image
from helper.Refine_image_prompt import compose_prompt_via_langchain
from models.image_generation_setting import ImageGenerationSetting
from models.post_settings import PostSettings
from models.post_prompt_settings import PostPromptSettings  # ← NEW (fetch keys)
from openai import OpenAI
from helper.helper import get_image_path, image_to_base64, save_base64_image, get_aspect_ratio
from helper.design_styles import design_styles
from io import BytesIO
from PIL import Image
from google import genai
import asyncio
from uuid import uuid4

router = APIRouter()


class GenerateImageForPostRequest(BaseModel):
    user_id: str
    post_data: dict
    image_design: str
    instruction: str
    image_type: str


# Ensures a directory exists
def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


async def get_user_refference_images(request):
    """Fetch settings for the user and image generation."""
    print(f"user setting id = {request.user_id}")
    print(f"request type = {request.image_type}")
    settings = await PostSettings.filter(user_id=request.user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Post settings not found")

    # Use admin setting for number of images
    setting = await ImageGenerationSetting.filter(id=1).first()
    num_images = setting.num_images if setting else 1
    return settings, num_images


# === Keys helper (DB first, then ENV) ========================================
async def _get_ai_keys() -> dict:
    """
    Fetch API keys from post_prompt_settings with environment fallbacks.
    Returns: {"openai_api_key": str, "fal_ai_api_key": str, "gemini_api_key": str}
    """
    rec = await PostPromptSettings.first()
    return {
        "openai_api_key": (rec.openai_api_key if rec and rec.openai_api_key else os.getenv("OPENAI_API_KEY", "")),
        "fal_ai_api_key": (rec.fal_ai_api_key if rec and rec.fal_ai_api_key else os.getenv("FAL_AI_API_KEY", "")),
        "gemini_api_key": (rec.gemini_api_key if rec and rec.gemini_api_key else os.getenv("GEMINI_API_KEY", "")),
    }


# === Prompt builder ===========================================================
async def build_prompt(image_no, post_data, image_type):
    """Build the image generation prompt based on various inputs."""
    title = post_data.get("title", "")
    description = post_data.get("description", "")
    content = post_data.get("content", "")
    image_design = post_data.get("image_design", "realistic_image")  # Default to realistic_image
    instruction = post_data.get("instruction", "")

    # Validate image_design
    if image_design not in design_styles:
        image_design = "realistic_image"  # Fallback to default
    design_description = design_styles.get(image_design)

    # Common object replacement instruction
    object_replacement_instruction = (
        f"Analyze the reference image to detect the number of primary objects (e.g., one object, two objects, etc.). "
        f"Replace the detected objects with new objects that visually represent the context of:\n"
        f"Title: '{title}'\n"
        f"Description: '{description}'\n"
        f"Maintain the same number of objects as in the reference image. "
        f"If the reference image contains human objects and the design style is '{image_design}' starting with 'realistic_image', "
        f"replace the human objects with new human figures that are relevant to the title and description. "
        f"For non-human objects, replace with contextually relevant objects.\n"
    )

    # image_only
    if image_type == "image_only":
        prompt = (
            f"{object_replacement_instruction}\n"
            f"Generate a new image version by replacing the visual objects from the reference image, without any text elements.\n" # Clarified intent
            f"Maintain the same number of objects as in the original reference image.\n\n" # Explicitly state object count
            
            f"**Design Constraints:**\n"
            f"Match the visual style of the reference — {image_design} ({design_description}).\n"
            f"Do **not** change the original background. The background color, pattern, and style must remain exactly as in the reference image.\n"
            f"Ensure the image is realistic if '{image_design}' starts with 'realistic_image', or stylized if it starts with 'digital_illustration' or 'vector_illustration'.\n" # Added realism/stylization
            
            f"**Negative Prompts (Applicable to Reference and New Elements):**\n"
            f"Do not include or replicate any textual elements (including titles or descriptions), logos, QR codes, URLs, icons, addresses, phone numbers, emails, or any unrelated decorative elements. This applies to elements from the reference image as well as new additions.\n" # Consolidated and strengthened
            f"Keep the design clean, modern, and visually meaningful.\n\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
            f"Additional Instructions: {instruction}\n"
        )

    # text_only
    elif image_type == "text_only":
        prompt = (
            f"Only replace the text with '{title}' while preserving the style and layout. "
            f"Do not add any visual elements such as icons, images, or logos. "
            f"Ensure the new title and description match the font style, spacing, and layout of the original image.\n\n"
            f"Title: '{title}'\n"
            f"**Design Constraints:**\n"
            f"Description: '{description}'\n\n"
            f"Design Style: {image_design} ({design_description})\n"
            f"**Negative Prompts:**\n"
            f"Exclusions: No URLs, icons, logos, address, phone, emails or PNG images should be added.\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
            f"Additional Instructions: {instruction}"
        )

    # both (or other)
    else:
        prompt = (
            f"{object_replacement_instruction}\n"
            f"Generate a new version that replaces both the text and visual elements with new content:\n\n"
            f"1. Replace the existing title and description with:\n"
            f"   - Title: '{title}'\n"
            f"   - Description: '{description}'\n\n"
            f"2. Replace the detected objects with new ones as described above, maintaining the same number of objects.\n\n"
            f"**Design Constraints:**\n"
            f"Do **not** change the original background. The background color, pattern, and style must remain exactly as in the reference image.\n"
            f"The new image should preserve the original design's layout, background, color palette, typography, font size, and spacing. "
            f"The new title and description should be clearly visible and integrated into the image as styled text, just like in the original.\n"
            f"Match the visual style of the reference — {image_design} ({design_description}).\n"
            f"Ensure the image is realistic if '{image_design}' starts with 'realistic_image', or stylized if it starts with 'digital_illustration' or 'vector_illustration'.\n"
            f"**Negative Prompts (Applicable to Reference and New Elements):**\n"
            f"Do not include or replicate any logos, QR codes, URLs, icons, addresses, phone numbers, emails, or unrelated decorative elements. This applies to elements from the reference image as well as new additions.\n\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
            f"Additional Instructions: {instruction}\n"
        )

    return prompt


# === OpenAI path ==============================================================
async def replace_text_and_visuals(prompt, image_filename):
    """Replace both text and visuals using OpenAI API."""
    try:
        keys = await _get_ai_keys()
        openai_key = keys["openai_api_key"]
        if not openai_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        client = OpenAI(api_key=openai_key)

        # Step 1: Reference image and encoded base64 (as data URI)
        image_path = get_image_path("reference_images", image_filename)
        b64 = image_to_base64(image_path)
        if not b64.startswith("data:"):
            # Try to infer mime from extension; PNG is safe default
            ext = os.path.splitext(image_path)[1].lower()
            mime = "image/png"
            if ext in [".jpg", ".jpeg"]:
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            b64 = f"data:{mime};base64,{b64}"

        # Step 2: Use the generated prompt for replacing text and visuals
        response = client.responses.create(
            model="gpt-4.1",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": b64},
                    ],
                }
            ],
            tools=[{"type": "image_generation", "size": "1024x1024"}],
        )

        # Step 3: Handle result
        image_calls = [o for o in response.output if o.type == "image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")

        result_b64 = image_calls[0].result
        image_name = save_base64_image(result_b64, "temp_images", image_path)

        return {"image_id": image_name}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Gemini path (uses gemini_api_key from DB/ENV) ============================
async def replace_text_and_visuals_gemini(prompt: str, image_filename: str):
    """
    Use Gemini API to replace visuals (and optionally text), by supplying a prompt + reference image.
    Reads gemini_api_key from post_prompt_settings (fallback: GEMINI_API_KEY env).
    Returns {'image_id': <saved filename>}.
    """
    try:
        keys = await _get_ai_keys()
        gemini_key = keys.get("gemini_api_key", "")
        if not gemini_key:
            raise HTTPException(status_code=500, detail="Gemini API key not configured")

        # Instantiate Gemini client with the DB/ENV key
        client: genai.Client = genai.Client(api_key=gemini_key)

        # Step 1: Load reference image
        image_path = get_image_path("reference_images", image_filename)
        input_image = Image.open(image_path)

        # Step 2: Gemini API call, offloaded to thread to keep async performance
        def _call_gemini():
            return client.models.generate_content(
                model="gemini-2.5-flash-image-preview",
                contents=[prompt, input_image],
            )

        response = await asyncio.to_thread(_call_gemini)

        # Step 3: Parse output and save first image
        try:
            parts = response.candidates[0].content.parts
        except Exception:
            raise HTTPException(status_code=500, detail="Unexpected Gemini response: no content parts")

        for part in parts:
            if getattr(part, "inline_data", None) is not None:
                img_bytes = part.inline_data.data  # raw image bytes
                img = Image.open(BytesIO(img_bytes))

                out_dir = get_image_path("temp_images", "")
                _ensure_dir(out_dir)

                out_name = f"gemini_{uuid4().hex}.png"
                out_path = os.path.join(out_dir, out_name)
                img.save(out_path, format="PNG")
                return {"image_id": out_name}

        raise HTTPException(status_code=500, detail="No image output found in Gemini response")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Route ====================================================================
@router.post("/business-post/generate-image-for-post")
async def generate_image_for_post(request: GenerateImageForPostRequest, image_no: int = Query(0)):
    try:
        # Fetch settings
        settings, num_images = await get_user_refference_images(request)

        # Extract reference image for layout analysis
        reference_layout = None
        if settings.reference_images:
            reference_layout = next(
                (ref_image for ref_image in settings.reference_images if ref_image.get("analysis_type") == request.image_type),
                None,
            )
            print(f"there is reference layout type = {type(reference_layout)}")

        if not reference_layout:
            raise HTTPException(status_code=404, detail="No reference layout found for the image type.Please go to brand guidelines and upload your reference images")

        if reference_layout.get("image_filename", ""):
            print(f"reference image name is = {reference_layout.get('image_filename', '')}")
            image_filename = reference_layout["image_filename"]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No reference layout found for the image type not found {image_filename}.",
            )

        # Build the image generation prompt
        prompt = await build_prompt(image_no, request.post_data, request.image_type)
        print("final we get prompt")

        # Choose path (currently Gemini)
        # result = await replace_text_and_visuals(prompt, image_filename)
        result = await replace_text_and_visuals_gemini(prompt, image_filename)

        # Return image details
        image_obj = {
            "image_id": result["image_id"],
            "image_url": f"/api/business-post/display-image/{result['image_id']}?temp=1",
            "post_text": request.post_data.get("content", ""),
            "prompt": prompt,
        }

        return image_obj

    except Exception as e:
        logging.error(f"Error in image generation: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating images: {str(e)}")
