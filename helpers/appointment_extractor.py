from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone as dtimezone
from typing import Optional, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

from models.auth import User
from models.appointment import Appointment, AppointmentOutcome
from models.call_log import CallLog
from models.call_detail import CallDetail

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _require_openai():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")
    return OPENAI_API_KEY

# ────────────────── Helpers ──────────────────

def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    # common voice-to-text forms: "plus 1 213 818 0318"
    s = re.sub(r"^\s*plus\s*", "+", s, flags=re.I)
    s = re.sub(r"[^\d+]", "", s)  # keep digits and '+' only
    # Collapse multiple '+' if any
    s = re.sub(r"^\++", "+", s)
    return s or None

def _tzinfo_from_string(tz_str: str, fallback: Optional[str] = None):
    """
    Accept:
      - IANA 'America/Los_Angeles'
      - Human 'America Los Angeles', 'Los Angeles', 'PST', 'PDT'
      - Offsets '+05:00', '-0300', 'UTC+5', '+5'
    """
    from zoneinfo import ZoneInfo

    s_in = tz_str or ""
    s = s_in.strip()

    # allow common aliases
    alias_map = {
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "los angeles": "America/Los_Angeles",
        "america los angeles": "America/Los_Angeles",
        "est": "America/New_York",
        "edt": "America/New_York",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
    }
    key = re.sub(r"[\s_]+", " ", s.lower())
    if key in alias_map:
        s = alias_map[key]

    # "America Los Angeles" -> "America/Los_Angeles"
    if "/" not in s and " " in s:
        parts = [p for p in s.split() if p]
        if len(parts) >= 2:
            s = parts[0] + "/" + "_".join(parts[1:])

    # If there is a slash but with spaces → replace with underscores
    if "/" in s and " " in s:
        a, b = s.split("/", 1)
        s = a + "/" + b.replace(" ", "_")

    # Try IANA
    try:
        return ZoneInfo(s)
    except Exception:
        pass

    # Try offset formats
    m = re.fullmatch(r'^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$', s_in or "")
    if m:
        sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if hh > 14 or mm > 59:
            raise ValueError("Invalid offset")
        delta = timedelta(hours=hh, minutes=mm)
        if sign == "-":
            delta = -delta
        return dtimezone(delta)

    # fallback if provided
    if fallback:
        try:
            return ZoneInfo(fallback)
        except Exception:
            pass

    raise ValueError(f"Invalid timezone string: {tz_str!r}")

def _safe_text(x) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, str):
        s = x.strip()
        return s if s else None
    try:
        if isinstance(x, (dict, list)):
            return json.dumps(x, ensure_ascii=False)
        return str(x)
    except Exception:
        return None

# ────────────────── Schema ──────────────────

class AppointmentExtracted(BaseModel):
    title: str = Field(..., description="Short reason/title of appointment")
    notes: Optional[str] = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d2$", description="YYYY-MM-DD")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM 24-hour")
    timezone: str = Field(..., description="IANA tz (e.g., 'Asia/Karachi') or offset like '+05:00'")
    phone: str = Field(..., min_length=6, max_length=32, description="number as string, keep '+' if present")
    location: Optional[str] = None
    status: Literal["Booked", "Follow-up Needed"]

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v):
        s = str(v or "").strip().lower()
        if s in {"booked"}:
            return "Booked"
        if s in {"follow up needed", "follow-up needed"}:
            return "Follow-up Needed"
        raise ValueError("status must be 'Booked' or 'Follow-up Needed'")

# ────────────────── LLM prompt ──────────────────

SYSTEM_MSG = (
    "You extract appointments from a sales/support call transcript. "
    "Return STRICT JSON only, matching the schema I describe. "
    "If the caller clearly agreed to book, status='Booked'. "
    "If they want to book but need a follow-up, status='Follow-up Needed'. "
    "Use 24h time and YYYY-MM-DD. If a field is not said clearly, leave it blank."
)

def _user_prompt(transcript: str, summary: Optional[str], context: dict) -> str:
    return (
        "Transcript:\n"
        f"{transcript}\n\n"
        "Summary (if any):\n"
        f"{summary or ''}\n\n"
        "Return a JSON with keys: "
        "title, notes, date (YYYY-MM-DD), time (HH:MM 24h), timezone,  "
        "phone, location, status (Booked|Follow-up Needed).\n"
        "Do not include any extra keys."
    )

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "notes": {"type": "string"},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "time": {"type": "string", "pattern": r"^\d{2}:\d{2}$"},
        "timezone": {"type": "string"},
        "phone": {"type": "string"},
        "location": {"type": "string"},
        "status": {"type": "string", "enum": ["Booked", "Follow-up Needed"]},
    },
    "required": ["status", "title", "date", "time", "timezone", "phone"],
    "additionalProperties": False,
}

async def _extract_with_openai(transcript: str, summary: Optional[str], extra_ctx: dict) -> dict:
    _require_openai()
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_schema", "json_schema": {"name": "appt", "schema": JSON_SCHEMA, "strict": True}},
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": _user_prompt(transcript, summary, extra_ctx)},
        ],
    }
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI error: {r.text}")
    data = r.json()
    content = (data["choices"][0]["message"]["content"] or "").strip()
    try:
        return json.loads(content)
    except Exception:
        return {}

# ────────────────── Public API ──────────────────

async def process_call_to_appointment(
    *,
    user: User,
    call_id: str,
    default_timezone: Optional[str] = None,
) -> Optional[str]:
    """
    Returns created appointment id (str) or None if skipped.
    Raises on hard errors.
    """
    cd = await CallDetail.get_or_none(user=user, call_id=call_id)
    cl = await CallLog.get_or_none(user=user, call_id=call_id)
    if not cd and not cl:
        return None

    # idempotency
    already = await Appointment.get_or_none(user=user, source_call_id=call_id)
    if already:
        return str(already.id)

    transcript = (cd and cd.transcript) or (cl and cl.transcript) or ""
    summary = (cd and cd.summary) or (cl and cl.summary) or None
    assistant_id = (cd and cd.assistant_id) or None
    if not transcript and not summary:
        return None

    raw = await _extract_with_openai(transcript, summary, {"assistant_id": assistant_id, "call_id": call_id})
    ap = AppointmentExtracted(**raw)

    # tz + time math (tolerant + fallback)
    tz_candidate = ap.timezone or default_timezone or "UTC"
    tzinfo = _tzinfo_from_string(tz_candidate, fallback=default_timezone or "UTC")

    start_naive = datetime.strptime(f"{ap.date} {ap.time}", "%Y-%m-%d %H:%M")
    start_at = start_naive.replace(tzinfo=tzinfo)

    # No duration in model: use zero-length; set end_at = start_at
    end_at = start_at

    status_enum = AppointmentOutcome.BOOKED if ap.status == "Booked" else AppointmentOutcome.FOLLOW_UP_NEEDED

    obj = await Appointment.create(
        user=user,
        assistant_id=assistant_id,
        source_call_id=call_id,
        source_transcript_id=None,
        title=ap.title,
        notes=_safe_text(ap.notes),
        phone=_normalize_phone(ap.phone) or ap.phone.strip(),
        location=_safe_text(ap.location),
        timezone=(default_timezone or tz_candidate),
        start_at=start_at,
        end_at=end_at,
        status=status_enum,
        extraction_version="v1",
        extraction_confidence=None,
        extraction_raw=raw,
    )

    if cd:
        await cd.save()  # optional backlink/flags

    return str(obj.id)
