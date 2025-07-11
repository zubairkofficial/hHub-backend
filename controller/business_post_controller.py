from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
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
    image_id: Optional[str] = None
    is_draft: bool = True

class ImageSelectionRequest(BaseModel):
    draft_id: int
    selected_image_id: str
    unselected_image_ids: Optional[list] = None

class GeneratePostsRequest(BaseModel):
    user_id: str
    keywords: list

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

helper = BusinessPostHelper()

@router.post("/post-settings", response_model=PostSettingsResponse)
async def upsert_post_settings(request: PostSettingsRequest):
    try:
        existing = await PostSettings.filter(user_id=request.user_id).first()
        if existing:
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
        # Only fetch posts that are actually published and from automation
        if user_id is not None:
            posts = await BusinessPost.filter(user_id=user_id, status='posted', source='auto').order_by('-created_at')
        else:
            posts = await BusinessPost.filter(status='posted', source='auto').order_by('-created_at')
        return [
            BusinessPostResponse(
                id=post.id,
                post=post.post,
                status=post.status,
                created_at=post.created_at.isoformat(),
                image_id=getattr(post, 'image_id', None)
            ) for post in posts
        ]
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
                from PyPDF2 import PdfReader
                reader = PdfReader(file_location)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                all_text = text
                lines = text.splitlines()
                if lines:
                    business_idea = lines[0]
                    brand_guidelines = "\n".join(lines[1:])
            except Exception as e:
                print(f"PDF extraction error: {e}")
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

        # Save the filename and extracted data in the user's PostSettings
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")
        settings.uploaded_file = file.filename
        if business_idea:
            settings.business_idea = business_idea
        if brand_guidelines:
            settings.brand_guidelines = brand_guidelines
        if all_text:
            settings.extracted_file_text = all_text
        await settings.save()

        return {
            "filename": file.filename,
            "business_idea": business_idea,
            "brand_guidelines": brand_guidelines,
            "extracted_file_text": all_text,
            "message": "File uploaded and data extracted successfully"
        }
    except Exception as e:
        print(f"error {str(e)}")

@router.post("/business-post/draft")
async def save_or_update_draft(request: DraftRequest):
    try:
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if not draft:
            draft = await PostDraft.create(
                user_id=request.user_id,
                current_step=request.current_step,
                content=request.content,
                keywords=request.keywords,
            )
        else:
            draft.current_step = request.current_step
            draft.content = request.content
            draft.keywords = request.keywords
            await draft.save()
        return {"message": "Draft saved", "draft_id": draft.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving draft: {str(e)}")

@router.get("/business-post/draft/active")
async def get_active_draft(user_id: str):
    try:
        draft = await PostDraft.filter(user_id=user_id, is_complete=False).order_by('-updated_at').first()
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
            "selected_image_id": draft.selected_image_id
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
                extracted_file_text=settings.extracted_file_text or content
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
                business_idea=settings.business_idea,
                brand_guidelines=settings.brand_guidelines,
                extracted_file_text=" ".join(request.keywords)
            )
            posts.append(post_text)
        # Save post options to draft
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            draft.post_options = posts
            await draft.save()
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
        image_id = await helper.generate_image(
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            extracted_file_text=request.post_text
        )
        # Move generated image to temp_images if not already there
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        os.makedirs(temp_dir, exist_ok=True)
        src_path = os.path.join(images_dir, image_id)
        temp_path = os.path.join(temp_dir, image_id)
        if os.path.exists(src_path):
            os.rename(src_path, temp_path)
        # Save image_id to draft (as temp reference)
        draft = await PostDraft.filter(user_id=request.user_id, is_complete=False).order_by('-updated_at').first()
        if draft:
            post_options = draft.post_options or []
            try:
                post_index = post_options.index(request.post_text)
            except ValueError:
                post_index = 0
            image_ids = draft.image_ids or [None, None, None]
            image_ids[post_index] = image_id
            draft.image_ids = image_ids
            await draft.save()
        logging.warning("Returning image generation response")
        return {
            "image_id": image_id,
            "image_url": f"/api/business-post/display-image/{image_id}?temp=1",
            "post_text": request.post_text
        }
    except Exception as e:
        logging.error(f"Error in image generation: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")

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
        if os.path.exists(temp_path) and not os.path.exists(images_path):
            shutil.move(temp_path, images_path)
        print(f"[select_post] Selection saved: post_index={post_index}, image_id={request.image_id}")
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
async def generate_idea(user_id: str = Form(...)):
    try:
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Post settings not found")
        helper = BusinessPostHelper()
        idea = await helper.generate_short_idea(
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            extracted_file_text=settings.extracted_file_text
        )
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
        await draft.save()
        return {
            "id": post.id,
            "post": post.post,
            "status": post.status,
            "created_at": post.created_at.isoformat(),
            "image_id": post.image_id
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

