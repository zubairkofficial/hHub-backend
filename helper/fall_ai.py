import uuid
import os
import requests
import fal_client

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(log["message"])

def fall_ai_image_generator(prompt,style):
    result = fal_client.subscribe(
        # "fal-ai/flux/dev",
        "fal-ai/recraft/v3/text-to-image",
        arguments={
            "prompt": prompt,
            "style": style
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    print(f"results: {result}")
    return result['images'][0]['url']

