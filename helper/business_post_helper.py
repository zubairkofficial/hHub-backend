import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from openai import OpenAI
import json
import requests
from urllib.parse import unquote, urlparse
import re
from fastapi.responses import FileResponse
from fastapi import HTTPException
import time
import traceback
from models.post_prompt_settings import PostPromptSettings


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, '..', 'images')

def sanitize_filename(filename):
    # Replace forbidden characters with underscore
    return re.sub(r'[<>:"/\\|?*%&=]', '_', filename)

class BusinessPostHelper:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=1.2,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print(f"key: {os.getenv('OPENAI_API_KEY')}")

    async def generate_post(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        prompts = await self.get_dynamic_prompts()
        prompt = prompts["post_prompt"]
        prompt_parts = []
        if business_idea:
            prompt_parts.append(f"Business Idea: {business_idea} \n")
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines} \n")
        post_data = "\n".join(prompt_parts)
        user_data = f"Data = {post_data}"
        # Add a unique instruction to the user prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("user", user_data)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip()

    async def generate_short_idea(self, user_text: str) -> str:
        prompts = await self.get_dynamic_prompts()
        prompt = prompts["idea_prompt"]
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("user", user_text)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content

    @staticmethod
    def save_image_from_url(image_url, filename=None):
        import requests
        # Extract filename and extension
        if not filename:
            filename = image_url.split("/")[-1].split("?")[0]
            decoded_filename = unquote(filename)
            parsed = urlparse(image_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext:
                ext = ".jpg"
            if not decoded_filename.lower().endswith((".jpg", ".jpeg", ".png")):
                decoded_filename += ext
            filename = sanitize_filename(decoded_filename)
        os.makedirs(IMAGE_DIR, exist_ok=True)
        image_path = os.path.join(IMAGE_DIR, filename)
        img_data = requests.get(image_url).content
        with open(image_path, "wb") as handler:
            handler.write(img_data)
        return filename

    @staticmethod
    def display_image_helper(image_id):
        image_id = unquote(image_id)
        image_path = os.path.join(IMAGE_DIR, image_id)
        if os.path.exists(image_path):
            return FileResponse(path=image_path, media_type='image/png')
        # Try with .jpg
        image_path_jpg = os.path.join(IMAGE_DIR, image_id + '.jpg')
        if os.path.exists(image_path_jpg):
            return FileResponse(path=image_path_jpg, media_type='image/jpeg')
        # Try with .png
        image_path_png = os.path.join(IMAGE_DIR, image_id + '.png')
        if os.path.exists(image_path_png):
            return FileResponse(path=image_path_png, media_type='image/png')
        raise HTTPException(status_code=404, detail="Image not found")

    async def generate_image(self, brand_guidelines: str, post_text: str) -> str:
        prompts = await self.get_dynamic_prompts()
        prompt = prompts["image_prompt"]
        prompt_parts = []
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines} \n")
        
        prompt_parts.append(f"Post Content: {post_text} \n")
        image_prompt = prompt
        max_retries = 3
        image_prompt += "".join(prompt_parts)
        for attempt in range(max_retries):
            try:
                response = self.client.images.generate(
                    model="dall-e-3",
                    prompt=image_prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                if hasattr(response, "data") and response.data and hasattr(response.data[0], "url"):
                    image_url = self.save_image_from_url(response.data[0].url)
                    print(f"[Image Generation] Image saved as images/{image_url}")
                    return image_url
                else:
                    print(f"[Image Generation] No image URL returned. Response: {response}")
                    return None
            except Exception as e:
                print(f"Error generating image (attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait before retrying
                else:
                    import traceback
                    traceback.print_exc()
                    return None 

    @staticmethod
    async def get_dynamic_prompts():
        prompt = await PostPromptSettings.first()
        if prompt:
            return {
                "post_prompt": prompt.post_prompt,
                "idea_prompt": prompt.idea_prompt,
                "image_prompt": prompt.image_prompt,
            }
        # Fallbacks if needed
        return {
            "post_prompt": "",
            "idea_prompt": "",
            "image_prompt": "",
        } 