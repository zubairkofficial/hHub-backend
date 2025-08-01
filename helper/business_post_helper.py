import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from helper.fall_ai import fall_ai_image_generator
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
from pydantic import BaseModel, Field
from helper.post_setting_helper import get_settings
import base64
import json
import re
import uuid, os, requests


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, '..', 'images')


class PostContent(BaseModel):
    content: str = Field(description="Content of the post, max of 10 words")
    title: str = Field(description="Title of the Post, max of 4 words")
    description: str = Field(description="Description of the Post, max of 7 words")

def sanitize_filename(filename):
    # Replace forbidden characters with underscore
    return re.sub(r'[<>:"/\\|?*%&=]', '_', filename)

def encode_image(file_path):
    with open(file_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    return base64_image

class BusinessPostHelper:
    def __init__(self):
        # Initialize without API key, will be set in async methods
        self.llm = None
        self.client = None

    async def _get_api_key(self):
        settings = await get_settings()
        return settings["openai_api_key"]

    async def _init_clients(self):
        if self.llm is None:
            api_key = await self._get_api_key()
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=1.2,
                api_key=api_key
            )
            self.client = OpenAI(api_key=api_key)
            print(f"key: {api_key}")

    async def generate_post(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        await self._init_clients()
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
        await self._init_clients()
        prompts = await self.get_dynamic_prompts()
        prompt = prompts["idea_prompt"]
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("user", user_text)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content

    async def generate_post_bundle(self, business_idea: str, keywords: str = None) -> dict:
        # Use the dynamic idea_prompt from settings/admin
        api_key = await self._get_api_key()
        llm_model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=1.2,
            api_key=api_key
        ).with_structured_output(PostContent)
        
        prompts = await self.get_dynamic_prompts()
        idea_prompt = prompts["post_prompt"]
        prompt = idea_prompt.format(business_idea=business_idea, keywords=keywords)
        response = await llm_model.ainvoke(prompt)
        response = response.model_dump()

        return response
        def extract_json_from_llm_response(response_text):
            # This will match ```json ... ``` or ``` ... ```
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if match:
                response_text = match.group(1)
            # Try to extract the first JSON object if extra text is present
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                return json_match.group(0)
            return response_text
        try:
            cleaned = extract_json_from_llm_response(response.content.strip())
            print(f"[DEBUG] Cleaned LLM response before json.loads: {cleaned}")
            if not cleaned or not cleaned.strip():
                print("[DEBUG] Cleaned response is empty or whitespace.")
                return {
                    "title": "",
                    "description": "",
                    "content": response.content.strip()
                }
            cleaned = cleaned.strip()
            if not (cleaned.startswith('{') and cleaned.endswith('}')):
                print("[DEBUG] Cleaned response does not look like a JSON object.")
                return {
                    "title": "",
                    "description": "",
                    "content": cleaned
                }
            result = json.loads(cleaned)
            return {
                "title": result.get("title", ""),
                "description": result.get("description", ""),
                "content": result.get("content", "")
            }
        except Exception as e:
            import traceback
            print(f"LLM response parsing error: {e}, raw response: {response.content.strip()}")
            print(f"[DEBUG] Cleaned response that failed: {cleaned}")
            traceback.print_exc()
            return {
                "title": "",
                "description": "",
                "content": cleaned
            }

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

    async def generate_image(self, brand_guidelines: str, post_data: dict, references=None, mode="generate", prompt_override=None,style:str=None,negative_prompt:str= "") -> str:
        # Only use prompt_override; do not use dynamic prompt templates
        await self._init_clients() 
        if prompt_override:
            prompt = prompt_override
        else:
            # If no prompt_override is provided, do not generate an image
            raise ValueError("A prompt_override must be provided for image generation.")
        print(f"test prompt> {prompt}, text style:{style}")
        # response = await fall_ai_image_generator(prompt,style,negative_prompt)
        # image_url = response
        # image_id = f"{uuid.uuid4()}.png"
        # temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
        # os.makedirs(temp_dir, exist_ok=True)
        # temp_path = os.path.join(temp_dir, image_id)
        # img_data = requests.get(image_url).content
        # with open(temp_path, "wb") as handler:
        #     handler.write(img_data)
        # return image_id  # Save this as the image_id in your DB/draft
        print(f"\n\n here are \n\n\n")
        response = self.client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            # size="1024x1024",
            # quality="standard",
            # n=1
        )
        # Extract the image URL from the response
        print(f"Image Response = {response}")
        # return response
        if hasattr(response, "data") and response.data:
            # Check if we have base64 data (newer API format)
            if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
                import base64
                image_id = f"{uuid.uuid4()}.png"
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, image_id)
                
                # Decode base64 data and save
                img_data = base64.b64decode(response.data[0].b64_json)
                with open(temp_path, "wb") as handler:
                    handler.write(img_data)
                return image_id
            # Fallback to URL format (older API format)
            elif hasattr(response.data[0], "url") and response.data[0].url:
                image_url = response.data[0].url
                image_id = f"{uuid.uuid4()}.png"
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp_images')
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, image_id)
                img_data = requests.get(image_url).content
                with open(temp_path, "wb") as handler:
                    handler.write(img_data)
                return image_id
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