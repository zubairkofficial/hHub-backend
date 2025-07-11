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
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print(f"key: {os.getenv('OPENAI_API_KEY')}")
        self.default_prompt = (
            "You are a creative social media manager. Given a business idea and brand guidelines, create a catchy, engaging social media post (2 to 4 lines) that promotes the business idea. For now, use only the business idea to write the post. The brand guidelines are provided for future use (such as image generation) and should not influence the text of the post at this stage."
        )
        self.image_prompt_template = (
            "Create a modern, minimal, and professional Instagram post image. "
            "The background should be clean, simple, and consist of subtle wavy lines or abstract shapes, following the brand's color palette. "
            "The design should not be too busy or distracting, keeping the focus on the text and visuals. "
            "Overlay a short, bold, catchy phrase (4-5 words) in the center of the image. The text should be the focal point: large, easy to read, and high contrast with the background. "
            "Ensure that if a person is included, they are clear, well-lit, and not obscured by the background, resembling the style of a high-quality Instagram post. "
            "The overall style should be minimal, polished, and visually appealing. "
            "Do NOT use more than 5 words in the text overlay, and make sure the background is not overly complex or busy. "
            "Business Idea: {business_idea}\n"
            "Brand Guidelines (including color and design): {brand_guidelines}\n"
            "Extracted File Text: {extracted_file_text}\n"
            "Generate a DALL-E prompt that will result in a clean, modern, branded image with a short, bold text overlay, similar to the provided examples."
)


    async def generate_post(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        prompt_parts = []
        if business_idea:
            prompt_parts.append(f"Business Idea: {business_idea}")
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines}")
        if not business_idea and not brand_guidelines and extracted_file_text:
            prompt_parts.append(f"Extracted File Text: {extracted_file_text}")
        elif extracted_file_text:
            prompt_parts.append(f"Extracted File Text: {extracted_file_text}")
        full_prompt = "\n".join(prompt_parts)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.default_prompt),
            ("user", full_prompt)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip()

    async def generate_image_prompt(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = "") -> str:
        # Format the template with the actual values to avoid KeyError
        system_prompt = self.image_prompt_template.format(
            business_idea=business_idea,
            brand_guidelines=brand_guidelines,
            extracted_file_text=extracted_file_text or ""
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", f"Business Idea: {business_idea}\nGuidelines: {brand_guidelines}\nExtracted File Text: {extracted_file_text or ''}")
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip()

    async def generate_short_idea(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        short_idea_prompt = (
            "You are a creative social media manager. Given a business idea, brand guidelines, and extracted file text, generate a catchy, engaging social media idea in 1 to 2 lines only. Do NOT include hashtags or tags. The idea should be concise, clear, and suitable as the main message for a post. Use all provided information to inspire the idea, but keep it short and punchy."
        )
        prompt_parts = []
        if business_idea:
            prompt_parts.append(f"Business Idea: {business_idea}")
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines}")
        if extracted_file_text:
            prompt_parts.append(f"Extracted File Text: {extracted_file_text}")
        full_prompt = "\n".join(prompt_parts)
        prompt = ChatPromptTemplate.from_messages([
            ("system", short_idea_prompt),
            ("user", full_prompt)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip()

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

    async def generate_image(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        prompt_parts = []
        if business_idea:
            prompt_parts.append(f"Business Idea: {business_idea}")
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines}")
        if not business_idea and not brand_guidelines and extracted_file_text:
            prompt_parts.append(f"Extracted File Text: {extracted_file_text}")
        elif extracted_file_text:
            prompt_parts.append(f"Extracted File Text: {extracted_file_text}")
        full_prompt = "\n".join(prompt_parts)
        image_prompt = await self.generate_image_prompt(business_idea, brand_guidelines, extracted_file_text or "")
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
            print(f"Error generating image: {str(e)}")
            return None 