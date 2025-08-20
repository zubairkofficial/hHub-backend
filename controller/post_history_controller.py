from fastapi import APIRouter, HTTPException, status
from tortoise import Tortoise
from tortoise.exceptions import DoesNotExist
from models.post_history import PostHistory
from models.post_draft import PostDraft
from pydantic import BaseModel
from typing import List, Dict
from enum import Enum

# FastAPI app instance
router = APIRouter()

class PageTypeEnum(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"

# Pydantic model for input validation
class PageData(BaseModel):
    page_name: str
    status: str
    message: str

class PostHistoryIn(BaseModel):
    user_id: str
    post_draft_id: str
    selected_pages: List[PageData]  # List of pages selected
    page_type: PageTypeEnum

@router.post("/post_history/save")
async def create_post_history(post_history:PostHistoryIn):
    print(f"data of history = {post_history}")
    try:
        # Retrieve the PostDraft record
        post_draft = await PostDraft.get(id=post_history.post_draft_id)
        
        # Loop through each selected page and process it
        for page_data in post_history.selected_pages:
            # Log page data (as you mentioned, similar to PHP logging)
            print(f"Processing page: {page_data.page_name}")
            
            # Log partial token for security purposes (similar to your PHP example)
            print(f"Calling uploadImageUsingUrl for page: {page_data.page_name}")

            # Create a new PostHistory record for each page
            await PostHistory.create(
                user_id=post_history.user_id,
                post_draft_id=post_history.post_draft_id,
                page_name=page_data.page_name,  # Use the page name
                page_type=post_history.page_type,
                status=page_data.status,
                message=page_data.message
            )

        # Return a success message
        return {"message": "Post history created for selected pages"}

    except DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PostDraft not found"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
