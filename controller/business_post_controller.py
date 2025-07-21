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
        if temp:
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
            image_path = os.path.join(temp_dir, image_id)
        else:
            images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
            image_path = os.path.join(images_dir, image_id)
        if os.path.exists(image_path):
            return FileResponse(path=image_path, media_type='image/png')
        # Try with .jpg
        if os.path.exists(image_path + '.jpg'):
            return FileResponse(path=image_path + '.jpg', media_type='image/jpeg')
        if os.path.exists(image_path + '.png'):
            return FileResponse(path=image_path + '.png', media_type='image/png')
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
        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        file_location = os.path.join(uploads_dir, file.filename)
        with open(file_location, "wb") as f:
            f.write(await file.read())

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
                "Given the following extracted content from a brand guidelines document, generate a comprehensive summary of the post guidelines. "
                "The summary should describe how posts should look, including logo usage, color palette, typography, and any other visual or content rules. "
                "Focus on actionable instructions for generating social media posts that match the brand's style.\n\n"
                f"Extracted Content:\n{all_text}\n\nSummary:"
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
    # return [{"image_id":"png_skoid_475fd488-6c59-44a5-9aa9-31c4db451bea_sktid_a48cca56-e6da-484e-a814-9c849652bcb3_skt_2025-07-18T12_27_44Z_ske_2025-07-19T12_27_44Z_sks_b_skv_2024-08-04_sig_pOM3NJ9ywptoIB8ODajdLhizNf85qNUImL1SolV3ktc_.png","image_url":"/api/business-post/display-image/png_skoid_475fd488-6c59-44a5-9aa9-31c4db451bea_sktid_a48cca56-e6da-484e-a814-9c849652bcb3_skt_2025-07-18T12_27_44Z_ske_2025-07-19T12_27_44Z_sks_b_skv_2024-08-04_sig_pOM3NJ9ywptoIB8ODajdLhizNf85qNUImL1SolV3ktc_.png?temp=1","post_text":"\"Transform $500 into a magical scrub adventure! 🌟 Share your scrubby story with us! #ScrubbersUnite\""},{"image_id":"79Og0FzSQCSZ8_.png","image_url":"/api/business-post/display-image/79Og0FzSQCSZ8_.png?temp=1","post_text":"\"Transform $500 into a magical scrub adventure! 🌟 Share your scrubby story with us! #ScrubbersUnite\""},{"image_id":"aHmT0fFHtgqGL3jqiqPjQ_.png","image_url":"/api/business-post/display-image/aHmT0fFHtgqGL3jqiqPjQ_.png?temp=1","post_text":"\"Transform $500 into a magical scrub adventure! 🌟 Share your scrubby story with us! #ScrubbersUnite\""}]
    logging.warning(f"Request body: {request}")
    try:
        settings = await PostSettings.filter(user_id=request.user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        os.makedirs(temp_dir, exist_ok=True)
        # Parallel image generation
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
        # draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        # if draft:
        #     post_options = draft.post_options or []
        #     try:
        #         post_index = post_options.index(request.post_text)
        #     except ValueError:
        #         post_index = 0
        #     draft_image_ids = draft.image_ids or [None, None, None]
        #     draft_image_ids[post_index] = image_id_list  # Save all 3 image ids for this post index
        #     draft.image_ids = draft_image_ids
        #     await draft.save()
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

