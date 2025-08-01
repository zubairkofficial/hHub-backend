from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import os
import logging
import json
import uuid
from helper.business_post_helper import BusinessPostHelper
from helper.image_generator_helper import get_focus_area_instruction, get_background_instruction, get_mood_instruction, get_lighting_instruction
from helper.prompts_helper import analyse_refference_image
from helper.Refine_image_prompt import compose_prompt_via_langchain
from models.image_generation_setting import ImageGenerationSetting
from models.post_settings import PostSettings
from helper.post_setting_helper import get_settings
from openai import OpenAI
from helper.helper import get_image_path, image_to_base64,save_base64_image
router = APIRouter()

class GenerateImageForPostRequest(BaseModel):
    user_id: str
    post_data: dict
    image_design: str
    instruction: str
    image_type: str


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


    # **Prompt for image_only**: Only visual content (no text)
async def build_prompt(image_no, post_data, image_type):
    """Build the image generation prompt based on various inputs."""
    title = post_data.get('title', '')
    description = post_data.get('description', '')
    content = post_data.get('content', '')
    image_design = post_data.get('image_design', '')  # Added image_design
    instruction = post_data.get('instruction', '')  # Added instruction

    # Define possible image designs and their meanings
    design_styles = {
        "realistic_image": "Realistic photography of humans, objects, or environments, with natural lighting and lifelike details.",
        "digital_illustration": "Hand-drawn or digitally created illustrations, with stylized artwork and vibrant colors.",
        "vector_illustration": "Flat, graphic vector art, often with clean lines and solid colors, typically used in logos and modern designs."
    }

    # Default design style if not found
    design_description = design_styles.get(image_design, "A general visual design style (can be realistic, illustrative, or vector-based)")

    # **Prompt for image_only**: Only visual content (no text)
    if image_type == "image_only":
        prompt = (
            f"Analyze the reference image. If it contains any text (title, heading, description, or labels), "
            f"generate a new version of the image that excludes all text. "
            f"Instead, add icons or images that visually represent the following:\n\n"
            f"Title context: '{title}'\n"
            f"Description context: '{description}'\n\n"
            f"Match the visual style of the reference — {image_design} ({design_description}).\n"
            f"Ensure the image looks realistic or fitting to the specified design style. "
            f"Do not add any textual elements, logos, or URLs. Keep the design clean, modern, and visually meaningful.\n\n"
            f"Additional Instructions: {instruction}\n"
        )

    # **Prompt for text_only**: Only text content (no images)
    elif image_type == "text_only":
        prompt = (
            f"Only replace the text with '{title}' while preserving the style and layout. "
            f"Do not add any visual elements such as icons, images, or logos. "
            f"Ensure the new title and description match the font style, spacing, and layout of the original image.\n\n"
            f"Title: '{title}'\n"
            f"Description: '{description}'\n\n"
            f"Design Style: {image_design} ({design_description})\n"
            f"Exclusions: No URLs, icons, or PNG images should be added.\n"
            f"Additional Instructions: {instruction}"
        )

    # **Prompt for both text and image**: Replace both text and visuals
    else:  # if image_type is both or any other variant
        prompt = (
            f"Analyze the reference image and generate a new version that replaces both the text and visual elements with new content.\n\n"
            f"1. Replace the existing title and description with:\n"
            f"   - Title: '{title}'\n"
            f"   - Description: '{description}'\n\n"
            f"2. Replace any existing icons, images, or illustrations with new ones that are visually relevant to the new text.\n\n"
            f"The new image should preserve the original design's layout, background, color palette, typography, font size, and spacing. "
            f"The new title and description should be clearly visible and integrated into the image as styled text, just like in the original.\n"
            f"Do not add logos, QR codes, URLs, or unrelated decorative elements.\n\n"
            f"Design Style: {image_design} ({design_description})\n"
            f"Additional Instructions: {instruction}\n"
        )

    return prompt



async def replace_text_and_visuals(prompt, image_filename):
    """Replace both text and visuals using OpenAI API."""
    try:
        settings = await get_settings()
        client = OpenAI(api_key=settings["openai_api_key"])
        
        # Step 1: Reference image and encoded base64
        image_path = get_image_path("reference_images", image_filename)
        b64 = image_to_base64(image_path)

        # Step 2: Use the generated prompt for replacing text and visuals
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

        # Step 3: Handle result
        image_calls = [o for o in response.output if o.type == "image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")

        result_b64 = image_calls[0].result
        image_name = save_base64_image(result_b64,'temp_images')

        return {"image_id": image_name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/business-post/generate-image-for-post")
async def generate_image_for_post(request: GenerateImageForPostRequest, image_no: int = Query(0)):
    try:
        # Fetch settings
        settings, num_images = await get_user_refference_images(request)
        
        # Extract reference image for layout analysis
        reference_layout = None
        if settings.reference_images:
            reference_layout = next((ref_image for ref_image in settings.reference_images if ref_image.get('analysis_type') == request.image_type), None)
            print(f"there is reference layout type = {type(reference_layout)}")
        
        if not reference_layout:
            raise HTTPException(status_code=404, detail="No reference layout found for the image type.")
        
        if reference_layout.get('image_filename',''):
            print(f"reference image name is = {reference_layout.get('image_filename','')}")
            image_filename = reference_layout['image_filename']
        else:
            raise HTTPException(status_code=404, detail="No reference layout found for the image type not found image_filename.")
        
        # Build the image generation prompt
        prompt = await build_prompt(image_no, request.post_data, request.image_type)
        
        print(f"final we get prompt")
        
        # Replace text and visuals using the new function
        result = await replace_text_and_visuals(prompt, image_filename)
        
        # Return image details
        image_obj = {
            "image_id": result["image_id"],
            "image_url": f"/api/business-post/display-image/{result['image_id']}?temp=1",
            "post_text": request.post_data.get('content', ''),
            "prompt": prompt
        }
        
        return image_obj
    
    except Exception as e:
        logging.error(f"Error in image generation: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating images: {str(e)}")
