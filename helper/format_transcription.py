# E:\Shoaib\Projects\hHub\hHub-backend\helper\format_transcription.py
from __future__ import annotations

import os
import re
import json
from typing import List, Dict, Optional

import aiohttp

__all__ = ["format_transcription", "format_transcription_ai"]

# ──────────────────────────────────────────────────────────────
# Heuristic fallback → now uses PATIENT (not Customer)
# ──────────────────────────────────────────────────────────────
def format_transcription(raw_text: str, output: str = "markdown") -> str:
    """
    Heuristic formatter (fallback). Separates Receptionist vs Patient, highlights
    phones/dates/times, and produces bullets. Prefer `format_transcription_ai`.
    """
    def bold(s: str) -> str:
        return f"**{s}**" if output == "markdown" else f"<strong>{s}</strong>"

    def li(role: str, text: str) -> str:
        if output == "markdown":
            return f"- {bold(role + ':')} {text}"
        else:
            return f"<li>{bold(role + ':')} {text}</li>"

    def wrap_list(items: List[str]) -> str:
        if output == "markdown":
            return "\n".join(items)
        else:
            return "<ul>" + "".join(items) + "</ul>"

    txt = " ".join((raw_text or "").split())
    if not txt:
        return wrap_list([li("System", "No transcription text was provided.")])

    # Segment on common cues; keep delimiters to infer turns
    cue_regex = (
        r'(?i)('
        r'thanks for calling|how can i help( you)?|hi[, ]|hello[, ]|excuse me|'
        r'yeah[, ]|okay[, ]|thank you|usually|my name is|i am|i\'m|this is|calling from|'
        r'and your phone number is|do you have any sort of dental insurance\??|'
        r'this call is recorded'
        r')'
    )
    tokens = re.split(cue_regex, txt)

    chunks: List[str] = []
    buf = ""
    for t in tokens:
        if not t:
            continue
        if re.match(cue_regex, t.strip()):
            if buf.strip():
                chunks.append(buf.strip()); buf = ""
        buf += (" " + t)
    if buf.strip():
        chunks.append(buf.strip())

    # Cues
    receptionist_cues = re.compile(
        r"(?i)thanks for calling|how can i help|excuse me|usually|do you have any sort of dental insurance|this call is recorded|we are (?:on the phone|assisting another patient)"
    )
    patient_cues = re.compile(
        r"(?i)^hi\b|^hello\b|^yeah\b|^okay\b|^my name is|^i'?m\b|^i am\b|this is\b|calling from\b|can you|i would like|i was wondering|please call me back"
    )

    lines: List[str] = []
    current_role = None  # "Receptionist" | "Patient"

    for c in chunks:
        s = c.strip()

        if receptionist_cues.search(s):
            current_role = "Receptionist"
        elif patient_cues.search(s):
            current_role = "Patient"
        elif current_role is None:
            # Most calls begin with the clinic greeting
            current_role = "Receptionist"
        else:
            current_role = "Patient" if current_role == "Receptionist" else "Receptionist"

        # Highlight timestamps, dates, phones, a few keywords
        s = re.sub(r"\b(\d{1,2}:\d{2})\b", lambda m: bold(m.group(1)), s)
        s = re.sub(
            r"\b("
            r"\d{1,2}/\d{1,2}/\d{2,4}|"
            r"\d{1,2}-\d{1,2}-\d{2,4}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.? \d{1,2}, \d{4}"
            r")\b",
            lambda m: bold(m.group(1)), s,
        )
        s = re.sub(r"\b(\+?\d{1,2}[-\s]?)?(\(?\d{3}\)?)[-\s]?\d{3}[-\s]?\d{4}\b",
                   lambda m: bold(m.group(0)), s)
        s = re.sub(r"\b(appointment|estimate|patient[s]?|new patient|follow up|follow-up)\b",
                   lambda m: bold(m.group(1)), s, flags=re.I)

        lines.append(li(current_role, s))

    return wrap_list(lines)

# ──────────────────────────────────────────────────────────────
# GPT-powered formatter (Receptionist vs Patient)
# ──────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("TRANSCRIPT_FORMAT_MODEL", "gpt-4o-mini")

_SPEAKER_NORMALIZE = [
    (re.compile(r"(?i)\bcaller\b"), "Patient"),
    (re.compile(r"(?i)\bcustomer\b"), "Patient"),
    (re.compile(r"(?i)\bclient\b"), "Patient"),
    (re.compile(r"(?i)\bfront desk\b"), "Receptionist"),
    (re.compile(r"(?i)\breception\b"), "Receptionist"),
    (re.compile(r"(?i)\boffice staff\b"), "Receptionist"),
]

def _normalize_labels_md(md: str) -> str:
    """
    Normalize any 'Caller/Customer/Client' → 'Patient' and front-desk variants → 'Receptionist'
    in Markdown bullet lines that start with '**Label:**'.
    """
    lines = []
    for line in md.splitlines():
        m = re.match(r"^\s*-\s*\*\*(.+?):\*\*\s*(.*)$", line)
        if m:
            label, rest = m.group(1), m.group(2)
            norm = label
            for rx, rep in _SPEAKER_NORMALIZE:
                if rx.search(label):
                    norm = rep
            # If model already used Patient/Receptionist + name, keep name but ensure role word correct
            # Examples: "Helena (Receptionist)" or "Chennai (Caller)"
            m2 = re.match(r"^(.*?)\s*\((.*?)\)\s*$", norm)
            if m2:
                name, role = m2.group(1).strip(), m2.group(2).strip()
                for rx, rep in _SPEAKER_NORMALIZE:
                    if rx.search(role):
                        role = rep
                norm = f"{name} ({role})"
            lines.append(f"- **{norm}:** {rest}")
        else:
            lines.append(line)
    return "\n".join(lines)

async def format_transcription_ai(
    raw_text: str,
    *,
    output: str = "markdown",                      # "markdown" | "html"
    temperature: float = 0.2,
    timeout: int = 25,
) -> str:
    """
    Use GPT to format as bullets with strict 'Receptionist' and 'Patient' roles.
    Falls back to heuristic if anything fails or no API key is present.
    """
    if not raw_text or not raw_text.strip() or not OPENAI_API_KEY:
        return format_transcription(raw_text, output=output)

    system_msg = (
        "You format medical/dental clinic phone transcripts. "
        "Always structure as bullet points per utterance. "
        "Label speakers as either 'Receptionist' or 'Patient'. "
        "If a proper name is evident, include it like 'Helena (Receptionist)' or 'Chennai (Patient)'. "
        "Bold timestamps (e.g., 0:23), dates, phone numbers, and key terms such as appointment, estimate, patient, follow-up. "
        "Never invent details or names; only infer when clearly stated like 'my name is X' or 'this is X'. "
        "No header or explanation—return only the final list."
    )

    user_msg = f"""Transcription:
{raw_text}

Format rules:
- One bullet per utterance.
- Start each line with **Speaker:** where Speaker is either 'Receptionist' or 'Patient'.
- If a name is present, format as **Name (Receptionist):** or **Name (Patient):**
- Use {'**bold**' if output=='markdown' else '<strong>bold</strong>'} for timestamps, dates, phone numbers, and key terms (appointment, estimate, patient, follow-up).
- Output only {output.upper()} content.
"""

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, headers=headers, data=json.dumps(payload)) as resp:
                if resp.status != 200:
                    return format_transcription(raw_text, output=output)
                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Normalize any stray "Caller/Customer/Client" labels → Patient (Markdown only)
                if output == "markdown":
                    content = _normalize_labels_md(content)

                # If HTML requested but bullets are markdown, wrap in <ul>
                if output == "html" and content.startswith("- "):
                    items = []
                    for line in content.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("- "):
                            items.append(f"<li>{line[2:].strip()}</li>")
                        else:
                            items.append(f"<li>{line}</li>")
                    return "<ul>" + "".join(items) + "</ul>"

                return content
    except Exception:
        return format_transcription(raw_text, output=output)
