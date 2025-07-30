from fastapi import APIRouter,HTTPException
from models.post_prompt_settings import PostPromptSettings

router = APIRouter()
# --- Super Admin Post Prompt Endpoints ---

@router.get("/post-prompts")
async def get_post_prompts():
    prompt = await PostPromptSettings.first()
    if not prompt:
        return {
            "post_prompt": "",
            "idea_prompt": "",
            "image_prompt": "",
            "fal_ai_api_key": "",
            "openai_api_key": "",
            
        }
    return {
        "post_prompt": prompt.post_prompt,
        "idea_prompt": prompt.idea_prompt,
        "image_prompt": prompt.image_prompt,
        "fal_ai_api_key": prompt.fal_ai_api_key,
        "openai_api_key": prompt.openai_api_key,
    }

@router.post("/post-prompts")
async def update_post_prompts(data: dict):
    prompt = await PostPromptSettings.first()
    if not prompt:
        prompt = await PostPromptSettings.create(
            post_prompt=data.get("post_prompt"),
            idea_prompt=data.get("idea_prompt"),
            image_prompt=data.get("image_prompt"),
            fal_ai_api_key=data.get("fal_ai_api_key"),
            openai_api_key=data.get("openai_api_key"),
        )
    else:
        prompt.post_prompt = data.get("post_prompt", prompt.post_prompt)
        prompt.idea_prompt = data.get("idea_prompt", prompt.idea_prompt)
        prompt.image_prompt = data.get("image_prompt", prompt.image_prompt)
        prompt.fal_ai_api_key = data.get("fal_ai_api_key", prompt.fal_ai_api_key)
        prompt.openai_api_key = data.get("openai_api_key", prompt.openai_api_key)
        await prompt.save()
    return {
        "post_prompt": prompt.post_prompt,
        "idea_prompt": prompt.idea_prompt,
        "image_prompt": prompt.image_prompt,
        "fal_ai_api_key": prompt.fal_ai_api_key,
        "openai_api_key": prompt.openai_api_key,
    }

