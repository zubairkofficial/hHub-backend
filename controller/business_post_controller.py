from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from helper.business_post_helper import BusinessPostHelper
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
    post_text: str

class SelectPostRequest(BaseModel):
    draft_id: int
    post_text: str
    image_id: str

class EditPostRequest(BaseModel):
    draft_id: int
    post_text: str

class BusinessPostUpdateRequest(BaseModel):
    post: Optional[str] = None
    title: Optional[str] = None
    image_id: Optional[str] = None
    status:Optional[str] = None

class GenerateIdeaPayload(BaseModel):
    user_id: str = Field(...)
    user_text: str = Field(...)


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


@router.get("/posts", response_model=List[BusinessPostResponse])
async def get_all_posts(user_id: Optional[int] = Query(None, description="User ID to filter posts")):
    try:
        if user_id is not None:
            posts = await BusinessPost.filter(user_id=user_id).order_by('-created_at')
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
        for draft in drafts:
            draft = await PostDraft.get(id=draft.id)
            post_text = None
            if draft.post_options and draft.selected_post_index is not None and 0 <= draft.selected_post_index < len(draft.post_options):
                post_text = draft.post_options[draft.selected_post_index]
            else:
                post_text = draft.content
                
            result.append({
                "id": draft.id,
                "post": post_text or "",
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
async def upload_post_settings_file(user_id: int = Query(...), file: UploadFile = File(...)):
    try:
        # Max file size in bytes (10 MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 10 MB.")
        # Reset file pointer for further reading
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

        # Generate summary using external LLM if all_text is available
        if all_text:
            LLM_API_URL = "https://api.openai.com/v1/chat/completions"
            LLM_API_KEY = os.getenv("OPENAI_API_KEY")
            prompt = (
                "You are an expert in social media branding. "
                "Given the following extracted content from a brand guidelines document, do the following:\n"
                "1. Extract the color palette as a list of hex color codes. For each color, specify if it is primary, secondary, accent, or other (if possible). Output each color on a new line in the format: <label>: <hex> (e.g., Primary: #FF5733). If the role is not clear, just output the hex code.\n"
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
        else:
            summary = None

        # Save the filename and extracted summary in the user's PostSettings
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        settings.uploaded_file = file.filename
        if business_idea:
            settings.business_idea = business_idea
        if brand_guidelines:
            settings.brand_guidelines = summary
        if summary:
            settings.extracted_file_text = summary
        await settings.save()

        print(summary)
        return {
            "filename": file.filename,
            "business_idea": business_idea,
            "brand_guidelines": brand_guidelines,
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
        if draft_id:
            draft = await PostDraft.get(id=draft_id)
            if not draft:
                raise HTTPException(status_code=404, detail="Draft not found")
            draft.current_step = request.current_step
            draft.content = request.content
            draft.keywords = request.keywords
            draft.post_options = getattr(request, "post_options", None)
            draft.selected_post_index = getattr(request, "selected_post_index", None)
            draft.image_ids = getattr(request, "image_ids", None)
            draft.selected_image_id = getattr(request, "selected_image_id", None)
            draft.is_complete = is_complete
            await draft.save()
        else:
            draft = await PostDraft.create(
                user_id=request.user_id,
                current_step=request.current_step,
                content=request.content,
                keywords=request.keywords,
                post_options=getattr(request, "post_options", None),
                selected_post_index=getattr(request, "selected_post_index", None),
                image_ids=getattr(request, "image_ids", None),
                selected_image_id=getattr(request, "selected_image_id", None),
                is_complete=is_complete,
            )
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
        posts = []
        for i in range(3):
            post_text = await helper.generate_post(
                business_idea=request.idea,
                brand_guidelines=settings.brand_guidelines,
                extracted_file_text=request.keywords
            )
            posts.append(post_text)
        # Save post options to draft
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            draft.post_options = posts
            await draft.save()
        print(f"Total Posts = {len(posts)}")
        return {"posts": posts}
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
async def generate_image_for_post(request: GenerateImageForPostRequest):
    logging.warning(f"Request body: {request}")
    try:
        settings = await PostSettings.filter(user_id=request.user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        # ref_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'reference_images')
        # os.makedirs(temp_dir, exist_ok=True)
        # Load reference images from PostSettings if present
        # reference_images = []
        # if settings.reference_images:
        #     for filename in settings.reference_images:
        #         if filename and isinstance(filename, str):  # Only process valid filenames
        #             file_path = os.path.join(ref_dir, filename)
        #             if os.path.exists(file_path):
        #                 reference_images.append(file_path)
        #                 # with open(file_path, "rb") as f:
        #                 #     reference_images.append(f.read())
        # Parallel image generation
        # mode = 'analyze' if reference_images else 'generate'
        
        
        async def generate_and_move():
            image_id = await helper.generate_image(
                brand_guidelines=settings.brand_guidelines,
                post_text=request.post_text
            )
            src_path = os.path.join(images_dir, image_id)
            temp_path = os.path.join(temp_dir, image_id)
            if os.path.exists(src_path):
                os.rename(src_path, temp_path)
            return image_id
        image_id_list = await asyncio.gather(*[generate_and_move() for _ in range(3)])
        image_objs = [
            {
                "image_id": image_id,
                "image_url": f"/api/business-post/display-image/{image_id}?temp=1",
                "post_text": request.post_text
            }
            for image_id in image_id_list
        ]
        # Save image_ids to draft (as temp reference)
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            post_options = draft.post_options or []
            try:
                post_index = post_options.index(request.post_text)
            except ValueError:
                post_index = 0
            draft_image_ids = draft.image_ids or [None, None, None]
            draft_image_ids[post_index] = image_id_list  # Save all 3 image ids for this post index
            draft.image_ids = draft_image_ids
            await draft.save()
        logging.warning("Returning image generation response (3 images, parallel)")
        return {"images": image_objs}
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
            post_index = draft.post_options.index(request.post_text)
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
            draft.post_options[draft.selected_post_index] = request.post_text
        else:
            draft.content = request.post_text
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
            if request.image_id is not None:
                draft.selected_image_id = request.image_id
            await draft.save()
            return BusinessPostResponse(
                id=draft.id,
                post=draft.content,
                status='draft',
                created_at=draft.created_at.isoformat(),
                title=getattr(draft, 'title', None),
                image_id=getattr(draft, 'selected_image_id', None)
            )
        else:
            post = await BusinessPost.get(id=post_id)
            if not post:
                raise HTTPException(status_code=404, detail="Post not found")
            if request.post is not None:
                post.post = request.post
            if request.title is not None:
                post.title = request.title
            if request.image_id is not None:
                post.image_id = request.image_id
            await post.save()
            return BusinessPostResponse(
                id=post.id,
                post=post.post,
                status=post.status,
                created_at=post.created_at.isoformat(),
                title=getattr(post, 'title', None),
                image_id=getattr(post, 'image_id', None)
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

@router.post("/business-post/upload-reference-image")
async def upload_reference_image(user_id: str = Form(...), slot: int = Form(...), file: UploadFile = File(...)):
    import os
    images_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reference_images'))
    os.makedirs(images_dir, exist_ok=True)
    def sanitize_filename(filename, max_length=100):
        import re
        filename = re.sub(r'[<>:"/\\|?*%&=]', '_', filename)
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            filename = name[:max_length-len(ext)] + ext
        return filename
    slot = max(1, min(3, int(slot)))  # Ensure slot is 1, 2, or 3
    filename = sanitize_filename(f"ref_{user_id}_{slot}_{file.filename}")
    file_path = os.path.join(images_dir, filename)
    print(f"Saving reference image to: {file_path}")
    with open(file_path, "wb") as f:
        f.write(await file.read())
    # Update the correct slot in PostSettings
    settings = await PostSettings.filter(user_id=user_id).first()
    if settings:
        ref_images = settings.reference_images or [None, None, None]
        # Ensure the list is always 3 elements
        while len(ref_images) < 3:
            ref_images.append(None)
        ref_images[slot-1] = filename
        settings.reference_images = ref_images
        await settings.save()
    return {"message": f"Reference image for slot {slot} uploaded", "filename": filename}

