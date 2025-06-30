from fastapi import APIRouter, HTTPException, Path, Query
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
            await existing.save()
            settings = existing
        else:
            settings = await PostSettings.create(
                user_id=request.user_id,
                business_idea=request.business_idea,
                brand_guidelines=request.brand_guidelines,
                frequency=request.frequency,
                posts_per_period=request.posts_per_period
            )
        return PostSettingsResponse(
            id=settings.id,
            user_id=settings.user_id,
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            frequency=settings.frequency,
            posts_per_period=settings.posts_per_period
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error upserting post settings: {str(e)}")
    
@router.get("/post-settings", response_model=PostSettingsResponse)
async def get_post_settings(user_id: int = Query(...)):
    try:
        settings = await PostSettings.filter(user_id=user_id).first()
        if not settings:
            raise HTTPException(status_code=404, detail="Settings not found")

        # Generate a preview image if brand guidelines are provided
        preview_image_id = None
        if settings.brand_guidelines:
            try:
                preview_image_id = await helper.generate_image(settings.business_idea, settings.brand_guidelines)
                print(f"[Image Generation] Generated preview image for user {user_id}")
            except Exception as e:
                print(f"[Image Generation] Error generating preview image for user {user_id}: {str(e)}")

        return PostSettingsResponse(
            id=settings.id,
            user_id=settings.user_id,
            business_idea=settings.business_idea,
            brand_guidelines=settings.brand_guidelines,
            frequency=settings.frequency,
            posts_per_period=settings.posts_per_period,
            preview_image_id=preview_image_id
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



@router.get('/display-image/{image_id}')
def display_image(image_id: str):
    try:
        image_id = unquote(image_id)
        image_folder = 'images'
        # Try with no extension
        image_path = os.path.join(image_folder, image_id)
        if os.path.exists(image_path):
            return FileResponse(path=image_path, media_type='image/jpeg')
        # Try with .jpg
        image_path_jpg = os.path.join(image_folder, image_id + '.jpg')
        if os.path.exists(image_path_jpg):
            return FileResponse(path=image_path_jpg, media_type='image/jpeg')
        # Try with .png
        image_path_png = os.path.join(image_folder, image_id + '.png')
        if os.path.exists(image_path_png):
            return FileResponse(path=image_path_png, media_type='image/png')
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
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

