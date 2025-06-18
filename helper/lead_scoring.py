from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Optional
import os
from dotenv import load_dotenv
from models.system_prompt import SystemPrompts

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
        
        self.default_analytics_prompt = """You are an expert call analyst. Given the following call transcriptions, previous analysis (if any), and client context, write a comprehensive analysis summary that incorporates both historical and new information.\n\nContext:\n- Client Type: {client_type}\n- Service:{service}\n- Location: {state}, {city}\n- First Call: {first_call}\n- Rota Plan: {rota_plan}\n\nPrevious Analysis (if any):\n{previous_analysis}\n\nNew Call Transcriptions:\n\n\nWrite a single, comprehensive analysis summary that incorporates all the provided data, including both historical context from previous analysis and new information from recent calls. Explain how each factor influences the lead's potential and highlight any changes or developments in the client's situation."""

        self.default_score_prompt = """You are an expert lead scoring analyst. Given the following analysis summary, provide scores for the following aspects (0-100):\n1. Customer Intent\n2. Urgency\n3. Overall\nAlso, briefly justify each score.\n\n{format_instructions}"""

    async def get_prompts(self):
        try:
            prompts = await SystemPrompts.filter().first()
            
            if prompts:
                analytics_prompt = prompts.analytics_prompt if prompts.analytics_prompt else self.default_analytics_prompt
                score_prompt = prompts.summery_score if prompts.summery_score else self.default_score_prompt
                
                return {
                    'analytics_prompt': analytics_prompt,
                    'score_prompt': score_prompt
                }
            else:
                return {
                    'analytics_prompt': self.default_analytics_prompt,
                    'score_prompt': self.default_score_prompt
                }
                
        except Exception as e:
            print(f"Error fetching prompts from database: {e}")
            return {
                'analytics_prompt': self.default_analytics_prompt,
                'score_prompt': self.default_score_prompt
            }

    async def generate_summary(self, transcription: str, client_type: Optional[str] = None, 
                             service: Optional[str] = None, state: Optional[str] = None, 
                             city: Optional[str] = None, first_call: Optional[bool] = None, 
                             rota_plan: Optional[str] = None, previous_analysis: Optional[str] = None) -> dict:
  
        prompts = await self.get_prompts()
        print(prompts['analytics_prompt'])
        summary_prompt = ChatPromptTemplate.from_messages([ 
            ("system", prompts['analytics_prompt']),
        ])
        
        formatted_prompt = summary_prompt.format_messages(
            transcription=transcription,
            previous_analysis=previous_analysis or "No previous analysis available",
            client_type=client_type or "Not specified",
            service=service or "Not specified",
            state=state or "Not specified",
            city=city or "Not specified",
            first_call=first_call or "Not specified",
            rota_plan=rota_plan or "Not specified"
        )
        
        response = await self.llm.ainvoke(formatted_prompt)
        return {"summary": response.content.strip()}

    async def score_summary(self, analysis_summary: str) -> LeadAnalysis:
        prompts = await self.get_prompts()
        print(prompts['score_prompt'])
      
        score_prompt = ChatPromptTemplate.from_messages([ 
            ("system", prompts['score_prompt']),
            ("user", "Analysis Summary:\n{analysis_summary}")
        ])
        
        formatted_prompt = score_prompt.format_messages(
            analysis_summary=analysis_summary,
            format_instructions=self.parser.get_format_instructions()
        )
        
        response = await self.llm.ainvoke(formatted_prompt)
        analysis = self.parser.parse(response.content)
        return analysis

    async def analyze_lead(self, transcription: str, client_type: Optional[str] = None, 
                          service: Optional[str] = None, state: Optional[str] = None, 
                          city: Optional[str] = None, first_call: Optional[bool] = None, 
                          rota_plan: Optional[str] = None, previous_analysis: Optional[str] = None) -> dict:
       
        try:
            # Generate the analysis summary first
            summary_result = await self.generate_summary(
                transcription=transcription,
                client_type=client_type,
                service=service,
                state=state,
                city=city,
                first_call=first_call,
                rota_plan=rota_plan,
                previous_analysis=previous_analysis
            )
            
            # Score the generated analysis summary
            scoring_result = await self.score_summary(summary_result["summary"])

            # Correctly accessing the attributes of the LeadAnalysis object
            return {
                "summary": summary_result["summary"],
                "intent_score": scoring_result.intent_score,  # Correct attribute access
                "urgency_score": scoring_result.urgency_score,  # Correct attribute access
                "overall_score": scoring_result.overall_score,  # Correct attribute access
                "analysis_summary": scoring_result.analysis_summary  # Correct attribute access
            }
            
        except Exception as e:
            print(f"Error in lead analysis: {e}")
            return {
                "error": str(e),
                "summary": "Error occurred during analysis",
                "intent_score": 0,
                "urgency_score": 0,
                "overall_score": 0,
                "analysis_summary": "Analysis could not be completed due to an error"
            }
