from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone as dtimezone
from typing import Optional, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query , Response
from pydantic import BaseModel, Field, field_validator

from models.auth import User
from models.appointment import Appointment, AppointmentOutcome
from models.call_log import CallLog
from models.call_detail import CallDetail
from helpers.token_helper import get_current_user
from helpers.Normalizers import normalize_extracted  

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _require_openai():
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OPENAI_API_KEY


def _tzinfo_from_string(tz_str: str, fallback: Optional[str] = None):
    """
    Accepts IANA like 'Asia/Karachi' OR offsets like '+05:00', '-0300', 'UTC+5', '+5'
    """
    from zoneinfo import ZoneInfo

    s_in = tz_str or ""
    s = s_in.strip()
    # try IANA
    try:
        return ZoneInfo(s)
    except Exception:
        pass
    # try offset
    m = re.fullmatch(r'^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$', s_in or "")
    if m:
        sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if hh > 14 or mm > 59:
            raise ValueError("Invalid offset")
        delta = timedelta(hours=hh, minutes=mm)
        if sign == "-":
            delta = -delta
        return dtimezone(delta)
    # fallback
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

# ───────── Pydantic I/O ─────────

class AppointmentExtracted(BaseModel):
    """
    Fields we expect to extract from transcript. (No duration anymore.)
    """
    title: str = Field(..., description="Short reason/title of appointment")
    notes: Optional[str] = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
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

class AppointmentOut(BaseModel):
    id: UUID
    user_id: int
    assistant_id: Optional[UUID] = None
    source_call_id: Optional[str]
    title: str
    notes: Optional[str]
    phone: str
    location: Optional[str]
    timezone: str
    start_at: datetime
    end_at: datetime
    status: AppointmentOutcome
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



class AppointmentUpdateIn(BaseModel):
    """
    Partial update. Only provided fields will be updated.
    If any of date/time/timezone are provided, start_at/end_at will be recomputed.
    """
    title: Optional[str] = None
    notes: Optional[str] = None
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    timezone: Optional[str] = None  # IANA or offset ('+05:00')
    phone: Optional[str] = Field(None, min_length=6, max_length=32)
    location: Optional[str] = None
    status: Optional[Literal["Booked", "Follow-up Needed"]] = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v):
        if v is None:
            return None
        s = str(v or "").strip().lower()
        if s in {"booked"}:
            return "Booked"
        if s in {"follow up needed", "follow-up needed"}:
            return "Follow-up Needed"
        raise ValueError("status must be 'Booked' or 'Follow-up Needed'")


SYSTEM_MSG = (
    "You extract appointments from a sales/support call transcript. "
    "Return STRICT JSON only, matching the schema I describe. "
    "If the caller clearly agreed to book, status='Booked'. "
    "If they want to book but need a follow-up, status='Follow-up Needed'. "
    "Normalize fields: "
    "date=YYYY-MM-DD, time=24h HH:MM, timezone=IANA (map common aliases like 'America Los Angeles'→'America/Los_Angeles'), "
    "phone=E.164 (leading '+', digits only; convert 'plus 121...' to '+121...'). "
    "If a field isn't said clearly, return null for optional fields (notes/location). "
    "Return JSON only."
)

def _user_prompt(transcript: str, summary: Optional[str], context: dict) -> str:
    return (
        "Transcript:\n"
        f"{transcript}\n\n"
        "Summary (if any):\n"
        f"{summary or ''}\n\n"
        "Return a JSON with keys: "
        "title, notes, date (YYYY-MM-DD), time (HH:MM 24h), timezone, "
        "phone, location, status (Booked|Follow-up Needed).\n"
        "Do not include any extra keys."
    )

# OpenAI strict json_schema: include ALL props in required; allow null for optional ones.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "notes": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "time": {"type": "string", "pattern": r"^\d{2}:\d{2}$"},
        "timezone": {"type": "string"},
        "phone": {"type": "string"},
        "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "status": {"type": "string", "enum": ["Booked", "Follow-up Needed"]},
    },
    "required": [
        "title",
        "notes",
        "date",
        "time",
        "timezone",
        "phone",
        "location",
        "status",
    ],
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
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "appt", "schema": JSON_SCHEMA, "strict": True},
        },
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": _user_prompt(transcript, summary, extra_ctx)},
        ],
    }
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=body)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {r.text}")
    data = r.json()
    content = (data["choices"][0]["message"]["content"] or "").strip()
    try:
        return json.loads(content)
    except Exception:
        # model promised JSON; guard anyway
        return {}

# ───────── Endpoints ─────────

@router.post(
    "/me/appointments/from-call/{call_id}",
    response_model=AppointmentOut,
    summary="Extract & create one appointment from a single call (scoped to me)"
)
async def create_appointment_from_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    default_timezone: Optional[str] = Query(None, description="Fallback timezone if not in transcript"),
):
    # Prefer CallDetail, then CallLog
    cd = await CallDetail.get_or_none(user=current_user, call_id=call_id)
    cl = await CallLog.get_or_none(user=current_user, call_id=call_id)

    if not cd and not cl:
        raise HTTPException(status_code=404, detail="Call not found")

    # Idempotency by call_id
    already = await Appointment.get_or_none(user=current_user, source_call_id=call_id)
    if already:
        return AppointmentOut.model_validate(already, from_attributes=True)

    transcript = (cd and cd.transcript) or (cl and cl.transcript) or ""
    summary = (cd and cd.summary) or (cl and cl.summary) or None
    assistant_id = (cd and cd.assistant_id) or None

    if not transcript and not summary:
        raise HTTPException(status_code=422, detail="No transcript/summary available on this call")

    # Extract via LLM
    raw = await _extract_with_openai(transcript, summary, {"assistant_id": assistant_id, "call_id": call_id})

    # Validate + normalize
    try:
        ap = AppointmentExtracted(**raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed/invalid: {e}")

    clean = normalize_extracted(ap)

    tz = clean.get("timezone") or default_timezone or "UTC"
    tzinfo = _tzinfo_from_string(tz, fallback=default_timezone or "UTC")
    start_naive = datetime.strptime(f'{clean["date"]} {clean["time"]}', "%Y-%m-%d %H:%M")
    start_at = start_naive.replace(tzinfo=tzinfo)
    # No duration: choose end_at = start_at (zero-length). If your DB allows NULL, you can set `end_at=None`.
    end_at = start_at

    status_enum = AppointmentOutcome.BOOKED if clean.get("status") == "Booked" else AppointmentOutcome.FOLLOW_UP_NEEDED

    # Create
    obj = await Appointment.create(
        user=current_user,
        assistant_id=assistant_id,
        source_call_id=call_id,
        source_transcript_id=None,
        title=clean["title"],
        notes=_safe_text(clean.get("notes")),
        phone=clean["phone"],
        location=_safe_text(clean.get("location")),
        timezone=tz,
        start_at=start_at,
        end_at=end_at,
        status=status_enum,
        # keep extraction metadata if your DB has these columns; otherwise remove them:
        extraction_version="v1",
        extraction_confidence=None,
        extraction_raw=raw,
    )

    if cd:
        await cd.save()

    return AppointmentOut.model_validate(obj, from_attributes=True)

@router.post(
    "/me/appointments/extract-batch",
    summary="Scan my recent calls, extract appointments for any with no appointment yet",
    response_model=dict
)
async def extract_batch_for_me(
    current_user: User = Depends(get_current_user),
    limit: int = Query(25, ge=1, le=200),
    status_filter: Optional[Literal["Booked","Follow-up Needed"]] = Query(None, description="Only consider calls with this unified status (from your pipeline)"),
    default_timezone: Optional[str] = Query(None),
):
    q = CallLog.filter(user=current_user)
    if status_filter:
        q = q.filter(status=status_filter)
    rows = await q.order_by("-call_started_at", "-id").limit(limit)

    created = 0
    skipped = 0
    errors = 0
    ids = []

    import logging, traceback
    lg = logging.getLogger("appointments")

    for cl in rows:
        try:
            # Already created?
            exists = await Appointment.get_or_none(user=current_user, source_call_id=cl.call_id)
            if exists:
                skipped += 1
                continue

            # Need content
            transcript = cl.transcript or ""
            summary = cl.summary or ""
            if not transcript and not summary:
                skipped += 1
                continue

            # assistant context if available
            cd = await CallDetail.get_or_none(user=current_user, call_id=cl.call_id)
            assistant_id = cd.assistant_id if cd else None

            # Extract, validate, normalize
            raw = await _extract_with_openai(transcript, summary, {"assistant_id": assistant_id, "call_id": cl.call_id})
            ap = AppointmentExtracted(**raw)
            clean = normalize_extracted(ap)

            tz = clean.get("timezone") or default_timezone or "UTC"
            tzinfo = _tzinfo_from_string(tz, fallback=default_timezone or "UTC")
            start_naive = datetime.strptime(f'{clean["date"]} {clean["time"]}', "%Y-%m-%d %H:%M")
            start_at = start_naive.replace(tzinfo=tzinfo)
            # No duration: set end_at = start_at (or None if allowed).
            end_at = start_at

            status_enum = AppointmentOutcome.BOOKED if clean.get("status") == "Booked" else AppointmentOutcome.FOLLOW_UP_NEEDED

            obj = await Appointment.create(
                user=current_user,
                assistant_id=assistant_id,
                source_call_id=cl.call_id,
                title=clean["title"],
                notes=_safe_text(clean.get("notes")),
                phone=clean["phone"],
                location=_safe_text(clean.get("location")),
                timezone=tz,
                start_at=start_at,
                end_at=end_at,
                status=status_enum,
                # keep extraction metadata only if your DB has these:
                extraction_version="v1",
                extraction_confidence=None,
                extraction_raw=raw,
            )
            ids.append(str(obj.id))
            created += 1

        except Exception as e:
            errors += 1
            lg.error("batch extract error for call %s: %s\n%s", cl.call_id, e, traceback.format_exc())

    return {
        "success": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "ids": ids,
        "message": f"Processed {len(rows)} calls",
    }

# ───────── List / Read ─────────

class AppointmentListOut(BaseModel):
    success: bool
    total: int
    items: list[AppointmentOut]

@router.get("/me/appointments", response_model=AppointmentListOut, summary="List my appointments")
async def list_my_appointments(
    current_user: User = Depends(get_current_user),
    status: Optional[Literal["Booked","Follow-up Needed"]] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (start_at >=)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (start_at <=)"),
    q: Optional[str] = Query(None, description="search in title/notes/phone"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    qs = Appointment.filter(user=current_user)
    if status:
        qs = qs.filter(status=status)

    def _parse_date(s: Optional[str]):
        if not s: return None
        try:
            return datetime.fromisoformat(s.strip() + "T00:00:00")
        except Exception:
            return None

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df: qs = qs.filter(start_at__gte=df)
    if dt: qs = qs.filter(start_at__lte=dt + timedelta(days=1, seconds=-1))

    if q:
        from tortoise.expressions import Q as TQ
        s = q.strip()
        qs = qs.filter(TQ(title__icontains=s) | TQ(notes__icontains=s) | TQ(phone__icontains=s))

    total = await qs.count()
    rows = await qs.order_by("-start_at").offset((page-1)*page_size).limit(page_size)
    items = [AppointmentOut.model_validate(r, from_attributes=True) for r in rows]
    return {"success": True, "total": total, "items": items}

@router.get("/me/appointments/{appointment_id}", response_model=AppointmentOut, summary="Get my appointment")
async def get_my_appointment(appointment_id: str, current_user: User = Depends(get_current_user)):
    appt = await Appointment.get_or_none(id=appointment_id, user=current_user)
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")
    return AppointmentOut.model_validate(appt, from_attributes=True)



@router.patch(
    "/me/appointments/{appointment_id}",
    response_model=AppointmentOut,
    summary="Update my appointment (partial)"
)
async def update_my_appointment(
    appointment_id: str,
    payload: AppointmentUpdateIn,
    current_user: User = Depends(get_current_user),
):
    appt = await Appointment.get_or_none(id=appointment_id, user=current_user)
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")

    # Track original values used to recompute start time if needed
    # Prefer the appointment's existing timezone unless a new one is provided
    new_tz_str = payload.timezone or appt.timezone
    try:
        tzinfo = _tzinfo_from_string(new_tz_str, fallback="UTC")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid timezone: {e}")

    # Extract the current date/time in the (possibly new) timezone
    current_local = appt.start_at.astimezone(tzinfo)
    cur_date = current_local.date().isoformat()  # 'YYYY-MM-DD'
    cur_time = current_local.strftime("%H:%M")   # 'HH:MM'

    # Use provided values or fall back to current ones
    upd_date = payload.date or cur_date
    upd_time = payload.time or cur_time

    # If date, time, or timezone changed, recompute start_at/end_at
    time_will_change = any([
        payload.date is not None,
        payload.time is not None,
        payload.timezone is not None,
    ])
    if time_will_change:
        try:
            start_naive = datetime.strptime(f"{upd_date} {upd_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date/time format")
        new_start = start_naive.replace(tzinfo=tzinfo)
        appt.start_at = new_start
        appt.end_at = new_start  # zero-length, consistent with create

    # Title / notes / phone / location
    if payload.title is not None:
        appt.title = payload.title.strip()
    if payload.notes is not None:
        appt.notes = _safe_text(payload.notes)
    if payload.phone is not None:
        appt.phone = payload.phone.strip()
    if payload.location is not None:
        appt.location = _safe_text(payload.location)

    # Timezone string persisted as provided (normalized/validated above)
    if payload.timezone is not None:
        appt.timezone = new_tz_str

    # Status (map to enum)
    if payload.status is not None:
        appt.status = (
            AppointmentOutcome.BOOKED
            if payload.status == "Booked"
            else AppointmentOutcome.FOLLOW_UP_NEEDED
        )

    await appt.save()
    return AppointmentOut.model_validate(appt, from_attributes=True)




@router.delete(
    "/me/appointments/{appointment_id}",
    summary="Delete my appointment",
    response_model=dict
)
async def delete_my_appointment(
    appointment_id: str,
    current_user: User = Depends(get_current_user),
):
    appt = await Appointment.get_or_none(id=appointment_id, user=current_user)
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")

    await appt.delete()
    return {"success": True, "deleted": str(appointment_id)}




