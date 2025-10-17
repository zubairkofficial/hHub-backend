# agents/router.py
from typing import TypedDict
import json
import re

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate




class Route(TypedDict):
    agent: str
    rationale: str
    confidence: float

# Tool-agnostic router model
_router_model = init_chat_model("gpt-4o-mini", model_provider="openai")

_examples = [
    # Lead by ID
    {"input": "show lead id 16", "output": {"agent": "SQLReader", "rationale": "Lead fetch by numeric id", "confidence": 0.95}},
    # Lead by email
    {"input": "find lead by email myla@example.com", "output": {"agent": "SQLReader", "rationale": "Lead fetch by email", "confidence": 0.95}},
    # Lead by phone
    {"input": "lookup lead phone +1 206 555 1234", "output": {"agent": "SQLReader", "rationale": "Lead fetch by phone", "confidence": 0.95}},
    # Update (goes to LeadAgent)
    {"input": "mark lead id 19 as won", "output": {"agent": "LeadAgent", "rationale": "CRM update", "confidence": 0.9}},
    # SmallTalk
    {"input": "hi", "output": {"agent": "SmallTalk", "rationale": "Small talk", "confidence": 0.8}},
]

_examples_prompt = FewShotChatMessagePromptTemplate(
    examples=_examples,
    example_prompt=ChatPromptTemplate.from_messages([
        ("human", "{input}"),
        # escape braces in JSON example
        ("ai", "{{\"agent\": \"{agent}\", \"rationale\": \"{rationale}\", \"confidence\": {confidence}}}"),
    ]),
    input_variables=["input"],
)

# IMPORTANT: Escape braces in the JSON example with double braces `{{ ... }}`
_router_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a skill router. Pick the best agent for the user request.\n"
     "Valid agents: LeadAgent, ReminderAgent, SQLReader, SmallTalk.\n"
     "Return STRICT JSON only, no extra text: "
     "{{\"agent\": \"<one of the valid agents>\", \"rationale\": \"<short why>\", \"confidence\": 0.0-1.0}}"
    ),
    _examples_prompt,
    ("user", "{msg}"),
])

_json_pattern = re.compile(r"\{.*\}", re.DOTALL)

async def pick_agent(user_msg: str) -> Route:
    # Ask for a JSON-only response
    try:
        # ⬇️ supply a dummy "input" to satisfy the few-shot template signature
        txt = await (_router_prompt | _router_model).ainvoke({"msg": user_msg, "input": ""})
    except Exception as e:
        # graceful fallback so the app never crashes on routing glitches
        return {"agent": "SmallTalk", "rationale": f"router_error:{e.__class__.__name__}", "confidence": 0.3}

    # Extract content robustly whether ai_msg/content is used
    raw = getattr(txt, "content", None) or str(txt)

    # Try direct JSON first
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to pull the first JSON object from the text (in case the model adds wrappers)
        m = _json_pattern.search(raw)
        if not m:
            return {"agent": "SmallTalk", "rationale": "fallback: no JSON", "confidence": 0.3}
        try:
            data = json.loads(m.group(0))
        except Exception:
            return {"agent": "SmallTalk", "rationale": "fallback: bad JSON", "confidence": 0.3}

    agent = str(data.get("agent", "SmallTalk"))
    rationale = str(data.get("rationale", ""))[:500]
    try:
        confidence = float(data.get("confidence", 0.5))
    except Exception:
        confidence = 0.5

    # Final guardrails on agent label
    if agent not in {"LeadAgent", "ReminderAgent", "SQLReader", "SmallTalk"}:
        agent = "SmallTalk"

    return {"agent": agent, "rationale": rationale, "confidence": confidence}
