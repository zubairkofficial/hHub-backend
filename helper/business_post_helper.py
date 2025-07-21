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
import base64
import uuid, os, requests


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, '..', 'images')

def sanitize_filename(filename):
    # Replace forbidden characters with underscore
    return re.sub(r'[<>:"/\\|?*%&=]', '_', filename)

def encode_image(file_path):
    with open(file_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    return base64_image

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

    async def generate_image(self, brand_guidelines: str, post_text: str, references=None, mode="generate") -> str:
        prompts = await self.get_dynamic_prompts()
        image_prompt = prompts["image_prompt"]
        # Use the image_prompt as a dynamic template, filling in {post_text} and {brand_guidelines}
        prompt = image_prompt.format(post_text=post_text, brand_guidelines=brand_guidelines)
        response = self.client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )
        # Extract the image URL from the response
        if hasattr(response, "data") and response.data and hasattr(response.data[0], "url"):
            image_url = response.data[0].url
            # Download and save to temp_images with a unique image_id
            image_id = f"{uuid.uuid4()}.png"
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, image_id)
            img_data = requests.get(image_url).content
            with open(temp_path, "wb") as handler:
                handler.write(img_data)
            return image_id  # Save this as the image_id in your DB/draft
        else:
            return None

    def move_image_to_permanent(self, image_id):
        import os
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
        os.makedirs(images_dir, exist_ok=True)
        src = os.path.join(temp_dir, image_id)
        dst = os.path.join(images_dir, image_id)
        if os.path.exists(src):
            os.rename(src, dst)
            return True
        return False

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