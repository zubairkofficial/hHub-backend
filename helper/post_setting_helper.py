import os
from models.post_prompt_settings import PostPromptSettings


async def get_settings():
    """Get all settings with API key fallback to .env"""
    settings = await PostPromptSettings.first()
    
    if not settings:
        return {
            "post_prompt": "",
            "idea_prompt": "",
            "image_prompt": "",
            "fal_ai_api_key": os.getenv("FAL_KEY", ""),
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        }
    
    return {
        "post_prompt": settings.post_prompt or "",
        "idea_prompt": settings.idea_prompt or "",
        "image_prompt": settings.image_prompt or "",
        "fal_ai_api_key": settings.fal_ai_api_key or os.getenv("FAL_KEY", ""),
        "openai_api_key": settings.openai_api_key or os.getenv("OPENAI_API_KEY", ""),
    }
