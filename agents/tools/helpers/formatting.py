# agents/helpers/formatting.py
from typing import Dict, Any

def fmt_lead_details(row: Dict[str, Any]) -> str:
    full_name = (" ".join([
        str(row.get("first_name") or "").strip(),
        str(row.get("last_name")  or "").strip()
    ]).strip()) or "(no name)"
    score = row.get("potential_score")
    score = score if score is not None else "—"
    return (
        f"- Name: {full_name}\n"
        f"- Email: {row.get('email') or '—'}\n"
        f"- Phone: {row.get('contact_number') or '—'}\n"
        f"- Status: {row.get('status') or '—'}\n"
        f"- Source: {row.get('lead_source') or '—'}\n"
        f"- Potential Score: {score}\n"
        f"- Description: {row.get('description') or '—'}\n"
        f"- Created: {row.get('created_at')}\n"
        f"- Updated: {row.get('updated_at')}"
    )

def fmt_clinic_details(c: Dict[str, Any]) -> str:
    return (
        f"- Name: {c.get('name') or '—'}\n"
        f"- Address: {c.get('address') or '—'} {c.get('address2') or ''}\n"
        f"- City/State/Country IDs: {c.get('city_id')} / {c.get('state_id')} / {c.get('country_id')}\n"
        f"- Zip: {c.get('zip_code') or '—'}\n"
        f"- Active: {c.get('is_active')}\n"
        f"- Review URL: {c.get('review_url') or '—'}\n"
        f"- Google Review URL: {c.get('google_review_url') or '—'}\n"
        f"- TW SIDs: appt={c.get('tw_content_sid_appt') or '—'}, review={c.get('tw_content_sid_review') or '—'}, nurture={c.get('tw_content_sid_nurture') or '—'}\n"
        f"- Created: {c.get('created_at')}\n"
        f"- Updated: {c.get('updated_at')}"
    )
