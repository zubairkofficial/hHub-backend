# agents/tools/appointment_tools.py - MODIFIED VERSION

import os
import json
import httpx
from typing import Optional
from langchain_core.tools import tool

API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_TOKEN", "")  # Add this to your .env file

def _dump(o):
    """Return JSON string with proper encoding."""
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
    Supports GET, POST, PATCH, DELETE. Follows redirects and handles auth.
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

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except Exception:
                    return {"ok": True, "data": response.text}
            else:
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
    Retrieve available appointment slots for a clinic on a given date.

    Args:
        client_id (int): ID of the client.
        clinic_id (int): ID of the clinic.
        date (str, optional): Date in YYYY-MM-DD format. Defaults to None.

    Returns:
        str: JSON string of available slots.
    """
    params = {"client_id": client_id, "clinic_id": clinic_id}
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
) -> str:
    """
    Create a new appointment for a patient in a clinic.

    Args:
        client_id (int): Client ID.
        clinic_id (int): Clinic ID.
        date (str): Appointment date YYYY-MM-DD.
        from_time (str): Start time HH:MM.
        to_time (str): End time HH:MM.
        first_name (str): Patient's first name.
        last_name (str, optional): Patient's last name.
        email (str): Patient email.
        contact_number (str): Patient phone number.
        gender (str): Patient gender.
        booking_for (str, optional): Booking for someone else.
        dob (str, optional): Date of birth.
        description (str, optional): Additional notes.

    Returns:
        str: JSON string of created appointment details.
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
    payload = {k: v for k, v in payload.items() if v not in (None, "")}
    data = await _http_request("POST", f"{API_URL}/api/appointments", json_data=payload)
    return _dump(data)


@tool("appointment_update")
async def appointment_update(lead_id: int, **fields) -> str:
    """
    Update an existing appointment by lead_id.

    Args:
        lead_id (int): Appointment ID.
        **fields: Any fields to update (clinic_id, date, times, email, etc.).

    Returns:
        str: JSON string of updated appointment details.
    """
    payload = {k: v for k, v in fields.items() if v is not None}
    data = await _http_request("PATCH", f"{API_URL}/api/appointments/{lead_id}", json_data=payload)
    return _dump(data)


@tool("appointment_cancel")
async def appointment_cancel(lead_id: int) -> str:
    """
    Cancel an appointment (status will be set to 'cancel').

    Args:
        lead_id (int): Appointment ID to cancel.

    Returns:
        str: JSON string of cancellation result.
    """
    data = await _http_request("DELETE", f"{API_URL}/api/appointments/{lead_id}")
    return _dump(data)


@tool("appointment_get")
async def appointment_get(lead_id: int, client_id: int = None) -> str:
    """
    Retrieve appointment details by lead ID.

    Args:
        lead_id (int): Appointment ID.
        client_id (int, optional): Client ID for verification.

    Returns:
        str: JSON string of appointment details.
    """
    params = {}
    if client_id:
        params["client_id"] = client_id
    data = await _http_request("GET", f"{API_URL}/api/appointments/{lead_id}", params=params)
    return _dump(data)
