from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from helper.business_post_helper import BusinessPostHelper
from models.post_settings import PostSettings
from models.business_post import BusinessPost
from typing import List, Optional
from datetime import datetime

router = APIRouter()

class PostSettingsRequest(BaseModel):
    user_id: int
    business_idea: str
    brand_guidelines: str = None
    frequency: str = 'daily'
    posts_per_period: int = 1

class PostSettingsResponse(BaseModel):
    id: int
    user_id: int
    business_idea: str
    brand_guidelines: str = None
    frequency: str
    posts_per_period: int

class BusinessPostResponse(BaseModel):
    id: int
    post: str
    status: str
    created_at: str

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

# @router.get("/post-settings", response_model=List[PostSettingsResponse])
# async def get_all_post_settings():
#     try:
#         settings = await PostSettings.all()
#         return [
#             PostSettingsResponse(
#                 id=s.id,
#                 user_id=s.user_id,
#                 business_idea=s.business_idea,
#                 brand_guidelines=s.brand_guidelines,
#                 frequency=s.frequency,
#                 posts_per_period=s.posts_per_period
#             ) for s in settings
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching post settings: {str(e)}")

# @router.get("/post-settings/{settings_id}", response_model=PostSettingsResponse)
# async def get_post_settings(settings_id: int):
#     try:
#         settings = await PostSettings.get(id=settings_id)
#         return PostSettingsResponse(
#             id=settings.id,
#             user_id=settings.user_id,
#             business_idea=settings.business_idea,
#             brand_guidelines=settings.brand_guidelines,
#             frequency=settings.frequency,
#             posts_per_period=settings.posts_per_period
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching post settings: {str(e)}")

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
                created_at=post.created_at.isoformat()
            ) for post in posts
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching posts: {str(e)}")

@router.post("/approve-post/{post_id}")
async def approve_post(post_id: int = Path(..., description="ID of the post to approve")):
    try:
        post = await BusinessPost.get(id=post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        post.status = 'posted'
        await post.save()
        return {"message": "Post approved and status updated to 'posted'", "id": post.id, "status": post.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving post: {str(e)}") 