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
from helper.helper import get_image_path, image_to_base64, save_base64_image,get_aspect_ratio
from helper.design_styles import design_styles  # Import design_styles

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

# async def build_prompt(image_no, post_data, image_type):
#     """Build the image generation prompt based on various inputs."""
#     title = post_data.get('title', '')
#     description = post_data.get('description', '')
#     content = post_data.get('content', '')
#     image_design = post_data.get('image_design', 'realistic_image')  # Default to realistic_image
#     instruction = post_data.get('instruction', '')

#     # Validate image_design
#     if image_design not in design_styles:
#         image_design = "realistic_image"  # Fallback to default
#     design_description = design_styles.get(image_design)

#     # Determine the art style category and object replacement style
#     def get_style_category_and_object_style(design_style):
#         if design_style.startswith('realistic_image'):
#             return 'realistic', 'realistic human figures with natural proportions and lifelike details'
#         elif design_style.startswith('digital_illustration'):
#             return 'digital_illustration', 'illustrated human characters in digital art style with stylized proportions, artistic rendering, and illustration aesthetics'
#         elif design_style.startswith('vector_illustration'):
#             return 'vector', 'vector-style human figures with clean lines, flat colors, and geometric simplification'
#         else:
#             return 'realistic', 'realistic human figures with natural proportions and lifelike details'

#     style_category, human_object_style = get_style_category_and_object_style(image_design)

#     # Enhanced object replacement instruction based on design style
#     object_replacement_instruction = (
#         f"Analyze the reference image to detect the number of primary objects (e.g., one object, two objects, etc.). "
#         f"Replace the detected objects with new objects that visually represent the context of:\n"
#         f"Title: '{title}'\n"
#         f"Description: '{description}'\n"
#         f"Maintain the same number of objects as in the reference image.\n\n"
#         f"IMPORTANT - Style-Specific Object Replacement Rules:\n"
#         f"- If the reference image contains human objects, replace them with {human_object_style} that are relevant to the title and description context.\n"
#         f"- For non-human objects, replace with contextually relevant objects rendered in the '{image_design}' style: {design_description}\n"
#         f"- ALL objects must match the visual style '{image_design}' - this means if you select digital illustration, humans should look like digital illustrations, not realistic photos.\n"
#         f"- If you select vector illustration, humans should be vector-style with flat colors and clean lines.\n"
#         f"- If you select realistic image, humans should look photorealistic.\n\n"
#     )

#     # **Prompt for image_only**: Only visual content (no text)
#     if image_type == "image_only":
#         prompt = (
#             f"{object_replacement_instruction}"
#             f"CRITICAL: The entire image must be rendered in the '{image_design}' style: {design_description}\n"
#             f"This means:\n"
#             f"- If '{image_design}' is a digital_illustration variant, ALL elements (humans, objects, environment) should look like digital illustrations, NOT realistic photos\n"
#             f"- If '{image_design}' is a vector_illustration variant, ALL elements should be vector-style with flat colors and clean lines\n"
#             f"- If '{image_design}' is a realistic_image variant, ALL elements should look photorealistic\n\n"
#             f"Do **not** change the original background color, pattern, and style. The background must remain exactly as in the reference image.\n"
#             f"Do not add any textual elements, logos, or URLs. Keep the design clean, modern, and visually meaningful.\n"
#             f"Ensure perfect consistency between the chosen design style and the visual appearance of all objects.\n"
#             f"Additional Instructions: {instruction}\n"
#         )

#     # **Prompt for text_only**: Only text content (no images)
#     elif image_type == "text_only":
#         prompt = (
#             f"Only replace the text with '{title}' while preserving the style and layout. "
#             f"Do not add any visual elements such as icons, images, or logos. "
#             f"Ensure the new title and description match the font style, spacing, and layout of the original image.\n\n"
#             f"Title: '{title}'\n"
#             f"Description: '{description}'\n\n"
#             f"Design Style: {image_design} ({design_description})\n"
#             f"Exclusions: No URLs, icons, or PNG images should be added.\n"
#             f"Additional Instructions: {instruction}"
#         )

#     # **Prompt for both text and image**: Replace both text and visuals
#     else:  # if image_type is both or any other variant
#         prompt = (
#             f"{object_replacement_instruction}"
#             f"Generate a new version that replaces both the text and visual elements with new content:\n\n"
#             f"1. Replace the existing title and description with:\n"
#             f"   - Title: '{title}'\n"
#             f"   - Description: '{description}'\n\n"
#             f"2. Replace the detected objects with new ones as described above, maintaining the same number of objects.\n\n"
#             f"CRITICAL STYLE CONSISTENCY:\n"
#             f"- The ENTIRE image must be rendered in the '{image_design}' style: {design_description}\n"
#             f"- If '{image_design}' is digital_illustration/pastel_sketch, then humans should look like pastel sketch illustrations, NOT realistic photos\n"
#             f"- If '{image_design}' is vector_illustration/flat, then humans should be flat vector-style figures\n"
#             f"- If '{image_design}' is realistic_image, then humans should look photorealistic\n"
#             f"- ALL visual elements (objects, humans, environment) must match the selected design style\n\n"
#             f"Do **not** change the original background color, pattern, and style. The background must remain exactly as in the reference image.\n"
#             f"The new image should preserve the original design's layout, background, color palette, typography, font size, and spacing. "
#             f"The new title and description should be clearly visible and integrated into the image as styled text, just like in the original.\n"
#             f"Do not add logos, QR codes, URLs, or unrelated decorative elements.\n\n"
#             f"Additional Instructions: {instruction}\n"
#         )

#     return prompt
async def build_prompt(image_no, post_data, image_type):
    """Build the image generation prompt based on various inputs."""
    title = post_data.get('title', '')
    description = post_data.get('description', '')
    content = post_data.get('content', '')
    image_design = post_data.get('image_design', 'realistic_image')  # Default to realistic_image
    instruction = post_data.get('instruction', '')

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
        f"replace the human objects with new human figures that are relevant to the title and description (e.g., if the title is 'Family Picnic', "
        f"For non-human objects, replace with contextually relevant objects (e.g., replace a car with a bicycle for a title about cycling, "
        f"a tree with a flower for a gardening theme, or a book with a laptop for a tech theme).\n"
    )

    # **Prompt for image_only**: Only visual content (no text)
    if image_type == "image_only":
        prompt = (
            f"{object_replacement_instruction}\n"
            f"Match the visual style of the reference — {image_design} ({design_description}).\n"
            f"Do **not** change the original background. The background color, pattern, and style must remain exactly as in the reference image.\n"
            f"Design Style: {image_design} ({design_description})\n"
            f"Do not add any textual elements, logos, or URLs. Keep the design clean, modern, and visually meaningful.\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
            f"Additional Instructions: {instruction}\n"
        )
            # f"Ensure the image is realistic if '{image_design}' starts with 'realistic_image', or stylized if it starts with 'digital_illustration' or 'vector_illustration'.\n"

    # **Prompt for text_only**: Only text content (no images)
    elif image_type == "text_only":
        prompt = (
            f"Only replace the text with '{title}' while preserving the style and layout. "
            f"Do not add any visual elements such as icons, images, or logos. "
            f"Ensure the new title and description match the font style, spacing, and layout of the original image.\n\n"
            f"Title: '{title}'\n"
            f"Description: '{description}'\n\n"
            f"Design Style: {image_design} ({design_description})\n"
            f"Exclusions: No URLs, icons,logos,,address,phone,emails or PNG images should be added.\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
            f"Additional Instructions: {instruction}"
        )

    # **Prompt for both text and image**: Replace both text and visuals
    else:  # if image_type is both or any other variant
        prompt = (
            f"{object_replacement_instruction}\n"
            f"Generate a new version that replaces both the text and visual elements with new content:\n\n"
            f"1. Replace the existing title and description with:\n"
            f"   - Title: '{title}'\n"
            f"   - Description: '{description}'\n\n"
            f"2. Replace the detected objects with new ones as described above, maintaining the same number of objects.\n\n"
            f"Do **not** change the original background. The background color, pattern, and style must remain exactly as in the reference image.\n"
            f"The new image should preserve the original design's layout, background, color palette, typography, font size, and spacing. "
            f"The new title and description should be clearly visible and integrated into the image as styled text, just like in the original.\n"
            f"Match the visual style of the reference — {image_design} ({design_description}).\n"
            f"Ensure the image is realistic if '{image_design}' starts with 'realistic_image', or stylized if it starts with 'digital_illustration' or 'vector_illustration'.\n"
            f"Do not add logos, QR codes, URLs,icons,address,phone,emails or unrelated decorative elements.\n\n"
            f"Do **not** add additional text on the image except for the title and description.\n\n"
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
            # model="gpt-image-1",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": b64}
                ]
            }],
            tools=[{"type": "image_generation","size":"1024x1024"}]
        )

        # Step 3: Handle result
        image_calls = [o for o in response.output if o.type == "image_generation_call"]
        if not image_calls:
            raise HTTPException(status_code=500, detail="No image output returned")

        result_b64 = image_calls[0].result
        image_name = save_base64_image(result_b64, 'temp_images',image_path)

        return {"image_id": image_name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/business-post/generate-image-for-post")
async def generate_image_for_post(request: GenerateImageForPostRequest, image_no: int = Query(0)):
    try:
        error
        # Fetch settings
        settings, num_images = await get_user_refference_images(request)
        
        # Extract reference image for layout analysis
        reference_layout = None
        if settings.reference_images:
            reference_layout = next((ref_image for ref_image in settings.reference_images if ref_image.get('analysis_type') == request.image_type), None)
            print(f"there is reference layout type = {type(reference_layout)}")
        
        if not reference_layout:
            raise HTTPException(status_code=404, detail="No reference layout found for the image type.")
        
        if reference_layout.get('image_filename', ''):
            print(f"reference image name is = {reference_layout.get('image_filename', '')}")
            image_filename = reference_layout['image_filename']
            # image_path = get_image_path("reference_images", image_filename)
            # width,height = get_aspect_ratio(image_path)
            # print(f"height we have get = {height} AND width = {width}")
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