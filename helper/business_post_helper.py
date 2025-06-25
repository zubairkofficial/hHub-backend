import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

load_dotenv()

class BusinessPostHelper:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.default_prompt = (
            "You are a creative social media manager. Given a business idea and brand guidelines, create a catchy, engaging social media post (2 to 4 lines) that promotes the business idea. For now, use only the business idea to write the post. The brand guidelines are provided for future use (such as image generation) and should not influence the text of the post at this stage."
        )

    async def generate_post(self, business_idea: str, brand_guidelines: str) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.default_prompt),
            ("user", f"Business Idea: {business_idea}\nGuidelines: {brand_guidelines}")
        ])
        formatted_prompt = prompt.format_messages()
        response = await self.llm.ainvoke(formatted_prompt)
        return response.content.strip() 