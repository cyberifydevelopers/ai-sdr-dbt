# services/interest_classifier.py
import os
import json
from typing import Optional, Tuple

try:
    # openai >= 1.0 client
    from openai import OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    _use_responses = True
except Exception:
    # fallback for older client
    import openai as _openai_legacy
    _openai_legacy.api_key = os.getenv("OPENAI_API_KEY")
    _client = _openai_legacy
    _use_responses = False

_ALLOWED = {"interested", "not-interested", "could-not-say"}

_SYSTEM = (
    "You are a call-center QA assistant. "
    "Classify the prospect's interest from the call transcript. "
    "Only three labels are allowed: interested, not-interested, could-not-say. "
    "Output STRICT JSON: {\"interest_status\": \"<label>\", \"confidence\": <0-1 float>, \"rationale\": \"short\"} with no extra text."
)

def _build_prompt(transcript_text: str) -> str:
    return (
        "Transcript:\n"
        f"{transcript_text}\n\n"
        "Rules:\n"
        "- 'interested' if caller explicitly agrees to proceed (appointment, demo, send documents) or shows positive buying intent.\n"
        "- 'not-interested' if caller declines, asks to stop, or clearly rejects.\n"
        "- 'could-not-say' if uncertain, too noisy/short, or mixed signals without clear intent.\n"
        "Return STRICT JSON ONLY."
    )

def classify_interest(transcript: Optional[str]) -> Tuple[Optional[str], Optional[float]]:
    """
    Returns (interest_status, confidence) or (None, None) if not classifiable / no transcript.
    """
    if not transcript:
        return (None, None)

    # If transcript is JSON (some VAPI payloads), try to extract text
    text = transcript
    if isinstance(transcript, (dict, list)):
        try:
            # common shapes: {'messages':[{'text':'...'}]} or {'text':'...'}
            if isinstance(transcript, dict) and "text" in transcript:
                text = transcript["text"]
            elif isinstance(transcript, dict) and "messages" in transcript:
                text = "\n".join([m.get("text","") for m in transcript.get("messages", []) if isinstance(m, dict)])
            else:
                text = json.dumps(transcript)[:4000]  # worst case
        except Exception:
            text = str(transcript)[:4000]

    prompt = _build_prompt(str(text)[:12000])  # guardrails

    try:
        if _use_responses:
            # Modern Responses API
            resp = _client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                input=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            content = resp.output_text if hasattr(resp, "output_text") else resp.choices[0].message.content
        else:
            # Legacy Chat Completions
            resp = _client.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            content = resp["choices"][0]["message"]["content"]

        data = json.loads(content)
        label = str(data.get("interest_status", "")).strip().lower()
        conf = float(data.get("confidence", 0.0) or 0.0)
        if label not in _ALLOWED:
            return (None, None)
        conf = max(0.0, min(conf, 1.0))
        return (label, conf)
    except Exception:
        return (None, None)
