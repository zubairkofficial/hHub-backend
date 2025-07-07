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
            "Create a prompt for DALL-E to generate an engaging social media image that aligns with the following business idea and brand guidelines. "
            "The prompt should be detailed, creative, and incorporate the brand's visual identity, especially the brand's color palette and design elements. "
            "Focus on creating an image that would work well on social media platforms and visually reflects the brand's color and design.\n\n"
            "Business Idea: {business_idea}\n"
            "Brand Guidelines (including color and design): {brand_guidelines}\n\n"
            "Generate a DALL-E prompt that is specific, descriptive, and would result in a visually appealing image that matches the brand's color and design."
        )

    async def generate_post(self, business_idea: str, brand_guidelines: str, extracted_file_text: str = None) -> str:
        prompt_parts = []
        if business_idea:
            prompt_parts.append(f"Business Idea: {business_idea}")
        if brand_guidelines:
            prompt_parts.append(f"Brand Guidelines: {brand_guidelines}")
        if extracted_file_text:
            prompt_parts.append(f"Additional Info: {extracted_file_text}")
        full_prompt = "\n".join(prompt_parts)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.default_prompt),
            ("user", full_prompt)
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip()

    async def generate_image_prompt(self, business_idea: str, brand_guidelines: str) -> str:
        # Format the template with the actual values to avoid KeyError
        system_prompt = self.image_prompt_template.format(
            business_idea=business_idea,
            brand_guidelines=brand_guidelines
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", f"Business Idea: {business_idea}\nGuidelines: {brand_guidelines}")
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
        if extracted_file_text:
            prompt_parts.append(f"Additional Info: {extracted_file_text}")
        full_prompt = "\n".join(prompt_parts)
        image_prompt = await self.generate_image_prompt(full_prompt, "")
        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            if hasattr(response, "data") and response.data and hasattr(response.data[0], "url"):
                image_url = response.data[0].url
                image_id = self.save_image_from_url(image_url)
                print(f"[Image Generation] Image saved as images/{image_id}")
                return image_id
            else:
                print(f"[Image Generation] No image URL returned. Response: {response}")
                return None
        except Exception as e:
            print(f"Error generating image: {str(e)}")
            return None 