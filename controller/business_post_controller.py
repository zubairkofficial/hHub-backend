from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from helper.business_post_helper import BusinessPostHelper
from helper.extract_data_from_image import extract_data_from_img
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
import asyncio
from models.post_prompt_settings import PostPromptSettings
import re
import json
from io import BytesIO
from models.image_settings import ImageSettings
from models.image_generation_setting import ImageGenerationSetting
from pydantic import BaseModel

router = APIRouter()

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
    reference_images: Optional[List[str]] = None


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

        # Ensure reference_images is a list, not a string
        reference_images = settings.reference_images
        if isinstance(reference_images, str):
            try:
                reference_images = json.loads(reference_images)
                print(f"[DEBUG] Parsed reference_images: {reference_images} (type: {type(reference_images)})")
            except Exception as e:
                print(f"[DEBUG] Error parsing reference_images: {e}")
                reference_images = [None, None, None]
        if not isinstance(reference_images, list):
            print(f"[DEBUG] reference_images is not a list after parsing, setting to [None, None, None]")
            reference_images = [None, None, None]
        while len(reference_images) < 3:
            reference_images.append(None)
        reference_images = reference_images[:3]
        # Convert all None to empty string for Pydantic
        reference_images = [img if isinstance(img, str) else "" for img in reference_images]
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
            LLM_API_KEY = os.getenv("OPENAI_API_KEY")
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
    logging.warning(f"Request body: {request}")
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

        def validate_and_trim_prompt(prompt, max_length=1000):
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

        def build_prompt(idx):
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

            if image_type == "text_only":
                prompt = f"""TEXT ONLY Post
                    Title: "{title_truncated}"
                    Desc: "{description_truncated}"
                    Style: {design_truncated} typography design

                    Rules:
                    - Typography focus only
                    - NO graphics/icons
                    - Creative text layouts
                    - Color schemes for text/bg
                    {features}
                    Extra: {instruction_truncated}"""
                
            elif image_type == "image_only":
                prompt = f"""GRAPHICS ONLY Post
                    Theme: {content_truncated}
                    Style: {design_truncated} visual design

                    Rules: 
                    - NO TEXT/letters/symbols
                    - Pure visual illustration
                    - Communicate via visuals only
                    {features}
                    Extra: {instruction_truncated}"""
            
            else:  # both
                prompt = f"""TEXT + GRAPHICS Post
                    Text: "{title_truncated}" | "{description_truncated}"
                    Style: {design_truncated}

                        Rules:
                        - Clear readable text
                        - High contrast text/bg
                        - Text is primary focus
                        - Graphics support text
                        {features}
                        Extra: {instruction_truncated}"""

            # Validate and trim if needed
            final_prompt = prompt
            print(f"[IMAGE GEN DEBUG] Prompt {idx+1} (Length: {len(final_prompt)}):\n{final_prompt}")
            return final_prompt

        prompt = build_prompt(image_no)
        print(f"[IMAGE GEN DEBUG] image_desing: {image_design}")
        image_id = await helper.generate_image(
            brand_guidelines=brand_guidelines,
            post_data=request.post_data,
            references=None,
            mode="generate",
            prompt_override=prompt,
            style=image_design
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

        logging.warning("Returning image generation response (single image)")
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

# --- Super Admin Post Prompt Endpoints ---
@router.get("/post-prompts")
async def get_post_prompts():
    prompt = await PostPromptSettings.first()
    if not prompt:
        return {
            "post_prompt": "",
            "idea_prompt": "",
            "image_prompt": "",
        }
    return {
        "post_prompt": prompt.post_prompt,
        "idea_prompt": prompt.idea_prompt,
        "image_prompt": prompt.image_prompt,
    }

@router.post("/post-prompts")
async def update_post_prompts(data: dict):
    prompt = await PostPromptSettings.first()
    if not prompt:
        prompt = await PostPromptSettings.create(
            post_prompt=data.get("post_prompt"),
            idea_prompt=data.get("idea_prompt"),
            image_prompt=data.get("image_prompt"),
        )
    else:
        prompt.post_prompt = data.get("post_prompt", prompt.post_prompt)
        prompt.idea_prompt = data.get("idea_prompt", prompt.idea_prompt)
        prompt.image_prompt = data.get("image_prompt", prompt.image_prompt)
        await prompt.save()
    return {
        "post_prompt": prompt.post_prompt,
        "idea_prompt": prompt.idea_prompt,
        "image_prompt": prompt.image_prompt,
    }

@router.get("/post-prompts/defaults")
async def get_post_prompt_defaults():
    return {
        "post_prompt": "",
        "idea_prompt": "",
        "image_prompt": "",
    }



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
