from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from helper.business_post_helper import BusinessPostHelper
from helper.extract_data_from_image import extract_data_from_img
from helper.prompts_helper import analyse_refference_image
from helper.Refine_image_prompt import compose_prompt_via_langchain
from models.post_settings import PostSettings
from models.business_post import BusinessPost
from typing import List, Optional, Any
from datetime import datetime
import os
from urllib.parse import unquote
from fastapi import Body, Path, HTTPException
from models.post_draft import PostDraft
import logging
import shutil
import httpx
from models.post_prompt_settings import PostPromptSettings
from helper.post_setting_helper import get_settings
import json
from io import BytesIO
from models.image_settings import ImageSettings
from models.image_generation_setting import ImageGenerationSetting
from pydantic import BaseModel
import base64
from openai import OpenAI
import re
import time
import uuid

router = APIRouter()


def extract_used_variables(prompt):
    # Find all {TITLE_LINE_*} variables
    title_vars = re.findall(r"\{HEADLINE_LINE_[^\}]+\}", prompt)
    print(f"title_vars = {title_vars}")
    # Also catch split title lines like {TITLE_LINE_2_PART1}
    description_vars = []
    if "{DESCRIPTION}" in prompt:
        description_vars.append("{DESCRIPTION}")
    if "{SUBTEXT}" in prompt:
        description_vars.append("{SUBTEXT}")
    return list(set(title_vars)), description_vars


def split_title_for_used_vars(title, used_title_vars):
    words = title.strip().split()
    result = {}
    count = len(used_title_vars)
    
    for i in range(count):
        if i < len(words):
            result[used_title_vars[i]] = words[i]
        else:
            result[used_title_vars[i]] = ""  # not enough words
    return result


def apply_layout_variables_dynamic(reference_prompt, title, description):
    prompt = reference_prompt

    # Detect which variables are used
    used_title_vars, description_vars = extract_used_variables(prompt)

    # Split title accordingly
    title_mapping = split_title_for_used_vars(title, used_title_vars)

    # Replace title variables
    for var in used_title_vars:
        prompt = prompt.replace(var, title_mapping.get(var, ""))

    # Replace description/subtext
    for var in description_vars:
        prompt = prompt.replace(var, description.strip())

    return prompt

class PostSettingsRequest(BaseModel):
    user_id: int
    business_idea: str
    brand_guidelines: str = None
    frequency: str = 'daily'
    posts_per_period: int = 1
    weekly_days: Optional[list] = None
    monthly_dates: Optional[list] = None
    uploaded_file: Optional[str] = None

class BusinessPostResponse(BaseModel):
    id: int
    post: str
    status: str
    created_at: str
    title: Optional[str] = None
    image_id: Optional[str] = None
    is_complete: Optional[bool] = None


class PostSettingsResponse(BaseModel):
    id: int
    user_id: int
    business_idea: str
    brand_guidelines: str = None
    frequency: str
    posts_per_period: int
    preview_image_id: Optional[str] = None
    weekly_days: Optional[list] = None
    monthly_dates: Optional[list] = None
    uploaded_file: Optional[str] = None
    extracted_file_text: Optional[str] = None
    reference_images: Optional[List[dict]] = None  # Changed from List[str] to List[dict]


class ApprovePostRequest(BaseModel):
    post_id: int

class DraftRequest(BaseModel):
    user_id: str
    current_step: int
    content: Optional[str] = None
    keywords: Optional[list] = None
    post_options: Optional[list] = None
    selected_post_index: Optional[int] = None
    post_data: Optional[dict] = None
    image_id: Optional[str] = None
    image_ids: Optional[list] = None
    selected_image_id: Optional[str] = None
    is_draft: bool = True
    draft_id: Optional[int] = None
    is_complete: bool = False

class ImageSelectionRequest(BaseModel):
    draft_id: int
    selected_image_id: str
    unselected_image_ids: Optional[list] = None

class GeneratePostsRequest(BaseModel):
    user_id: str
    idea: str
    keywords: str

class GenerateImageForPostRequest(BaseModel):
    user_id: str
    post_data: dict
    image_design: str
    instruction: str
    lighting_effects: str
    image_mood: str
    background_type: str
    focus_area: str
    image_type: str

class SelectPostRequest(BaseModel):
    draft_id: int
    post_data: dict
    image_id: str

class EditPostRequest(BaseModel):
    draft_id: int
    post_data: dict

class BusinessPostUpdateRequest(BaseModel):
    post: Optional[str] = None
    title: Optional[str] = None
    image_id: Optional[str] = None
    status:Optional[str] = None
    description: Optional[str] = None

class GenerateIdeaPayload(BaseModel):
    user_id: str = Field(...)
    user_text: str = Field(...)

class ImageSettingsRequest(BaseModel):
    user_id: str = Field(...)
    image_type: str
    image_design: str
    instruction: str = None
    lighting_effects: str = None
    image_mood: str = None
    background_type: str = None
    focus_area: str = None

class ImageSettingsResponse(BaseModel):
    user_id: str
    image_type: str
    image_design: str
    instruction: str = None
    lighting_effects: str = None
    image_mood: str = None
    background_type: str = None
    focus_area: str = None
    created_at: str
    updated_at: str

class ImageGenSettingRequest(BaseModel):
    num_images: int

helper = BusinessPostHelper()

def sanitize_filename(filename, max_length=100):
    import re
    filename = re.sub(r'[<>:"/\\|?*%&=]', '_', filename)
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length-len(ext)] + ext
    return filename

@router.post("/post-settings", response_model=PostSettingsResponse)
async def upsert_post_settings(request: PostSettingsRequest):
    try:
        existing = await PostSettings.filter(user_id=request.user_id).first()
        if existing:
            print("Exist -------------")
            print(request.brand_guidelines)
            existing.business_idea = request.business_idea
            existing.brand_guidelines = request.brand_guidelines
            existing.frequency = request.frequency
            existing.posts_per_period = request.posts_per_period
            existing.weekly_days = request.weekly_days
            existing.monthly_dates = request.monthly_dates
            if request.uploaded_file:
                existing.uploaded_file = request.uploaded_file
            await existing.save()
            settings = existing
        else:
            settings = await PostSettings.create(
                user_id=request.user_id,
                business_idea=request.business_idea,
                brand_guidelines=request.brand_guidelines,
                frequency=request.frequency,
                posts_per_period=request.posts_per_period,
                weekly_days=request.weekly_days,
                monthly_dates=request.monthly_dates,
                uploaded_file=request.uploaded_file
            )
        return PostSettingsResponse(
            id=settings.id,
            user_id=settings.user_id,
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            frequency=settings.frequency,
            posts_per_period=settings.posts_per_period,
            preview_image_id=getattr(settings, 'preview_image_id', None),
            weekly_days=getattr(settings, 'weekly_days', None),
            monthly_dates=getattr(settings, 'monthly_dates', None),
            uploaded_file=getattr(settings, 'uploaded_file', None),
            extracted_file_text=getattr(settings, 'extracted_file_text', None)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error upserting post settings: {str(e)}")
    
@router.get("/post-settings", response_model=PostSettingsResponse)
async def get_post_settings(user_id: int = Query(...)):
    try:
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")

        # Get reference_images as is (should be a list of dicts or None)
        reference_images = settings.reference_images
        if reference_images is None:
            reference_images = []
        
        # Ensure it's a list
        if not isinstance(reference_images, list):
            reference_images = []
        
        print(f"[DEBUG] Final reference_images to return: {reference_images}")

        return PostSettingsResponse(
            id=settings.id,
            user_id=settings.user_id,
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            frequency=settings.frequency,
            posts_per_period=settings.posts_per_period,
            preview_image_id=getattr(settings, 'preview_image_id', None),
            weekly_days=getattr(settings, 'weekly_days', None),
            monthly_dates=getattr(settings, 'monthly_dates', None),
            uploaded_file=getattr(settings, 'uploaded_file', None),
            extracted_file_text=getattr(settings, 'extracted_file_text', None),
            reference_images=reference_images
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching post settings: {str(e)}")


@router.get("/posts")
async def get_all_posts(user_id: Optional[int] = Query(None, description="User ID to filter posts")):
    try:
        if user_id is not None:
            posts = await BusinessPost.filter(user_id=user_id).order_by('-created_at')
            print(f"post get = {posts}")
            drafts = await PostDraft.filter(user_id=user_id).order_by('-created_at')
        else:
            posts = await BusinessPost.all().order_by('-created_at')
            drafts = await PostDraft.all().order_by('-created_at')
        result = [
            BusinessPostResponse(
                id=post.id,
                post=post.post,
                status=post.status,
                created_at=post.created_at.isoformat(),
                image_id=getattr(post, 'image_id', None),
                is_complete=False
            ) for post in posts
        ]
        print(f"results get = {result}")
        for draft in drafts:
            draft = await PostDraft.get(id=draft.id)
            post_data = None
            if draft.post_options and draft.selected_post_index is not None and 0 <= draft.selected_post_index < len(draft.post_options):
                post_data = draft.post_options[draft.selected_post_index]
            else:
                post_data = draft.content
                
            result.append({
                "id": draft.id,
                "post": post_data or "",
                "status": "draft",
                "created_at": draft.created_at.isoformat(),
                "image_id": getattr(draft, 'selected_image_id', None),
                "is_complete": draft.is_complete,
                "current_step": draft.current_step,
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
                "posted_at": draft.posted_at.isoformat() if draft.posted_at else None
            })
        result.sort(key=lambda x: x["created_at"] if isinstance(x, dict) else x.created_at, reverse=True)
        print(f"result of the send user posts {result}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching posts: {str(e)}")

def display_image_helper(image_id):
    return BusinessPostHelper.display_image_helper(image_id)

@router.get('/display-image/{image_id}')
def display_image(image_id: str, temp: int = 0):
    try:
        print(f"Requested image_id: {image_id}")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if temp:
            temp_dir = os.path.join(base_dir, '..', 'temp_images')
            image_path = os.path.join(temp_dir, image_id)
        else:
            images_dir = os.path.join(base_dir, '..', 'images')
            image_path = os.path.join(images_dir, image_id)
        if not os.path.exists(image_path):
            ref_dir = os.path.join(base_dir, '..', 'reference_images')
            ref_path = os.path.join(ref_dir, image_id)
            print(f"Checking reference_images: {ref_path}")
            if os.path.exists(ref_path):
                image_path = ref_path
        print(f"Serving image from: {image_path}")
        if os.path.exists(image_path):
            return FileResponse(path=image_path, media_type='image/png')
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        print(f"Error in display_image: {e}")
        raise HTTPException(detail=str(e), status_code=400)
    
@router.get("/posts/{post_id}", response_model=BusinessPostResponse)
async def get_post_by_id(post_id: int = Path(..., description="ID of the post to fetch")):
    try:
        post = await BusinessPost.get(id=post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return BusinessPostResponse(
            id=post.id,
            post=post.post,
            status=post.status,
            created_at=post.created_at.isoformat(),
            image_id=getattr(post, 'image_id', None)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching post: {str(e)}")
    


@router.post("/post-settings/upload-file")
async def upload_post_settings_file(file_type:str = "pdf", user_id: int = Query(...), file: UploadFile = File(...)):
    try:

        MAX_FILE_SIZE = 10 * 1024 * 1024
        file_content = await file.read()

        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 10 MB.")

        file.file = BytesIO(file_content)

        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        file_location = os.path.join(uploads_dir, file.filename)
        with open(file_location, "wb") as f:
            f.write(file_content)

        business_idea = None
        brand_guidelines = None
        all_text = None
        summary = None
        file_name = file.filename.split(".")
        extension = file_name[-1]
        # Extract data from the file
        if file.filename.endswith('.txt'):
            with open(file_location, "r", encoding="utf-8") as f:
                content = f.read()
                all_text = content
                lines = content.splitlines()
                if lines:
                    business_idea = lines[0]
                    brand_guidelines = "\n".join(lines[1:])
        elif file.filename.endswith('.pdf'):
            try:
                import pdfplumber
                with pdfplumber.open(file_location) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                all_text = text
                lines = text.splitlines()
                if lines:
                    business_idea = lines[0]
                    brand_guidelines = "\n".join(lines[1:])
            except Exception as e:
                print(f"pdfplumber extraction error: {e}")
        elif file.filename.endswith('.docx'):
            try:
                from docx import Document
                doc = Document(file_location)
                text = "\n".join([para.text for para in doc.paragraphs])
                all_text = text
                lines = text.splitlines()
                if lines:
                    business_idea = lines[0]
                    brand_guidelines = "\n".join(lines[1:])
            except Exception as e:
                print(f"DOCX extraction error: {e}")

        if extension in ['png', 'jpeg', 'jpg']:
            print(f"Extracting data from logo")
            summary = await extract_data_from_img(path= file_location)
            print(f"Summary of jpg = {summary}")
        if all_text and extension not in ['png', 'jpeg', 'jpg']:
            print("In All Text if statement")
            LLM_API_URL = "https://api.openai.com/v1/chat/completions"
            settings = await get_settings()
            LLM_API_KEY = settings["openai_api_key"]
            prompt = (
                "You are an expert in social media branding. "
                "Given the following extracted content from a brand guidelines document, do the following:\n"
                "1. Extract the color palette as a list of RGB color codes. For each color, specify if it is primary, secondary, accent, or other (if possible). Output each color on a new line in the format: <label>: rgb(R, G, B) (e.g., Primary: rgb(255, 87, 51)). If the role is not clear, just output the RGB code.\n"
                "2. Write a clear, plain-text overview of the brand in no more than 50 words. Do not use tags or formatting.\n"
                "Separate the two sections with the line '---'.\n"
                "If no colors are found, leave the first section empty.\n\n"
                f"Extracted Content:\n{all_text}\n\n"
                "Colors:\n"
            )
            headers = {
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 512,
                "temperature": 0.7
            }
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(LLM_API_URL, headers=headers, json=data)
                    response.raise_for_status()
                    result = response.json()
                    summary = result["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"LLM summarization error: {e}")
                summary = all_text  # fallback to raw text

        # Save the filename and extracted summary in the user's PostSettings
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        settings.uploaded_file = file.filename
        if business_idea:
            settings.business_idea = business_idea
        if summary:
            settings.brand_guidelines = summary
        if summary:
            settings.extracted_file_text = summary
        await settings.save()

        print(f"summary outside function = {summary}")
        return {
            "filename": file.filename,
            "business_idea": business_idea,
            "brand_guidelines": summary,
            "extracted_file_text": summary,
            "message": "File uploaded, data extracted, and summary generated successfully"
        }
    except Exception as e:
        print(f"error {str(e)}")

@router.post("/business-post/draft")
async def save_or_update_draft(request: DraftRequest):
    try:
   
        draft_id = getattr(request, "draft_id", None)
        is_complete = getattr(request, "is_complete", False)
        print('frist step')
        if draft_id:
            draft = await PostDraft.get(id=draft_id)
            print('second step')
            if not draft:
                raise HTTPException(status_code=404, detail="Draft not found")
            print('third step')
            
            draft.current_step = request.current_step
            print('4th step')
            # Support dict or string for post_data
            if request.post_data:
                print('request.post_data start')
              
                draft.content = request.post_data.get('content', '')
                draft.title = request.post_data.get('title', '')
                draft.description = request.post_data.get('description', '')
                print('request.post_data end')
            draft.keywords = request.keywords
            print(f"draf keywords = {draft.keywords}")
            # When saving/updating a draft, ensure post_options is a list of dicts with content, title, description
            if hasattr(request, 'post_options') and request.post_options:
                normalized_post_options = []
                for opt in request.post_options:
                    if isinstance(opt, dict):
                        normalized_post_options.append({
                            'content': opt.get('content', ''),
                            'title': opt.get('title', ''),
                            'description': opt.get('description', '')
                        })
                    else:
                        normalized_post_options.append({'content': str(opt), 'title': '', 'description': ''})
                print("[DEBUG] Normalized post_options:", normalized_post_options)
                draft.post_options = normalized_post_options
            else:
                draft.post_options = None
            print('after else')
            draft.selected_post_index = getattr(request, "selected_post_index", None)
            draft.image_ids = getattr(request, "image_ids", None)
            print("[DEBUG] image_ids before save:", draft.image_ids)
            draft.selected_image_id = getattr(request, "selected_image_id", None)
            draft.is_complete = is_complete
            print("[DEBUG] Draft object before save:", draft.__dict__)
            await draft.save()
            print("[DEBUG] Saved Draft:", draft.__dict__)
        else:
            draft = await PostDraft.create(
                user_id=request.user_id,
                current_step=request.current_step,
                content=request.content,
                title=request.title if hasattr(request, 'title') else None,
                description=request.description if hasattr(request, 'description') else None,
                keywords=request.keywords,
                post_options=getattr(request, "post_options", None),
                selected_post_index=getattr(request, "selected_post_index", None),
                image_ids=getattr(request, "image_ids", None),
                selected_image_id=getattr(request, "selected_image_id", None),
                is_complete=is_complete,
            )
            print("[DEBUG] Created Draft:", draft.__dict__)
        # Move selected image from temp_images to images if needed
        selected_image_id = getattr(request, "selected_image_id", None)
        if selected_image_id:
            import os, shutil
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
            images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
            temp_path = os.path.join(temp_dir, selected_image_id)
            images_path = os.path.join(images_dir, selected_image_id)
            if os.path.exists(temp_path) and not os.path.exists(images_path):
                shutil.move(temp_path, images_path)
        return {"message": "Draft saved", "draft_id": draft.id}
    except Exception as e:
        print("[DEBUG] Error saving draft:", str(e))
        raise HTTPException(status_code=500, detail=f"Error saving draft: {str(e)}")

@router.get("/business-post/draft/active")
async def get_active_draft(user_id: str, draft_id: int = None):
    try:
        if draft_id is not None:
            draft = await PostDraft.filter(user_id=user_id, id=draft_id).first()
        else:
            draft = await PostDraft.filter(user_id=user_id, is_complete=False).order_by('-id').first()
        if not draft:
            return {"message": "No active draft found"}
        return {
            "draft_id": draft.id,
            "current_step": draft.current_step,
            "content": draft.content,
            "keywords": draft.keywords,
            "post_options": draft.post_options,
            "selected_post_index": draft.selected_post_index,
            "image_ids": draft.image_ids,
            "selected_image_id": draft.selected_image_id,
            "is_completed": True,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "posted_at": draft.posted_at.isoformat() if draft.posted_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching active draft: {str(e)}")

@router.post("/business-post/generate-images")
async def generate_images(user_id: str = Form(...), content: str = Form(...)):
    try:
        # Get business idea, brand guidelines, extracted file text from PostSettings
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        images = []
        for _ in range(3):
            image_id = await helper.generate_image(
                business_idea=settings.business_idea,
                brand_guidelines=settings.brand_guidelines,
                extracted_file_text=settings.brand_guidelines
            )
            images.append(image_id)
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating images: {str(e)}")

@router.post("/business-post/upload-image")
async def upload_image(user_id: str = Form(...), file: UploadFile = File(...)):
    try:
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        os.makedirs(images_dir, exist_ok=True)
        filename = f"{user_id}_{file.filename}"
        file_path = os.path.join(images_dir, filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {"image_id": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")
    
@router.get("/business-post/display-image/{filename}")
async def display_image(filename: str, temp: int = 0):
    folder = 'temp_images' if temp else 'images'
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', folder, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(file_path)

@router.post("/business-post/draft/image")
async def save_selected_image(request: ImageSelectionRequest):
    try:
        draft = await PostDraft.get(id=request.draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        # Save selected image
        draft.selected_image_id = request.selected_image_id
        await draft.save()
        # Delete unselected images
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        for img_id in (request.unselected_image_ids or []):
            img_path = os.path.join(images_dir, img_id)
            if os.path.exists(img_path):
                os.remove(img_path)
        return {"message": "Image selection saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving selected image: {str(e)}")

@router.post("/business-post/generate-posts")
async def generate_posts(request: GeneratePostsRequest):

    try:
        helper = BusinessPostHelper()
        settings = await PostSettings.filter(user_id=request.user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        post_bundles = []
        for i in range(3):
            bundle = await helper.generate_post_bundle(
                business_idea=request.idea,
                keywords=request.keywords  # Use actual keywords
            )
            post_bundles.append(bundle)
   
        # Save post options and keywords to draft
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            draft.post_options = post_bundles
            # Ensure keywords is always a list for JSONField
            import json
            try:
                parsed_keywords = json.loads(request.keywords)
                if not isinstance(parsed_keywords, (list, dict)):
                    parsed_keywords = [parsed_keywords]
            except Exception:
                parsed_keywords = [request.keywords]
            draft.keywords = parsed_keywords
            await draft.save()
        print(f"Total Posts = {post_bundles}")
        
        return {"posts": post_bundles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating posts: {str(e)}")

@router.post("/business-post/upload-image-for-post")
async def upload_image_for_post(user_id: str = Form(...), post_index: int = Form(...), file: UploadFile = File(...)):
    try:
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        os.makedirs(temp_dir, exist_ok=True)
        filename = f"{user_id}_{file.filename}"
        file_path = os.path.join(temp_dir, filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        # Save image_id to draft (as temp reference)
        draft = await PostDraft.filter(user_id=user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            image_ids = draft.image_ids or [None, None, None]
            image_ids[post_index] = filename
            draft.image_ids = image_ids
            await draft.save()
        return {"image_id": filename, "image_url": f"/api/business-post/display-image/{filename}?temp=1", "post_index": post_index}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")

@router.post("/business-post/generate-image-for-post")
async def generate_image_for_post(request: GenerateImageForPostRequest, image_no: int = Query(0)):
    import re
    try:
        # Fetch settings
        settings = await PostSettings.filter(user_id=request.user_id).first()
        # Always use admin setting for number of images
        setting = await ImageGenerationSetting.filter(id=1).first()
        num_images = setting.num_images if setting else 1
        
        # Always use image options from the request, not from the database
        image_type = getattr(request, 'image_type', '')
        image_design = getattr(request, 'image_design', '')
        instruction = getattr(request, 'instruction', '')
        lighting_effects = getattr(request, 'lighting_effects', '')
        image_mood = getattr(request, 'image_mood', '')
        background_type = getattr(request, 'background_type', '')
        focus_area = getattr(request, 'focus_area', '')
        
        # Get reference images for layout analysis
        reference_layout = None
        if settings and settings.reference_images:
            # Find matching reference image based on image_type
            for ref_image in settings.reference_images:
                if ref_image.get('analysis_type') == image_type:
                    reference_layout = ref_image
                    break
        else:
            print(f"[IMAGE GEN DEBUG] No reference images found for user {request.user_id}")
        print(f"[IMAGE GEN DEBUG] image_design 1: {image_design}")


        # Extract post data fields
        post_title = request.post_data.get('title', '') if hasattr(request, 'post_data') and request.post_data else ''
        post_description = request.post_data.get('description', '') if hasattr(request, 'post_data') and request.post_data else ''
        post_content = request.post_data.get('content', '') if hasattr(request, 'post_data') and request.post_data else ''
        brand_guidelines = getattr(request, 'brand_guidelines', settings.brand_guidelines)
        print(f"[IMAGE GEN DEBUG] brand_guidelines: {brand_guidelines}")

        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')

        # Extract color code from brand_guidelines (e.g., #AABBCC)
        color_code = None
        overview = None
        if brand_guidelines:
            match = re.search(r"#(?:[0-9a-fA-F]{3}){1,2}", brand_guidelines)
            if match:
                color_code = match.group(0)
            # Extract overview if present (e.g., 'Overview: ...')
            overview_match = re.search(r"Overview[:\-\s]+(.+)", brand_guidelines, re.IGNORECASE)
            if overview_match:
                overview = overview_match.group(1).strip()

        def get_focus_area_instruction(focus_area):
            """Generate focus area instruction based on selection"""
            if focus_area == "center":
                return "Center composition, balanced symmetry"
            elif focus_area == "left":
                return "Left-aligned focus and elements"
            elif focus_area == "right":
                return "Right-aligned focus and elements"
            elif focus_area == "random":
                return "Asymmetrical, dynamic placement"
            else:
                return "Balanced composition"

        def get_background_instruction(background_type):
            """Generate background instruction based on selection"""
            if background_type == "plain":
                return "Clean solid background"
            elif background_type == "textured":
                return "Subtle textured background"
            elif background_type == "gradient":
                return "Smooth gradient background"
            else:
                return "Complementary background"

        def get_mood_instruction(image_mood):
            """Generate mood instruction based on selection"""
            if image_mood == "cheerful":
                return "Upbeat, vibrant, energetic"
            elif image_mood == "calm":
                return "Peaceful, soft tones"
            elif image_mood == "mysterious":
                return "Intriguing, deeper tones"
            else:
                return "Balanced emotional tone"

        def get_lighting_instruction(lighting_effects):
            """Generate lighting instruction based on selection"""
            if lighting_effects == "bright":
                return "Bright, well-lit"
            elif lighting_effects == "soft":
                return "Gentle, diffused lighting"
            elif lighting_effects == "dramatic":
                return "High-contrast, bold shadows"
            else:
                return "Natural balanced lighting"

        def truncate_text(text, max_length=100):
            """Truncate text to specified length"""
            if not text:
                return ""
            return text[:max_length] + "..." if len(text) > max_length else text

        def validate_and_trim_prompt(prompt, max_length=2500):
            """Check prompt length and trim if necessary"""
            if len(prompt) <= max_length:
                return prompt
            
            # Find key sections to preserve
            lines = prompt.split('\n')
            essential_lines = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 <= max_length:
                    essential_lines.append(line)
                    current_length += len(line) + 1
                else:
                    break
            
            trimmed_prompt = '\n'.join(essential_lines)
            if len(trimmed_prompt) < max_length - 20:
                trimmed_prompt += "\n[Content trimmed for optimization]"
            
            return trimmed_prompt

        negative_prompt = ""
        aspect_ratio = ""
        variables_mapping = ""
        async def build_prompt(idx):
            # Truncate user-provided fields
            title_truncated = post_title
            description_truncated = post_description
            content_truncated = post_content
            instruction_truncated = instruction
            design_truncated = image_design
            
            # Get shortened instructions for features
            focus_instruction = get_focus_area_instruction(focus_area)
            background_instruction = get_background_instruction(background_type)
            mood_instruction = get_mood_instruction(image_mood)
            lighting_instruction = get_lighting_instruction(lighting_effects)
            
            # Compact feature requirements
            features = f"Focus: {focus_instruction} | BG: {background_instruction} | Mood: {mood_instruction} | Light: {lighting_instruction}"
            
            # Add reference layout analysis if available
            layout_instruction = None
            if reference_layout:
                reference_prompt = reference_layout.get('reference_prompt')
                if reference_prompt:
                    # Try to parse the reference_prompt as JSON if it's a string
                    try:
                        import json
                        layout_instruction = json.loads(reference_prompt)
                    except (json.JSONDecodeError, TypeError):
                        # If it's not valid JSON, use it as is
                        layout_instruction = reference_prompt
                    print(f"[IMAGE GEN DEBUG] Using reference layout for {image_type}: {layout_instruction}")
                else:
                    layout_instruction = None
                    print(f"[IMAGE GEN DEBUG] No reference_prompt found in reference_layout")
            else:
                print(f"[IMAGE GEN DEBUG] No reference layout available for {image_type}")

            if image_type == "text_only":
                # Extract brand colors from brand_guidelines
                brand_colors = ""
                if brand_guidelines:
                    # Extract color codes from brand guidelines
                    color_matches = re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}|rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)", brand_guidelines)
                    if color_matches:
                        brand_colors = f"Use ONLY these brand colors: {', '.join(color_matches)}"
                
                # If we have a reference layout, edit only the text content
                if reference_layout and reference_layout.get('reference_prompt'):
                    print(f"we have in if ={layout_instruction}")
                  
                    # Apply layout variables to the reference prompt
                    result = await compose_prompt_via_langchain(
                        reference_layout_json=layout_instruction,     # ← Step‑1 output
                        title=title_truncated,
                        description=description_truncated,
                    )
                    prompt = result.composed_prompt
                    negative_prompt = result.negative_prompt
                    aspect_ratio = result.aspect_ratio
                    variables_mapping = result.variables_mapping
                    print(f"Negative Prompt are = {negative_prompt}")
                    print(f"here are final prompt = {prompt}")
                else:
                    # Fallback to original prompt if no reference layout
                    print(f"we have in else ")
                    prompt = f"""SOCIAL MEDIA POST - TEXT ONLY LAYOUT
                        Create a social media post graphic (NOT a product mockup)
                        
                        TEXT CONTENT:
                        Title: "{title_truncated}"
                        Description: "{description_truncated}"
                        
                        DESIGN REQUIREMENTS:
                        - Create a new social media post layout
                        - Typography focus with proper color contrast
                        - NO additional graphics, icons, or visual elements
                        - NO product mockups (shirts, mugs, etc.)
                        
                        BRAND COLORS: {brand_colors}
                        STYLE: {design_truncated} typography design
                        {features}
                        EXTRA INSTRUCTIONS: {instruction_truncated}"""
                
            elif image_type == "image_only":
                prompt = f"""SOCIAL MEDIA POST - GRAPHICS ONLY LAYOUT
                    Create a social media post graphic (NOT a product mockup)
                    Theme: {content_truncated}
                    Style: {design_truncated} visual design

                    Rules: 
                    - Create a social media post layout (square format)
                    - NO TEXT/letters/symbols
                    - NO product mockups (shirts, mugs, etc.)
                    - Pure visual illustration for social media
                    - Communicate via visuals only
                    {features}
                    Extra: {instruction_truncated}{layout_instruction}"""
            
            else:  # both
                prompt = f"""SOCIAL MEDIA POST - TEXT + GRAPHICS LAYOUT
                    Create a social media post graphic (NOT a product mockup)
                    Text: "{title_truncated}" | "{description_truncated}"
                    Style: {design_truncated}

                    Rules:
                    - Create a social media post layout (square format)
                    - Clear readable text
                    - High contrast text/bg
                    - Text is primary focus
                    - Graphics support text
                    - NO product mockups (shirts, mugs, etc.)
                    {features}
                    Extra: {instruction_truncated}{layout_instruction}"""

            # Return full prompt without trimming for debugging
            final_prompt = prompt
            print(f"[IMAGE GEN DEBUG] Prompt {idx+1} (Full Length: {len(final_prompt)}):\n{final_prompt}")
            return final_prompt

        prompt = await build_prompt(image_no)
        final_prompt = prompt
        # return final_prompt;
        
        
        image_id = await helper.generate_image(
            brand_guidelines=brand_guidelines,
            post_data=request.post_data,
            references=None,
            mode="generate",
            prompt_override=final_prompt,
            style=image_design,
            negative_prompt=negative_prompt
        )
        src_path = os.path.join(images_dir, image_id)
        temp_path = os.path.join(temp_dir, image_id)
        if os.path.exists(src_path):
            os.rename(src_path, temp_path)
        image_obj = {
            "image_id": image_id,
            "image_url": f"/api/business-post/display-image/{image_id}?temp=1",
            "post_text": post_content,
            "prompt": prompt
        }
        return image_obj
    except Exception as e:
        logging.error(f"Error in image generation: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating images: {str(e)}")
        
@router.post("/business-post/draft/select-post")
async def select_post(request: SelectPostRequest):
    try:
        print(f"[select_post] Incoming request: {request}")
        draft = await PostDraft.get(id=request.draft_id)
        print(f"[select_post] Loaded draft: {draft}")
        if not draft:
            print("[select_post] Draft not found")
            raise HTTPException(status_code=404, detail="Draft not found")
        # Save selected post and image
        if draft.post_options and request.post_text in draft.post_options:
            post_index = draft.post_options.index(request.post_data)
        else:
            print(f"[select_post] post_text not found in post_options. post_text: {request.post_text}, post_options: {draft.post_options}")
            post_index = 0
        draft.selected_post_index = post_index
        draft.selected_image_id = request.image_id
        draft.current_step = 4
        await draft.save()
        # Move selected image from temp_images to images if needed
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        temp_path = os.path.join(temp_dir, request.image_id)
        images_path = os.path.join(images_dir, request.image_id)
        print(f"[select_post] temp_path: {temp_path}, images_path: {images_path}")
        print(f"[select_post] temp_path exists: {os.path.exists(temp_path)}, images_path exists: {os.path.exists(images_path)}")
        try:
            if os.path.exists(temp_path) and not os.path.exists(images_path):
                shutil.move(temp_path, images_path)
                print(f"[select_post] Image moved from temp_images to images: {request.image_id}")
            else:
                print(f"[select_post] Image not moved. temp_path exists: {os.path.exists(temp_path)}, images_path exists: {os.path.exists(images_path)}")
        except Exception as move_err:
            print(f"[select_post] Error moving image: {move_err}")
        print(f"[select_post] Selection saved: post_index={post_index}, image_id={request.image_id}, draft.selected_image_id={draft.selected_image_id}")
        return {"message": "Selection saved"}
    except Exception as e:
        print(f"[select_post] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error selecting post: {str(e)}")

@router.post("/business-post/draft/edit-post")
async def edit_post(request: EditPostRequest):
    try:
        draft = await PostDraft.get(id=request.draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        # Edit the selected post content
        if draft.post_options and draft.selected_post_index is not None:
            draft.post_options[draft.selected_post_index] = request.post_data
        await draft.save()
        return {"message": "Post content updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error editing post: {str(e)}")

@router.post("/business-post/generate-idea")
async def generate_idea(payload: GenerateIdeaPayload):
    try:
        settings = await PostSettings.filter(user_id=payload.user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        print(f"User text = {payload.user_text}")
        print(f"User ID = {payload.user_id}")
        idea = await helper.generate_short_idea(
            user_text=payload.user_text,
        )
        settings.business_idea = idea

        await settings.save()
        print(f"Idea = {idea}")
        return {"idea": idea}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating idea: {str(e)}")

@router.post("/business-post/publish/{draft_id}")
async def publish_post_from_draft(draft_id: int):
    try:
        draft = await PostDraft.get(id=draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if draft.selected_post_index is not None and draft.post_options:
            post_content = draft.post_options[draft.selected_post_index]
        else:
            post_content = draft.content
        # Create BusinessPost with selected image, status 'pending', source 'manual'
        post = await BusinessPost.create(
            user_id=draft.user_id,
            post=post_content,
            status='pending',
            image_id=draft.selected_image_id,
            source='manual'
        )
        draft.is_complete = True
        draft.status = 'published'
        from datetime import datetime
        draft.posted_at = datetime.utcnow()
        await draft.save()
        return {
            "id": post.id,
            "post": post.post,
            "status": post.status,
            "created_at": post.created_at.isoformat(),
            "image_id": post.image_id,
            "posted_at": draft.posted_at.isoformat() if draft.posted_at else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error publishing post: {str(e)}")

@router.post("/business-post/mark-posted/{post_id}")
async def mark_post_as_posted(post_id: int):
    try:
        post = await BusinessPost.get(id=post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        post.status = 'posted'
        await post.save()
        return {"message": "Post marked as posted", "id": post.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking post as posted: {str(e)}")

@router.put("/posts/{post_id}", response_model=BusinessPostResponse)
async def update_post(post_id: int, request: BusinessPostUpdateRequest):
    try:
        if request.status == "draft":
            draft = await PostDraft.get(id=post_id)
            if not draft:
                raise HTTPException(status_code=404, detail="Draft not found")
            if request.post is not None:
                draft.content = request.post
            if request.title is not None:
                draft.title = request.title
            if hasattr(request, 'description') and request.description is not None:
                draft.description = request.description
            # Update post_options at selected_post_index
            if draft.post_options and draft.selected_post_index is not None:
                idx = draft.selected_post_index
                if 0 <= idx < len(draft.post_options):
                    opt = draft.post_options[idx]
                    if isinstance(opt, dict):
                        opt['content'] = request.post if request.post is not None else opt.get('content', '')
                        opt['title'] = request.title if request.title is not None else opt.get('title', '')
                        opt['description'] = request.description if hasattr(request, 'description') and request.description is not None else opt.get('description', '')
                        draft.post_options[idx] = opt
            await draft.save()
            return BusinessPostResponse(
                id=draft.id,
                post=draft.content,
                status='draft',
                created_at=draft.created_at.isoformat(),
                title=getattr(draft, 'title', None),
                description=getattr(draft, 'description', None),
            )
        else:
            post = await BusinessPost.get(id=post_id)
            if not post:
                raise HTTPException(status_code=404, detail="Post not found")
            if request.post is not None:
                post.post = request.post
            if request.title is not None:
                post.title = request.title
            await post.save()
            return BusinessPostResponse(
                id=post.id,
                post=post.post,
                status=post.status,
                created_at=post.created_at.isoformat(),
                title=getattr(post, 'title', None),
            )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error updating post: {str(e)}")


@router.post("/post-settings/image-options")
async def upsert_image_settings(request: ImageSettingsRequest):
    print(f"data = {request}")
    try:
        existing = await ImageSettings.filter(user_id=request.user_id).first()
        if existing:
            existing.image_type = request.image_type
            existing.image_design = request.image_design
            existing.instruction = request.instruction
            existing.lighting_effects = request.lighting_effects
            existing.image_mood = request.image_mood
            existing.background_type = request.background_type
            existing.focus_area = request.focus_area
            await existing.save()
            settings = existing
        else:
            settings = await ImageSettings.create(
                user_id=request.user_id,
                image_type=request.image_type,
                image_design=request.image_design,
                instruction=request.instruction,
                lighting_effects=request.lighting_effects,
                image_mood=request.image_mood,
                background_type=request.background_type,
                focus_area=request.focus_area
            )
        return ImageSettingsResponse(
            user_id=settings.user_id,
            image_type=settings.image_type or "",
            image_design=settings.image_design or "",
            instruction=settings.instruction or "",
            lighting_effects=settings.lighting_effects or "",
            image_mood=settings.image_mood or "",
            background_type=settings.background_type or "",
            focus_area=settings.focus_area or "",
            created_at=settings.created_at.isoformat(),
            updated_at=settings.updated_at.isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error upserting image settings: {str(e)}")

@router.get("/post-settings/image-options", response_model=ImageSettingsResponse)
async def get_image_settings(user_id: str = Query(...)):
    try:
        settings = await ImageSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Image settings not found")
        return ImageSettingsResponse(
            user_id=settings.user_id,
            image_type=settings.image_type or "",
            image_design=settings.image_design or "",
            instruction=settings.instruction or "",
            lighting_effects=settings.lighting_effects or "",
            image_mood=settings.image_mood or "",
            background_type=settings.background_type or "",
            focus_area=settings.focus_area or "",
            created_at=settings.created_at.isoformat(),
            updated_at=settings.updated_at.isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching image settings: {str(e)}")

@router.get("/admin/image-generation-setting")
async def get_image_generation_setting():
    setting = await ImageGenerationSetting.filter(id=1).first()
    if not setting:
        # Create default if not exists
        setting = await ImageGenerationSetting.create(id=1, num_images=1)
    return {"num_images": setting.num_images}

@router.post("/admin/image-generation-setting")
async def set_image_generation_setting(payload: ImageGenSettingRequest):
    num_images = payload.num_images
    setting = await ImageGenerationSetting.filter(id=1).first()
    if not setting:
        setting = await ImageGenerationSetting.create(id=1, num_images=num_images)
    else:
        setting.num_images = num_images
        await setting.save()
    return {"num_images": setting.num_images}

@router.post("/business-post/upload-reference-image")
async def upload_reference_image(
    file: UploadFile = File(...),
    analysis_type: str = Form(...),
    user_id: str = Form(...)
):
    """
    Upload reference image, analyze its layout, and save both image and analysis to database
    """
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save the uploaded image
        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'reference_images')
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"ref_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = os.path.join(uploads_dir, unique_filename)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(await file.read())
        
        # Analyze the image layout using GPT Vision
        image_content = open(file_path, "rb").read()
        base64_image = base64.b64encode(image_content).decode('utf-8')
        
                # Get user's post settings or create if doesn't exist
        post_settings = await PostSettings.filter(user_id=user_id).first()
        if not post_settings:
            # Create default post settings for the user
            post_settings = await PostSettings.create(
                user_id=user_id,
                business_idea="",
                brand_guidelines="",
                frequency="daily",
                posts_per_period=1
            )

        # Create OpenAI client
        api_settings = await get_settings()
        client = OpenAI(api_key=api_settings["openai_api_key"])
        
        # Define analysis prompt based on type - comprehensive design analysis
        analysis_prompts = analyse_refference_image()
        
        # prompt = analysis_prompts.get(analysis_type, analysis_prompts["image_only"])
        prompt = analysis_prompts
     
        
        # Call GPT Vision API
        response = client.chat.completions.create(
            # model="gpt-4o-mini",
            model="gpt-4.1-mini",
            messages=[
               {
                 "role": "system",
                    "content": f"""You are an expert graphic designer and layout analyst. **Do not include** any analysis of icons, logos, graphical illustrations, or URLs."""
                },

                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1
        )
        analysis_result = response.choices[0].message.content
        print(f"anaylsis Result = {analysis_result}")
        
        # Prepare reference image data (only necessary fields)
        reference_data = {
            "image_filename": unique_filename,
            "analysis_type": analysis_type,
            "reference_prompt": analysis_result,
            "uploaded_at": datetime.now().isoformat(),
            "file_size": os.path.getsize(file_path)
        }
        
        # Update reference_images field
        current_references = getattr(post_settings, 'reference_images', []) or []
        print(f"current_references 1 = {current_references}")
        
        # Remove existing image of the same type (replace instead of append)
        current_references = [ref for ref in current_references if ref.get('analysis_type') != analysis_type]
        print(f"current_references 2 = {current_references}")
        
        # Add the new reference image
        current_references.append(reference_data)
        print(f"current_references 3 = {current_references}")
        
        # Keep only the last 10 reference images (though we should only have 3 max now)
        if len(current_references) > 10:
            current_references = current_references[-10:]
            print(f"current_references 4 in if = {current_references}")
        
        post_settings.reference_images = current_references
        await post_settings.save()
        
        return {
            "success": True,
            "message": "Reference image uploaded and analyzed successfully",
            "image_filename": unique_filename,
            "analysis_type": analysis_type
        }
        
    except Exception as e:
        logging.error(f"Error in reference image upload: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading reference image: {str(e)}")

@router.get("/business-post/display-reference-image/{filename}")
async def display_reference_image(filename: str):
    """
    Display reference images from the reference_images folder
    """
    try:
        reference_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'reference_images')
        file_path = os.path.join(reference_dir, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Reference image not found: {filename}")
        
        return FileResponse(file_path)
        
    except Exception as e:
        logging.error(f"Error displaying reference image: {e}")
        raise HTTPException(status_code=500, detail=f"Error displaying reference image: {str(e)}")
