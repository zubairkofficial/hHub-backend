import dotenv
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import os
import httpx
from helper.business_post_helper import encode_image
dotenv.load_dotenv()

client = OpenAI()


def create_file(file_path):
  with open(file_path, "rb") as file_content:
    result = client.files.create(
        file=file_content,
        purpose="vision",
    )
    return result.id
async def extract_data_from_img(path) -> str:
    try:
        file_id = create_file(path)
        print(f"File ID = {file_id}")
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Extract the primary, secondary, and other dominant colors from this image. Provide a list of the most prominent colors along with their corresponding color codes (e.g., HEX, RGB). NOTE: JUST RETURN COLORS AND NO ADDITIONAL TEXT"},
                    {
                        "type": "input_image",
                        "file_id": file_id,
                    },
                ],
            }],
        )
        print(f"Respones = {response.output_text}")
        return response.output_text

    except Exception as e:
        print(f"LLM summarization error: {e}")
        return "No data"  # fallback to raw text