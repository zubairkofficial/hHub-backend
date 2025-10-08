from __future__ import annotations

import os
import re
import json
from typing import List, Optional

import aiohttp
import logging

__all__ = ["format_transcription", "format_transcription_ai"]

log = logging.getLogger(__name__)

# ===============================================================
# Shared patterns & helpers
# ===============================================================

# Canonical roles
ROLE_RECEPTIONIST = "Receptionist"
ROLE_PATIENT = "Patient"

# Normalize lots of label variants → canonical roles
_SPEAKER_NORMALIZE = [
    (re.compile(r"(?i)\b(front\s*desk|reception(?:ist)?|office\s*staff|agent|rep)\b"), ROLE_RECEPTIONIST),
    (re.compile(r"(?i)\b(caller|customer|client|patient)\b"), ROLE_PATIENT),
]

# Accept many line styles:
#  - "- **Receptionist:** text"
#  - "Receptionist: text"
#  - "**Receptionist:** text"
#  - "Helena (Receptionist): text"
#  - "- Patient — text"
_LABEL_LINE = re.compile(
    r"""^\s*
        (?:[-*]\s*)?                             # optional bullet symbols
        (?:\*\*)?                                # optional starting bold
        (?P<label>[^:\-\u2014\*]+?(?:\s*\([^)]+\))?) # label or "Name (Role)"
        (?:\*\*)?                                # optional end bold
        \s*[:\-\u2014]\s*                        # colon, dash, or em dash
        (?P<body>.+)$                            # rest of line
    """,
    re.VERBOSE,
)

# Filler/stock phrases we can collapse if repeated
_FILLER_RX = re.compile(
    r"(?i)\b(this call is recorded|quality and training purposes|how can i help)\b"
)

# Times: 0:23, 12:30, 10:30am/pm
_TIME_RX = re.compile(r"\b(\d{1,2}:\d{2}\s?(?:am|pm)?)\b", re.I)

# Dates (US-ish & month names)
_DATE_RX = re.compile(
    r"\b("
    r"\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{1,2}-\d{1,2}-\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.? \d{1,2}, \d{4}|"
    r"(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+\d{4})"
    r")\b",
    re.I,
)

# Phones: E.164 or common US formats
_PHONE_RX = re.compile(
    r"\b("
    r"\+\d{10,15}"                       # +923331234567 / +14155552671
    r"|(?:\(?\d{3}\)?[-\s.]?\d{3}[-\s.]?\d{4})"  # (415) 555-2671 / 415-555-2671
    r")\b"
)

# Clinical key terms to emphasize
_KEYTERMS_RX = re.compile(
    r"\b("
    r"appointment|estimate|patient[s]?|new\s+patient|follow[\s-]?up|"
    r"insurance|copay|deductible|authorization|referral|"
    r"tomorrow|today|reschedule|cancel|availability|confirm"
    r")\b",
    re.I,
)

def _B(s: str, output: str) -> str:
    return f"**{s}**" if output == "markdown" else f"<strong>{s}</strong>"

def _bold_tokens(txt: str, *, output: str) -> str:
    txt = _TIME_RX.sub(lambda m: _B(m.group(1), output), txt)
    txt = _DATE_RX.sub(lambda m: _B(m.group(1), output), txt)
    txt = _PHONE_RX.sub(lambda m: _B(m.group(1), output), txt)
    txt = _KEYTERMS_RX.sub(lambda m: _B(m.group(1), output), txt)
    return txt

def _normalize_role(label: str) -> str:
    """Map any label variant (with optional '(role)') → canonical role or keep name (Role)."""
    label = label.strip()
    # If "Name (Role)" keep the name and normalize the role inside
    m = re.match(r"^(?P<name>.+?)\s*\((?P<role>[^)]+)\)\s*$", label)
    if m:
        name = m.group("name").strip()
        role = m.group("role").strip()
        for rx, rep in _SPEAKER_NORMALIZE:
            if rx.search(role):
                role = rep
                break
        # If the role didn't match any synonym, try to detect
        role_low = role.lower()
        if "reception" in role_low or "front" in role_low or "desk" in role_low:
            role = ROLE_RECEPTIONIST
        elif "patient" in role_low or "caller" in role_low or "customer" in role_low or "client" in role_low:
            role = ROLE_PATIENT
        return f"{name} ({role})"

    # No parentheses, normalize label word directly
    norm = label
    for rx, rep in _SPEAKER_NORMALIZE:
        if rx.search(label):
            norm = rep
            break

    # Heuristics if still raw
    l = norm.lower()
    if "reception" in l or "front" in l or "desk" in l or "office" in l or "agent" in l or "rep" in l:
        return ROLE_RECEPTIONIST
    if "caller" in l or "customer" in l or "client" in l or "patient" in l:
        return ROLE_PATIENT

    # If looks like a personal name and no role word, keep as-is
    # (Model might have already produced "Tatiana (Patient)"—we handle above.)
    return norm

def _mk_bullet(role_display: str, body: str, *, output: str) -> str:
    if output == "markdown":
        return f"- {_B(role_display + ':', output)} {body}"
    else:
        return f"<li>{_B(role_display + ':', output)} {body}</li>"

def _wrap(items: List[str], *, output: str) -> str:
    if output == "markdown":
        return "\n".join(items)
    return "<ul>" + "".join(items) + "</ul>"

def _collapse_fillers(lines: List[str]) -> List[str]:
    """Remove immediate duplicates of common filler lines to keep output clean."""
    out: List[str] = []
    prev_key: Optional[str] = None
    for ln in lines:
        key = _FILLER_RX.sub("", ln.lower()).strip()
        if not key:  # if line is only filler
            # allow one instance, drop repeats
            if prev_key == "":
                continue
            prev_key = ""
            out.append(ln)
            continue
        if key == prev_key:
            continue
        prev_key = key
        out.append(ln)
    return out

# ===============================================================
# Heuristic fallback (offline)
# ===============================================================
def format_transcription(raw_text: str, output: str = "markdown") -> str:
    """
    Heuristic formatter (fallback). Separates Receptionist vs Patient, highlights
    phones/dates/times, and produces bullets. Prefer `format_transcription_ai`.
    """
    def bold(s: str) -> str:
        return _B(s, output)

    def li(role: str, text: str) -> str:
        return _mk_bullet(role, text, output=output)

    txt = " ".join((raw_text or "").split())
    if not txt:
        return _wrap([li("System", "No transcription text was provided.")], output=output)

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

    receptionist_cues = re.compile(
        r"(?i)thanks for calling|how can i help|excuse me|usually|do you have any sort of dental insurance|this call is recorded|we are (?:on the phone|assisting another patient)"
    )
    patient_cues = re.compile(
        r"(?i)^hi\b|^hello\b|^yeah\b|^okay\b|^my name is|^i'?m\b|^i am\b|this is\b|calling from\b|can you|i would like|i was wondering|please call me back"
    )

    lines: List[str] = []
    current_role: Optional[str] = None

    for c in chunks:
        s = c.strip()

        if receptionist_cues.search(s):
            current_role = ROLE_RECEPTIONIST
        elif patient_cues.search(s):
            current_role = ROLE_PATIENT
        elif current_role is None:
            current_role = ROLE_RECEPTIONIST
        else:
            current_role = ROLE_PATIENT if current_role == ROLE_RECEPTIONIST else ROLE_RECEPTIONIST

        s = _bold_tokens(s, output=output)
        lines.append(li(current_role, s))

    lines = _collapse_fillers(lines)
    return _wrap(lines, output=output)

# ===============================================================
# AI-powered formatter with strong post-processing
# ===============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_APIKEY") or os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("TRANSCRIPT_FORMAT_MODEL", "gpt-4o-mini")

def _normalize_md_lines(md: str) -> str:
    """Normalize Markdown bullets like '- **Label:** text' to canonical roles."""
    out = []
    for line in md.splitlines():
        m = re.match(r"^\s*-\s*\*\*(.+?):\*\*\s*(.*)$", line)
        if not m:
            out.append(line)
            continue
        label, rest = m.group(1), m.group(2)
        norm = _normalize_role(label)
        out.append(f"- **{norm}:** {rest}")
    return "\n".join(out)

def _postprocess_any(content: str, *, output: str) -> str:
    """
    Accepts messy model output and enforces:
      • bullet per line
      • canonical/kept label with **bold** (or <strong>)
      • bold tokens (times, dates, phones, key terms)
      • HTML/Markdown wrapping
    """
    is_html = output == "html"

    raw_lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    normalized_items: List[str] = []

    for ln in raw_lines:
        # Try to parse "Label: body"
        m = _LABEL_LINE.match(ln)
        if m:
            label_raw = m.group("label").strip()
            body = m.group("body").strip()

            # Normalize label (and any '(role)' suffix)
            label_norm = _normalize_role(label_raw)

            # If label is a bare role word, keep it; if it's "Name (Role)" keep the whole
            # Example: "Tatiana (Patient)"
            # Also ensure final role words are exactly Receptionist/Patient where applicable.
            body = _bold_tokens(body, output=output)

            normalized_items.append(_mk_bullet(label_norm, body, output=output))
            continue

        # If the line has no explicit "label:", try to detect leading label word at start
        m2 = re.match(r"^\s*(Receptionist|Patient)\b[:\-\u2014]?\s*(.*)$", ln, flags=re.I)
        if m2:
            role = ROLE_RECEPTIONIST if m2.group(1).lower().startswith("reception") else ROLE_PATIENT
            body = _bold_tokens(m2.group(2).strip(), output=output)
            normalized_items.append(_mk_bullet(role, body, output=output))
            continue

        # Fallback: treat as unlabeled utterance, just bold tokens
        normalized_items.append(_mk_bullet(ROLE_RECEPTIONIST, _bold_tokens(ln, output=output), output=output))

    # Collapse repeated filler-y lines
    normalized_items = _collapse_fillers(normalized_items)

    return _wrap(normalized_items, output=output)

async def format_transcription_ai(
    raw_text: str,
    *,
    output: str = "markdown",   # "markdown" | "html"
    temperature: float = 0.2,
    timeout: int = 25,
) -> str:
    """
    Use GPT to format as bullets with strict 'Receptionist' / 'Patient' roles.
    Robust post-processing guarantees bolding & structure even if the model slips.
    Falls back to heuristic if anything fails or no API key is present.
    """
    if not raw_text or not raw_text.strip() or not OPENAI_API_KEY:
        return format_transcription(raw_text, output=output)

    system_msg = (
        "You format medical/dental clinic phone transcripts. "
        "Return bullet points per utterance. "
        "Label speakers as either 'Receptionist' or 'Patient'. "
        "If a proper name is evident, include it like 'Helena (Receptionist)' or 'Tatiana (Patient)'. "
        "Bold timestamps (e.g., 0:23), dates, phone numbers, and key terms such as appointment, estimate, patient, follow-up. "
        "Never invent details or names. "
        "Return only the final list with no preface."
    )

    user_msg = f"""Transcription:
{raw_text}

Format rules:
- One bullet per utterance.
- Start each line with Speaker label (Receptionist/Patient). If a name is present, use "Name (Receptionist/Patient)".
- Use {'**bold**' if output=='markdown' else '<strong>bold</strong>'} for timestamps, dates, phone numbers, and key terms (appointment, estimate, patient, follow-up, insurance, copay, today/tomorrow).
- Output only {output.upper()} content (no code fences).
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
                    log.warning("format_transcription_ai: non-200 %s", resp.status)
                    return format_transcription(raw_text, output=output)
                data = await resp.json()
                content = (data.get("choices", [{}])[0]
                              .get("message", {})
                              .get("content", "")).strip()

                if not content:
                    return format_transcription(raw_text, output=output)

                # If Markdown: normalize any stray labels like Caller/Client → Patient, etc.
                if output == "markdown":
                    content = _normalize_md_lines(content)

                # Strong post-processing for BOTH markdown and html
                return _postprocess_any(content, output=output)

    except Exception as e:
        log.exception("format_transcription_ai error: %s", e)
        return format_transcription(raw_text, output=output)
