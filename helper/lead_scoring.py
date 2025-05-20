from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class LeadAnalysis(BaseModel):
    intent_score: float = Field(description="Score for customer intent (0-100)")
    urgency_score: float = Field(description="Score for urgency level (0-100)")
    overall_score: float = Field(description="Combined score (0-100)")
    analysis_summary: str = Field(description="Comprehensive analysis incorporating all provided data")

class LeadScoringService:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.parser = PydanticOutputParser(pydantic_object=LeadAnalysis)
        self.summary_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert call analyst. Given the following call transcriptions and client context, write a comprehensive analysis summary.\n\nContext:\n- Client Type: {client_type}\n- Service: {service}\n- Location: {state}, {city}\n- First Call: {first_call}\n- Rota Plan: {rota_plan}\n\nCall Transcriptions:\n{transcription}\n\nWrite a single, comprehensive analysis summary that incorporates all the provided data and explains how each factor influences the lead's potential."""),
        ])
        self.score_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert lead scoring analyst. Given the following analysis summary, provide scores for the following aspects (0-100):\n1. Customer Intent\n2. Urgency\n3. Overall\nAlso, briefly justify each score.\n\n{format_instructions}"""),
            ("user", "Analysis Summary:\n{analysis_summary}")
        ])

    async def generate_summary(self, transcription: str, client_type: Optional[str] = None, service: Optional[str] = None, state: Optional[str] = None, city: Optional[str] = None, first_call: Optional[bool] = None, rota_plan: Optional[str] = None) -> dict:
        formatted_prompt = self.summary_prompt.format_messages(
            transcription=transcription,
            client_type=client_type or "Not specified",
            service=service or "Not specified",
            state=state or "Not specified",
            city=city or "Not specified",
            first_call="Yes" if first_call else "No",
            rota_plan=rota_plan or "Not specified"
        )
        response = await self.llm.ainvoke(formatted_prompt)
        return {"summary": response.content.strip()}

    async def score_summary(self, analysis_summary: str) -> LeadAnalysis:
        formatted_prompt = self.score_prompt.format_messages(
            analysis_summary=analysis_summary,
            format_instructions=self.parser.get_format_instructions()
        )
        response = await self.llm.ainvoke(formatted_prompt)
        analysis = self.parser.parse(response.content)
        return analysis