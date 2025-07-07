from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from helper.business_post_helper import BusinessPostHelper
from models.post_settings import PostSettings
from models.business_post import BusinessPost
from typing import List, Optional
from datetime import datetime
import os
from urllib.parse import unquote
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
        if user_id is not None:
            posts = await BusinessPost.filter(user_id=user_id).order_by('-created_at')
        else:
            posts = await BusinessPost.all().order_by('-created_at')
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
def display_image(image_id: str):
    try:
        return display_image_helper(image_id)
    except Exception as e:
        print(f"Error in display_image: {e}")
        raise HTTPException(detail=str(e), status_code=400)
    
@router.post("/approve-post/{post_id}")
async def approve_post(post_id: int = Path(..., description="ID of the post to approve")):
    try:
        post = await BusinessPost.get(id=post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Update post status to 'posted'
        post.status = 'posted'
        await post.save()

        # Generate the post URL for sharing
        post_url = f"https://your-website-url.com/post/{post.id}"  # Post URL for sharing
        
        return {"message": "Post approved and status updated to 'posted'", "id": post.id, "status": post.status, "post_url": post_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving post: {str(e)}")
    
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

