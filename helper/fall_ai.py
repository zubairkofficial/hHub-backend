import uuid
import os
import requests
import fal_client
from helper.post_setting_helper import get_settings

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(log["message"])

async def fall_ai_image_generator(prompt, style, negative_prompt=""):
    # Get FAL API key from settings or environment
    settings = await get_settings()
    fal_api_key = settings["fal_ai_api_key"]
    
    if not fal_api_key:
        raise ValueError("FAL API key not found in settings or environment variables")
    
    # Set the API key as environment variable for fal_client
    import os
    os.environ["FAL_KEY"] = fal_api_key
    
    result = fal_client.subscribe(
        # "fal-ai/flux/dev",
        # "fal-ai/recraft/v3/text-to-image",
        "fal-ai/imagen4/preview",
        arguments={
            "prompt": prompt,
            # "style": style
            "negative_prompt": negative_prompt,
            "seed": 123456,
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    print(f"results: {result}")
    return result['images'][0]['url']

