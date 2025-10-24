# agents/tools/appointment_tools.py - FIXED VERSION

import os
import json
import httpx
from typing import Optional
from langchain_core.tools import tool

API_URL = os.getenv("API_URL", "http://127.0.0.1:8080")
API_TOKEN = os.getenv("API_TOKEN", "")  # Add this to your .env file

def _dump(o):
    return json.dumps(o, ensure_ascii=False, default=str)

def _get_headers():
    """Return headers with authentication if token is available."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers

async def _http_request(method: str, url: str, params=None, json_data=None):
    """
    Generic HTTP request handler with proper error handling.
    Follows redirects and handles authentication.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            if method == "GET":
                response = await client.get(url, params=params, headers=_get_headers())
            elif method == "POST":
                response = await client.post(url, json=json_data, headers=_get_headers())
            elif method == "PATCH":
                response = await client.patch(url, json=json_data, headers=_get_headers())
            elif method == "DELETE":
                response = await client.delete(url, headers=_get_headers())
            else:
                return {"ok": False, "error": f"Unsupported method: {method}"}

            # Check for successful response
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except Exception:
                    return {"ok": True, "data": response.text}
            else:
                # Return error with status code
                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text[:1000]
                
                return {
                    "ok": False,
                    "status_code": response.status_code,
                    "error": error_data
                }
        except httpx.ConnectError as e:
            return {"ok": False, "error": f"Connection failed: {str(e)}"}
        except httpx.TimeoutException:
            return {"ok": False, "error": "Request timed out"}
        except Exception as e:
            return {"ok": False, "error": f"Request failed: {type(e).__name__}: {str(e)}"}


@tool("appointment_slots")
async def appointment_slots(client_id: int, clinic_id: int, date: str = None) -> str:
    """
    Get available slots for a clinic on a date.
    Args: client_id (int), clinic_id (int), date (YYYY-MM-DD optional)
    """
    params = {
        "client_id": client_id,
        "clinic_id": clinic_id,
    }
    if date:
        params["date"] = date
    
    data = await _http_request("GET", f"{API_URL}/api/appointments/slots", params=params)
    return _dump(data)


@tool("appointment_create")
async def appointment_create(
    client_id: int,
    clinic_id: int,
    date: str,
    from_time: str,
    to_time: str,
    first_name: str,
    email: str,
    contact_number: str,
    gender: str,
    last_name: str = "",
    booking_for: str = None,
    dob: str = None,
    description: str = None,
    human_readable: bool = True,  # ✅ New flag
) -> str:
    """
    Create a new appointment.
    If human_readable=True, returns a nicely formatted text instead of raw JSON.
    """
    payload = {
        "client_id": client_id,
        "clinic_id": clinic_id,
        "date": date,
        "from_time": from_time,
        "to_time": to_time,
        "first_name": first_name,
        "last_name": last_name or None,
        "email": email,
        "contact_number": contact_number or None,
        "booking_for": booking_for,
        "dob": dob,
        "gender": gender,
        "description": description,
    }

    # Remove empty/None
    payload = {k: v for k, v in payload.items() if v not in (None, "")}

    data = await _http_request("POST", f"{API_URL}/api/appointments", json_data=payload)

    if not human_readable or not data.get("ok"):
        return _dump(data)  # fallback: raw JSON

    # ✅ Build human-readable response
    lead = data.get("lead", {})
    clinic_name = "Happy Teeth Clinic"  # or fetch dynamically if API returns
    response_text = f"""
✅ Appointment Booked Successfully!

📍 Clinic: {clinic_name}
🗓 Date: {lead.get('date', date)}
⏰ Time: {lead.get('from_time', from_time)[:5]} – {lead.get('to_time', to_time)[:5]}

👤 Patient Details:
   Name: {lead.get('first_name', first_name)} {lead.get('last_name', last_name)}
   Email: {lead.get('email', email)}
   Phone: {lead.get('contact_number', contact_number)}
   DOB: {lead.get('dob', dob)}
   Gender: {lead.get('gender', gender)}

Status: {lead.get('status', 'new').capitalize()}
"""
    return response_text.strip()


@tool("appointment_update")
async def appointment_update(lead_id: int, **fields) -> str:
    """
    Update an appointment (lead) by id. Fields may include clinic_id, date, from_time, to_time, etc.
    """
    # Remove None values
    payload = {k: v for k, v in fields.items() if v is not None}
    
    data = await _http_request("PATCH", f"{API_URL}/api/appointments/{lead_id}", json_data=payload)
    return _dump(data)


@tool("appointment_cancel")
async def appointment_cancel(lead_id: int) -> str:
    """
    Cancel an appointment (sets status=cancel).
    """
    data = await _http_request("DELETE", f"{API_URL}/api/appointments/{lead_id}")
    return _dump(data)


@tool("appointment_get")
async def appointment_get(lead_id: int, client_id: int = None) -> str:
    """
    Get appointment details by lead_id.
    """
    params = {}
    if client_id:
        params["client_id"] = client_id
    
    data = await _http_request("GET", f"{API_URL}/api/appointments/{lead_id}", params=params)
    return _dump(data)