# agents/registry.py
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel

AgentName = Literal[
    "LeadAgent",
    "ReminderAgent",
    "SQLReader",
    "SQLWriter",
    "Knowledge",
    "SmallTalk",
    "ClinicAgent",
    "ServiceAgent",  # ✅ add this line
    "AppointmentAgent",  # ✅ add this line
]

class AgentSpec(BaseModel):
    name: AgentName
    system_prompt: str
    tools: List  # LangChain tool callables
    allow_tool_calls: bool = True

REGISTRY: Dict[AgentName, AgentSpec] = {}

def register(spec: AgentSpec):
    REGISTRY[spec.name] = spec

def get_agent(name: AgentName) -> AgentSpec:
    return REGISTRY[name]
