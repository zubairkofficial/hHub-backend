from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

class LeadAnalysis(BaseModel):
    intent_score: float = Field(description="Score for customer intent (0-100)")
    tone_score: float = Field(description="Score for conversation tone (0-100)")
    urgency_score: float = Field(description="Score for urgency level (0-100)")
    overall_score: float = Field(description="Combined score (0-100)")
    analysis_summary: str = Field(description="Detailed analysis of the conversation")

class LeadScoringService:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.parser = PydanticOutputParser(pydantic_object=LeadAnalysis)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert lead scoring analyst. Analyze the following call transcription 
            and provide scores for different aspects of the conversation. Consider:
            1. Customer Intent: How likely is the customer to convert?
            2. Conversation Tone: How positive and engaging was the conversation?
            3. Urgency: How urgent is the customer's need?
            
            Provide scores from 0-100 for each aspect and an overall score.
            Also provide a detailed analysis summary.
            
            {format_instructions}"""),
            ("user", "Call Transcription:\n{transcription}")
        ])

    async def analyze_transcription(self, transcription: str) -> LeadAnalysis:
        # Format the prompt with the transcription
        formatted_prompt = self.prompt.format_messages(
            transcription=transcription,
            format_instructions=self.parser.get_format_instructions()
        )
        
        # Get the response from the model
        response = await self.llm.ainvoke(formatted_prompt)
        
        # Parse the response into our Pydantic model
        analysis = self.parser.parse(response.content)
        return analysis

