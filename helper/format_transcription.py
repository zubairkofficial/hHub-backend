# E:\Shoaib\Projects\hHub\hHub-backend\helper\format_transcription.py
from __future__ import annotations

import re
from typing import List

__all__ = ["format_transcription"]

def format_transcription(raw_text: str, output: str = "markdown") -> str:
    """
    Convert a plain transcription into bullet-pointed conversation.

    - Separates Customer vs Receptionist turns (heuristics + simple alternation).
    - Bolds key details: timestamps, dates, phone numbers, names, and a few domain terms.
    - `output`: "markdown" | "html" (choose based on how your frontend renders).

    Returns:
        str: formatted list (Markdown bullets or <ul><li>…</li></ul>)
    """
    # ---------- helpers ----------
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

    # ---------- normalize ----------
    txt = " ".join((raw_text or "").split())  # collapse whitespace safely

    if not txt:
        return wrap_list([li("System", "No transcription text was provided.")])

    # ---------- split into clauses/mini-turns ----------
    # Keep delimiter tokens; they help infer speaker boundaries.
    cue_regex = (
        r'(?i)('
        r'thanks for calling|how can i help you|hi[, ]|hello[, ]|excuse me|'
        r'yeah[, ]|okay[, ]|thank you|usually|my name is|'
        r'and your phone number is|do you have any sort of dental insurance\??'
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
                chunks.append(buf.strip())
                buf = ""
        buf += (" " + t)
    if buf.strip():
        chunks.append(buf.strip())

    # ---------- role inference + highlighting ----------
    lines: List[str] = []
    current_role = None

    receptionist_cues = re.compile(
        r"(?i)thanks for calling|how can i help|excuse me|usually|do you have any sort of dental insurance"
    )
    customer_cues = re.compile(r"(?i)^hi\b|^hello\b|^yeah\b|^okay\b|^my name is")

    for c in chunks:
        s = c.strip()

        # decide speaker
        if receptionist_cues.search(s):
            current_role = "Receptionist"
        elif customer_cues.search(s):
            current_role = "Customer"
        elif current_role is None:
            current_role = "Receptionist"  # default first turn
        else:
            current_role = "Customer" if current_role == "Receptionist" else "Receptionist"

        # highlight timestamps (e.g., 0:23, 12:05)
        s = re.sub(r"\b(\d{1,2}:\d{2})\b", lambda m: bold(m.group(1)), s)

        # highlight common date formats
        s = re.sub(
            r"\b("
            r"\d{1,2}/\d{1,2}/\d{2,4}|"
            r"\d{1,2}-\d{1,2}-\d{2,4}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.? \d{1,2}, \d{4}"
            r")\b",
            lambda m: bold(m.group(1)),
            s,
        )

        # highlight phone numbers
        s = re.sub(
            r"\b(\+?\d{1,2}[-\s]?)?(\(?\d{3}\)?)[-\s]?\d{3}[-\s]?\d{4}\b",
            lambda m: bold(m.group(0)),
            s,
        )

        # highlight likely names from sample
        s = re.sub(r"\b(alissa|alyssa|aly)\b", lambda m: bold(m.group(1)), s, flags=re.I)

        # optional emphasis for domain terms
        s = re.sub(r"\b(appointment|teeth whitening|estimate)\b", lambda m: bold(m.group(1)), s, flags=re.I)

        lines.append(li(current_role, s))

    return wrap_list(lines)
