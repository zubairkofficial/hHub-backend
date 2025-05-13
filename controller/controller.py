from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Union

from helper.lead_scoring import LeadScoringService

router = APIRouter()



class LeadScoreResponse(BaseModel):
    lead_id: int
    intent_score: float
    tone_score: float
    urgency_score: float
    overall_score: float
    analysis_summary: str
    priority: int
    priority_level: str  # New field for priority level description

class AnalysisResponse(BaseModel):
    leads: List[LeadScoreResponse]
    total_leads: int

def calculate_priority_level(overall_score: float) -> str:
    if overall_score >= 90:
        return "Critical"
    elif overall_score >= 80:
        return "High"
    elif overall_score >= 70:
        return "Medium"
    elif overall_score >= 60:
        return "Low"
    else:
        return "Very Low"



@router.get("/analyze-leads")
async def analyze_leads(
    leads: str  # JSON string of leads array
):
    try:
        import json
        leads_data = json.loads(leads)
        
        if not isinstance(leads_data, list):
            leads_data = [leads_data]
        
        scoring_service = LeadScoringService()
        results = []
        
        # Analyze all transcriptions
        for lead in leads_data:
            analysis = await scoring_service.analyze_transcription(lead['transcription'])
            results.append({
                "lead_id": lead['lead_id'],
                "intent_score": analysis.intent_score,
                "tone_score": analysis.tone_score,
                "urgency_score": analysis.urgency_score,
                "overall_score": analysis.overall_score,
                "analysis_summary": analysis.analysis_summary
            })
        
        # Sort by overall score and assign priorities
        sorted_results = sorted(results, key=lambda x: x['overall_score'], reverse=True)
        
        # Assign priorities and priority levels
        for i, result in enumerate(sorted_results, 1):
            result['priority'] = i
            result['priority_level'] = calculate_priority_level(result['overall_score'])
        return {
            "leads": sorted_results,
            "total_leads": len(sorted_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
