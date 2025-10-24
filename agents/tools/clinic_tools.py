# agents/tools/clinic_tools.py
import json
from pydantic import BaseModel
from langchain_core.tools import tool
import httpx
import os
API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")

class ClinicGetArgs(BaseModel):
    client_id: int
    clinic_id: int

@tool("clinic_get", args_schema=ClinicGetArgs)
async def clinic_get(client_id: int, clinic_id: int) -> str:
    """
    Fetch a clinic by client_id and clinic_id. Returns clinic details in JSON format.
    """
    url = f"{API_URL}/api/clinics/{clinic_id}"
    headers = {"Accept": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params={"client_id": client_id})
            if response.status_code == 200:
                return json.dumps(response.json(), ensure_ascii=False)
            else:
                return json.dumps({"ok": False, "error": f"Failed to fetch clinic: {response.status_code}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Error fetching clinic data: {str(e)}"}, ensure_ascii=False)

