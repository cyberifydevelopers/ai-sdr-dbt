# sms_controller.py

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
import json
import os
from typing import Annotated, List, Optional, Tuple, Dict, Any, AsyncGenerator
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Form, Query
import logging
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import httpx
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from twilio.base.exceptions import TwilioRestException

from tortoise.expressions import Q

from helpers.token_helper import get_current_user, decode_user_token, generate_user_token
from helpers.vapi_helper import get_headers  # if using your VAPI
from models.auth import User
from models.purchased_numbers import PurchasedNumber
from models.assistant import Assistant
from models.appointment import Appointment, AppointmentStatus
from models.message import MessageJob, MessageRecord
from scheduler.campaign_scheduler import schedule_minutely_job, nudge_once

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TextMessageRequest(BaseModel):
    to_number: str
    body: str
    from_number: Optional[str] = None
    status_webhook: Optional[str] = None  # optional override for Twilio status callback

class TextAssistantCreate(BaseModel):
    name: str
    provider: str
    model: str
    voice_provider: Optional[str] = None
    voice: Optional[str] = None
    system_prompt: str
    language: Optional[str] = None
    forwardingPhoneNumber: Optional[str] = None
    assistant_toggle: Optional[bool] = True

class JobQuery(BaseModel):
    job_id: Optional[str] = None

class MessageScheduledRequest(BaseModel):
    assistant_id: Optional[int] = None
    from_number: Optional[str] = None
    limit: Optional[int] = None
    # If True, run in background and immediately return a job_id; progress via SSE
    background: Optional[bool] = True
    # Multi-send and retry configuration
    messages_per_recipient: Optional[int] = Field(default=1, ge=1, le=10)
    retry_count: Optional[int] = Field(default=0, ge=0, le=5)
    retry_delay_seconds: Optional[int] = Field(default=60, ge=5, le=3600)
    per_message_delay_seconds: Optional[int] = Field(default=0, ge=0, le=3600)
    # Scheduled window filtering
    horizon_hours: Optional[int] = Field(default=None, description="Override horizon hours; 0 disables window filter")
    include_past_minutes: Optional[int] = Field(default=0, ge=0, le=1440)
    include_unowned: Optional[bool] = Field(default=True, description="Include appointments with null user_id as fallback")
    # Dedupe/backoff controls
    allow_repeat_to_same_number: Optional[bool] = Field(default=True, description="Allow sending again to same number even if a prior success exists")
    unscheduled_backoff_hours: Optional[int] = Field(default=None, description="Override UNSCHEDULED_BACKOFF_HOURS for unscheduled flow")

class AttachAssistantRequest(BaseModel):
    phone_number: str
    assistant_id: Optional[int] = None
    # advisory only; no migrations required
    kind: Optional[str] = Field(default=None, description="scheduled|unscheduled (advisory only)")

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter()
logger = logging.getLogger("text_assistant")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
# ---- SSE token helpers -------------------------------------------------------

def _make_sse_token(user_id: int, job_id: str, ttl_seconds: int = 600) -> str:
    """
    Create a short-lived JWT for SSE auth that is scoped to a specific job.
    """
    exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    payload = {"id": user_id, "job_id": job_id, "kind": "sse", "exp": exp}
    return generate_user_token(payload)

def _validate_sse_token(token: str, expected_job_id: str) -> Optional[int]:
    """
    Validate SSE token and return user_id if valid and scoped to expected job.
    """
    try:
        claims = decode_user_token(token)
        if not isinstance(claims, dict):
            return None
        if claims.get("kind") != "sse":
            return None
        if claims.get("job_id") != expected_job_id:
            return None
        uid = claims.get("id")
        if not isinstance(uid, int):
            return None
        return uid
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _twilio_client_from_values(account_sid: Optional[str], auth_token: Optional[str]) -> Tuple[Client, str, str]:
    sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
    token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise HTTPException(
            status_code=400,
            detail="No Twilio credentials found for this user. Set them via POST /twilio/credentials.",
        )
    return Client(sid, token), sid, token

def _twilio_client_for_user_sync(user: User) -> Tuple[Client, str, str]:
    return _twilio_client_from_values(
        getattr(user, "twilio_account_sid", None),
        getattr(user, "twilio_auth_token", None),
    )

def _build_status_callback_url(request: Request, override_url: Optional[str] = None) -> Optional[str]:
    """
    Build a Twilio StatusCallback URL only if it is publicly reachable.
    - If override_url is provided and valid, use it.
    - Else if PUBLIC_BASE_URL is set and valid, construct from it.
    - Else return None (skip StatusCallback to avoid Twilio 21609 on localhost).
    """
    def _is_valid_public(u: str) -> bool:
        try:
            p = urlparse(u)
            if p.scheme not in ("http", "https"):
                return False
            if not p.netloc:
                return False
            host = p.hostname or ""
            if host in ("localhost", "127.0.0.1", "::1"):
                return False
            return True
        except Exception:
            return False

    if override_url and _is_valid_public(override_url):
        return override_url

    public = os.getenv("PUBLIC_BASE_URL")
    if public:
        base = public.rstrip("/")
        candidate = f"{base}/api/text/sms-status"
        if _is_valid_public(candidate):
            return candidate

    # As a last resort, do not set StatusCallback; Twilio cannot reach localhost
    return None

def _sanitize_phone(number: str) -> str:
    """
    Light sanitization: trim whitespace. Avoid aggressive rewriting to prevent
    accidental E.164 mis-formatting across locales.
    """
    return (number or "").strip()

def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")

async def _prefer_assistant_for_appt(user_id: int, appt: Appointment, default_assistant: Optional[Assistant]) -> Optional[Assistant]:
    """Use per-appointment assistant if your model has assistant_id; otherwise default."""
    try:
        if getattr(appt, "assistant_id", None):
            return await Assistant.get_or_none(id=appt.assistant_id, user_id=user_id)
    except Exception:
        pass
    return default_assistant

async def _generate_via_vapi_or_openai(system_prompt: str, user_message: str, user: Optional[User] = None) -> Optional[str]:
    """
    Prefer your VAPI (helpers.vapi_helper.get_headers) if VAPI_URL set, else fallback to OpenAI.
    """
    vapi_url = os.getenv("VAPI_URL")
    if vapi_url:
        try:
            headers = get_headers(user=user)
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    f"{vapi_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": os.getenv("VAPI_MODEL", "gpt-4o-mini"),
                        "temperature": 0.4,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    },
                )
                res.raise_for_status()
                data = res.json()
                text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                if text:
                    return text
        except Exception:
            pass
    # Fallback to OpenAI
    return _safe_openai_generate(system_prompt, user_message)

def _safe_openai_generate(system_prompt: str, user_message: str):
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.4,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            import openai  # type: ignore
            openai.api_key = api_key
            resp = openai.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.4,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return (resp["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return None

async def _twilio_send_message(
    client: Client,
    body: str,
    from_number: str,
    to_number: str,
    status_callback: Optional[str] = None,
) -> Any:
    """Run Twilio's sync call in a thread so we don't block the event loop."""
    def _send():
        return client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
            status_callback=status_callback if status_callback else None,
        )
    return await run_in_threadpool(_send)

async def _store_record_outbound(
    *,
    job: Optional[MessageJob],
    user: User,
    assistant: Optional[Assistant],
    appointment: Optional[Appointment],
    to_number: str,
    from_number: str,
    body: str,
    sid: Optional[str],
    success: bool,
    error: Optional[str] = None,
):
    # Ensure a job exists to satisfy NOT NULL constraint on message_records.job_id
    if job is None:
        job = await MessageJob.create(
            user=user,
            assistant=assistant,
            from_number=from_number,
            status="completed",
            total=1,
            sent=1 if success else 0,
            failed=0 if success else 1,
        )

    await MessageRecord.create(
        job=job,
        user=user,
        assistant=assistant,
        appointment=appointment,
        to_number=to_number,
        from_number=from_number,
        body=body[:1000],
        sid=sid,
        success=success,
        error=error,
    )

async def _store_record_inbound(
    *,
    user: User,
    purchased_to: str,
    from_external: str,
    body: str,
    sid: Optional[str],
    ok: bool = True,
    error: Optional[str] = None,
):
    # Create a placeholder job for inbound messages to satisfy NOT NULL constraint
    job = await MessageJob.create(
        user=user,
        assistant=None,
        from_number=purchased_to,
        status="completed",
        total=1,
        sent=1 if ok else 0,
        failed=0 if ok else 1,
    )

    await MessageRecord.create(
        job=job,
        user=user,
        assistant=None,
        appointment=None,
        to_number=purchased_to,
        from_number=from_external,
        body=body[:1000],
        sid=sid,
        success=ok,
        error=error,
    )

# ---- Appointment timing/window knobs ----------------------------------------

def _ensure_aware(dt: datetime, tz_str: Optional[str]) -> datetime:
    """Ensure datetime is timezone-aware using provided tz string or UTC."""
    if dt.tzinfo:
        return dt
    try:
        if tz_str:
            return dt.replace(tzinfo=ZoneInfo(tz_str))
    except Exception:
        pass
    return dt.replace(tzinfo=timezone.utc)

def _now_like(appt: Appointment) -> datetime:
    """Return 'now' aligned with the appointment tz."""
    tz_name = getattr(appt, "timezone", None)
    try:
        if tz_name:
            return datetime.now(tz=ZoneInfo(tz_name))
    except Exception:
        pass
    return datetime.now(tz=timezone.utc)

def _in_scheduled_window(appt: Appointment, *, horizon_hours: Optional[int] = None, include_past_minutes: int = 0) -> bool:
    """
    Only push reminders for near-future SCHEDULED appointments.
    Default: within next 48h (configurable via SCHEDULED_HORIZON_HOURS). If horizon_hours == 0, no upper bound.
    include_past_minutes allows slight grace period for recently missed times.
    """
    if horizon_hours is None:
        try:
            horizon_hours = int(os.getenv("SCHEDULED_HORIZON_HOURS", "48"))
        except Exception:
            horizon_hours = 48
    now = _now_like(appt)
    start_at = _ensure_aware(appt.start_at, getattr(appt, "timezone", None))
    lower = now - timedelta(minutes=max(0, include_past_minutes))
    if horizon_hours == 0:
        return start_at >= lower
    return lower <= start_at <= now + timedelta(hours=max(0, horizon_hours))

async def _unscheduled_backoff_ok_async(phone: str, user: User, since_hours: Optional[int] = None) -> bool:
    """
    Optional anti-spam guard for unscheduled nudges:
    ensure we haven't texted this phone recently.
    """
    if since_hours is None:
        try:
            since_hours = int(os.getenv("UNSCHEDULED_BACKOFF_HOURS", "0"))
        except Exception:
            since_hours = 0
    if since_hours <= 0:
        return True
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    recent = await MessageRecord.filter(
        user=user, to_number=phone, created_at__gte=since
    ).exists()
    return not recent

# ---- Assistant picking without migrations -----------------------------------

async def _pick_assistant_for_flow(db_user: User, flow: str) -> Optional[Assistant]:
    """
    flow: 'scheduled' | 'unscheduled'
    Priority:
      1) Env ID (SCHEDULED_ASSISTANT_ID / UNSCHEDULED_ASSISTANT_ID)
      2) Env NAME (SCHEDULED_ASSISTANT_NAME / UNSCHEDULED_ASSISTANT_NAME)
      3) Enabled assistant whose name contains '[scheduled]' or '[unscheduled]'
      4) Any enabled assistant (fallback)
    """
    env_id_key = "SCHEDULED_ASSISTANT_ID" if flow == "scheduled" else "UNSCHEDULED_ASSISTANT_ID"
    env_name_key = "SCHEDULED_ASSISTANT_NAME" if flow == "scheduled" else "UNSCHEDULED_ASSISTANT_NAME"

    env_id = os.getenv(env_id_key)
    if env_id and env_id.isdigit():
        a = await Assistant.get_or_none(id=int(env_id), user=db_user)
        if a:
            return a

    env_name = os.getenv(env_name_key)
    if env_name:
        a = await Assistant.filter(user=db_user, name=env_name).first()
        if a:
            return a

    needle = "[scheduled]" if flow == "scheduled" else "[unscheduled]"
    a = await Assistant.filter(user=db_user, assistant_toggle=True, name__icontains=needle).first()
    if a:
        return a

    return await Assistant.filter(user=db_user, assistant_toggle=True).first()

# ---- Twilio webhook signature (optional) ------------------------------------

def _validate_twilio_signature(request: Request, form_data: Dict[str, str]) -> bool:
    """
    Set TWILIO_VALIDATE_SIGNATURE=true to enable. Requires TWILIO_AUTH_TOKEN.
    """
    if os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() != "true":
        return True
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        return False
    try:
        signature = request.headers.get("X-Twilio-Signature", "")
        validator = RequestValidator(auth_token)
        # Twilio expects the full URL as seen by Twilio (PUBLIC_BASE_URL helps behind proxies)
        base_url = os.getenv("PUBLIC_BASE_URL")
        url = str(request.url)
        if base_url:
            path_q = request.url.path
            if request.url.query:
                path_q += f"?{request.url.query}"
            url = f"{base_url.rstrip('/')}{path_q}"
        return validator.validate(url, form_data, signature)
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# Real-time progress (polling via SSE)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/text/message-progress")
async def get_message_progress(
    job_id: Optional[str] = None,
    user: Annotated[User, Depends(get_current_user)] = None
):
    if not job_id:
        job = await MessageJob.filter(user=user).order_by("-created_at").first()
        if not job:
            return {"success": True, "found": False}
    else:
        job = await MessageJob.get_or_none(id=job_id, user=user)
        if not job:
            return {"success": True, "found": False}

    return {
        "success": True,
        "found": True,
        "job": {
            "id": str(job.id),
            "status": job.status,
            "from_number": job.from_number,
            "assistant_id": job.assistant_id,
            "total": job.total,
            "sent": job.sent,
            "failed": job.failed,
            "created_at": job.created_at,
        }
    }

@router.get("/text/message-progress-sse")
async def stream_message_progress_sse(
    request: Request,
    job_id: str = Query(..., description="Job ID to stream updates for"),
    token: Optional[str] = Query(default=None, description="JWT token (fallback for EventSource)"),
    sse: Optional[str] = Query(default=None, description="Ephemeral SSE token scoped to job_id")
):
    # Manual auth to support EventSource (no Authorization header).
    # Priority: SSE token (scoped, short-lived) → Authorization header → query token → cookies
    auth_user: Optional[User] = None
    try:
        uid_from_sse: Optional[int] = None
        if sse:
            uid_from_sse = _validate_sse_token(sse, job_id)
            if uid_from_sse:
                auth_user = await User.get_or_none(id=uid_from_sse)
        if not auth_user:
            auth_header = request.headers.get("Authorization")
            raw_token: Optional[str] = None
            if auth_header and auth_header.lower().startswith("bearer "):
                raw_token = auth_header.split(" ", 1)[1]
            elif token:
                raw_token = token
            else:
                # Try common cookie names
                raw_token = request.cookies.get("token") or request.cookies.get("access_token") or request.cookies.get("Authorization")
            if raw_token:
                creds = decode_user_token(raw_token)
                uid = creds.get("id") if isinstance(creds, dict) else None
                if uid is not None:
                    auth_user = await User.get_or_none(id=uid)
    except Exception:
        auth_user = None
    if not auth_user:
        logger.warning(f"[sse] auth failed for job_id={job_id}")
        raise HTTPException(status_code=403, detail="Not authenticated")
    async def event_stream() -> AsyncGenerator[bytes, None]:
        """
        Very light polling every ~1s that pushes SSE until job completes.
        Works without Redis; easy to swap to pub/sub later.
        """
        last: Dict[str, Any] = {}
        while True:
            if await request.is_disconnected():
                break
            job = await MessageJob.get_or_none(id=job_id, user=auth_user)
            if not job:
                logger.info(f"[sse] job not found job_id={job_id}")
                yield b"event: done\ndata: {\"error\":\"not_found\"}\n\n"
                break
            payload = {
                "id": str(job.id),
                "status": job.status,
                "total": job.total,
                "sent": job.sent,
                "failed": job.failed,
                "from_number": job.from_number,
                "assistant_id": job.assistant_id,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            if payload != last:
                # emit valid JSON
                logger.info(f"[sse] prog job_id={job_id} sent={payload['sent']} failed={payload['failed']} status={payload['status']}")
                yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
                last = payload
            if job.status in ("completed", "failed", "canceled"):
                logger.info(f"[sse] done job_id={job_id} status={job.status}")
                yield b"event: done\ndata: {}\n\n"
                break
            await asyncio.sleep(1.0)
    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream", "Connection": "keep-alive"}
    return StreamingResponse(event_stream(), headers=headers)

# ─────────────────────────────────────────────────────────────────────────────
# Message browsing (filters + threads)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/text/messages")
async def list_messages(
    limit: int = 100,
    offset: int = 0,
    success: Optional[bool] = None,
    job_id: Optional[str] = None,
    assistant_id: Optional[int] = None,
    to_like: Optional[str] = None,
    from_like: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    peer_number: Optional[str] = None,   # external number for a "thread"
    user: Annotated[User, Depends(get_current_user)] = None,
):
    q = MessageRecord.filter(user=user).order_by("-created_at")
    if success is not None:
        q = q.filter(success=success)
    if job_id:
        q = q.filter(job_id=job_id)
    if assistant_id:
        q = q.filter(assistant_id=assistant_id)
    if to_like:
        q = q.filter(to_number__icontains=to_like)
    if from_like:
        q = q.filter(from_number__icontains=from_like)
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
            q = q.filter(created_at__gte=start_dt)
        except Exception:
            pass
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            q = q.filter(created_at__lte=end_dt)
        except Exception:
            pass

    # Thread filter with Q OR
    if peer_number:
        q = q.filter(Q(to_number__icontains=peer_number) | Q(from_number__icontains=peer_number))

    total = await q.count()

    # Preload purchased numbers once for direction calc (avoid N+1)
    purchased_set = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))

    rows = await q.offset(offset).limit(limit)
    def _direction(r) -> str:
        # if 'to_number' is one of ours, then the message is INBOUND
        return "inbound" if r.to_number in purchased_set else "outbound"

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "job_id": str(r.job_id) if r.job_id else None,
                "assistant_id": r.assistant_id,
                "appointment_id": str(r.appointment_id) if r.appointment_id else None,
                "from_number": r.from_number,
                "to_number": r.to_number,
                "sid": r.sid,
                "success": r.success,
                "error": r.error,
                "body": r.body,
                "created_at": r.created_at,
                "direction": _direction(r),
            }
            for r in rows
        ],
    }

@router.get("/text/threads")
async def list_threads(
    limit: int = 50,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    """
    Lightweight "thread" rollup by external number. We derive "peer" as the non-purchased number.
    """
    purchased = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))
    rows = await MessageRecord.filter(user=user).order_by("-created_at").limit(1000)
    threads: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a, b = r.from_number, r.to_number
        if a in purchased and b not in purchased:
            peer = b
            mynum = a
        elif b in purchased and a not in purchased:
            peer = a
            mynum = b
        else:
            continue
        t = threads.get(peer)
        if not t:
            threads[peer] = {
                "peer_number": peer,
                "my_number": mynum,
                "last_message_at": r.created_at,
                "last_body": r.body,
                "last_direction": "inbound" if r.to_number in purchased else "outbound",
                "count": 1,
            }
        else:
            t["count"] += 1
            if r.created_at and (t["last_message_at"] is None or r.created_at > t["last_message_at"]):
                t["last_message_at"] = r.created_at
                t["last_body"] = r.body
                t["last_direction"] = "inbound" if r.to_number in purchased else "outbound"
    items = sorted(threads.values(), key=lambda x: (x["last_message_at"] or datetime.min), reverse=True)[:limit]
    return {"items": items, "total": len(items)}

# ─────────────────────────────────────────────────────────────────────────────
# Jobs list / detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/text/message-jobs")
async def list_message_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    q = MessageJob.filter(user=user).order_by("-created_at")
    if status:
        q = q.filter(status=status)
    total = await q.count()
    rows = await q.offset(offset).limit(limit)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(j.id),
                "status": j.status,
                "from_number": j.from_number,
                "assistant_id": j.assistant_id,
                "total": j.total,
                "sent": j.sent,
                "failed": j.failed,
                "created_at": j.created_at,
            }
            for j in rows
        ],
    }

@router.get("/text/message-job/{job_id}")
async def get_message_job(job_id: str, user: Annotated[User, Depends(get_current_user)] = None):
    job = await MessageJob.get_or_none(id=job_id, user=user)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    success_count = await MessageRecord.filter(job=job, success=True).count()
    fail_count = await MessageRecord.filter(job=job, success=False).count()
    return {
        "id": str(job.id),
        "status": job.status,
        "from_number": job.from_number,
        "assistant_id": job.assistant_id,
        "total": job.total,
        "sent": job.sent,
        "failed": job.failed,
        "success_count": success_count,
        "fail_count": fail_count,
        "created_at": job.created_at,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Assistants
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/text-assistants")
async def create_text_assistant(assistant: TextAssistantCreate, user: Annotated[User, Depends(get_current_user)]):
    try:
        required_fields = ['name', 'provider', 'model', 'system_prompt']
        empty_fields = [field for field in required_fields if not getattr(assistant, field, None)]
        if empty_fields:
            raise HTTPException(status_code=400, detail=f"All fields are required. Empty fields: {', '.join(empty_fields)}")

        new_assistant = await Assistant.create(
            user=user,
            name=assistant.name,
            provider=assistant.provider,
            model=assistant.model,
            voice_provider=assistant.voice_provider,
            voice=assistant.voice,
            systemPrompt=assistant.system_prompt,
            languages=[assistant.language] if assistant.language else None,
            first_message="",
            forwardingPhoneNumber=assistant.forwardingPhoneNumber,
            assistant_toggle=assistant.assistant_toggle,
        )

        return {
            "success": True,
            "id": new_assistant.id,
            "name": new_assistant.name,
            "detail": "Text assistant created successfully."
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred while creating the assistant: {str(e)}")

@router.get("/text-assistants")
async def get_all_text_assistants(user: Annotated[User, Depends(get_current_user)]):
    try:
        assistants = await Assistant.filter(user=user).all()
        if not assistants:
            return []
        return [
            {
                "id": a.id,
                "name": a.name,
                "provider": a.provider,
                "model": a.model,
                "languages": a.languages,
                "voice_provider": a.voice_provider,
                "voice": a.voice,
                "system_prompt": a.systemPrompt,
                "assistant_toggle": a.assistant_toggle,
            }
            for a in assistants
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching assistants: {str(e)}")

@router.put("/toggle-text-assistant/{assistant_id}")
async def toggle_text_assistant(assistant_id: int, assistant_toggle: bool, user: Annotated[User, Depends(get_current_user)]):
    try:
        assistant = await Assistant.get_or_none(id=assistant_id, user=user)
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")
        assistant.assistant_toggle = assistant_toggle
        await assistant.save()
        return {
            "success": True,
            "assistant_id": assistant.id,
            "assistant_toggle": assistant.assistant_toggle,
            "detail": "Text assistant toggle updated successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error toggling assistant: {str(e)}")

@router.post("/text/attach-assistant")
async def attach_assistant_to_number(payload: AttachAssistantRequest, user: Annotated[User, Depends(get_current_user)]):
    try:
        row = await PurchasedNumber.get_or_none(user=user, phone_number=payload.phone_number)
        if not row:
            raise HTTPException(status_code=404, detail="Purchased number not found")

        if payload.assistant_id:
            assistant = await Assistant.get_or_none(id=payload.assistant_id, user=user)
            if not assistant:
                raise HTTPException(status_code=404, detail="Assistant not found")
            row.attached_assistant = assistant.id
        else:
            row.attached_assistant = None
        await row.save()
        return {
            "success": True,
            "phone_number": row.phone_number,
            "attached_assistant": row.attached_assistant,
            "kind": payload.kind
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error attaching assistant: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Send (single) + Status callback
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/send-text-message")
async def send_text_message(
    request: Request,
    payload: TextMessageRequest,
    user: Annotated[User, Depends(get_current_user)]
):
    try:
        db_user = await User.get(id=user.id)
        client, _, _ = _twilio_client_for_user_sync(db_user)
        # choose sender with helper (prefers attached by assistant if provided later)
        from_row = await _resolve_from_number(db_user, None, payload.from_number)

        status_cb = _build_status_callback_url(request, payload.status_webhook)

        logger.info(f"[send] to={_sanitize_phone(payload.to_number)} from={_sanitize_phone(from_row.phone_number)}")
        msg = await _twilio_send_message(
            client=client,
            body=(payload.body or "")[:1000],
            from_number=_sanitize_phone(from_row.phone_number),
            to_number=_sanitize_phone(payload.to_number),
            status_callback=status_cb,
        )

        # Persist as an outbound record
        await _store_record_outbound(
            job=None,
            user=db_user,
            assistant=None,
            appointment=None,
            to_number=payload.to_number,
            from_number=from_row.phone_number,
            body=payload.body,
            sid=getattr(msg, "sid", None),
            success=True,
        )

        return {
            "success": True,
            "message_sid": getattr(msg, "sid", None),
            "detail": "Message sent successfully."
        }
    except TwilioRestException as e:
        # Surface Twilio details to aid debugging
        detail = {
            "message": getattr(e, "msg", str(e)),
            "status": getattr(e, "status", None),
            "code": getattr(e, "code", None),
            "more_info": getattr(e, "more_info", None),
        }
        logger.error(f"[send] twilio_error to={_sanitize_phone(payload.to_number)} code={detail['code']} status={detail['status']} msg={detail['message']}")
        raise HTTPException(status_code=400, detail={"twilio_error": detail})
    except HTTPException:
        # Preserve explicit HTTPException (e.g., bad from_number, no purchased number)
        raise
    except Exception as e:
        logger.exception(f"[send] unexpected_error to={_sanitize_phone(payload.to_number)}: {e}")
        raise HTTPException(status_code=400, detail=f"Error sending message: {str(e)}")

@router.post("/text/sms-status")
async def twilio_status_webhook(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
):
    """
    Twilio calls this to update delivery status.
    We only have `success` and `error` fields — map basic states.
    """
    rec = await MessageRecord.get_or_none(sid=MessageSid)
    if not rec:
        return {"ok": True}  # nothing to update
    if MessageStatus in ("delivered", "sent", "queued"):
        rec.success = True
        rec.error = None
    elif MessageStatus in ("failed", "undelivered"):
        rec.success = False
        rec.error = MessageStatus
    await rec.save()
    return {"ok": True}

# ─────────────────────────────────────────────────────────────────────────────
# Inbound webhook → log + AI auto-reply + log reply
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/text/sms-webhook")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(alias="From"),
    To: str = Form(alias="To"),
    Body: str = Form(alias="Body"),
    MessageSid: Optional[str] = Form(default=None, alias="MessageSid"),
):
    try:
        # Optional: validate signature first
        form_dict = {"From": From, "To": To, "Body": Body or ""}
        if MessageSid:
            form_dict["MessageSid"] = MessageSid
        if not _validate_twilio_signature(request, form_dict):
            return {"success": False, "error": "twilio_signature_invalid"}

        # Which purchased number received it?
        to_row = await PurchasedNumber.filter(phone_number=To).first()
        if not to_row:
            return {"status": "ignored"}  # unknown number

        # Owner user + Twilio client
        user = await User.get(id=to_row.user_id)
        client, _, _ = _twilio_client_for_user_sync(user)

        logger.info(f"[inbound] to={_sanitize_phone(To)} from={_sanitize_phone(From)}")
        # Log inbound first
        await _store_record_inbound(
            user=user,
            purchased_to=To,
            from_external=From,
            body=Body or "",
            sid=MessageSid,
            ok=True,
        )

        # Choose assistant: number-attached → toggle fallback
        assistant = None
        if to_row.attached_assistant:
            assistant = await Assistant.get_or_none(id=to_row.attached_assistant, user=user)
        if not assistant:
            assistant = await Assistant.filter(user=user, assistant_toggle=True).first()

        # If no assistant, echo back polite message
        if not assistant:
            msg_text = Body or "Thanks for your message."
            await _twilio_send_message(client, msg_text, To, From, None)
            await _store_record_outbound(
                job=None, user=user, assistant=None, appointment=None,
                to_number=From, from_number=To, body=msg_text, sid=None, success=True
            )
            return {"status": "echoed"}

        system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful SMS assistant. Keep replies short and useful."
        generated = await _generate_via_vapi_or_openai(system_prompt, Body or "", user=user)
        reply_text = generated or "Thanks for your message. We'll get back to you shortly."

        status_cb = _build_status_callback_url(request)
        msg = await _twilio_send_message(client, reply_text[:1000], To, From, status_cb)

        # Log AI reply
        await _store_record_outbound(
            job=None, user=user, assistant=assistant, appointment=None,
            to_number=From, from_number=To, body=reply_text, sid=getattr(msg, "sid", None), success=True
        )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[inbound] error to={_sanitize_phone(To)} from={_sanitize_phone(From)}: {e}")
        return {"success": False, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# BULK: Scheduled vs. Unscheduled
# ─────────────────────────────────────────────────────────────────────────────

async def _bulk_message_appointments_core(
    *,
    db_user: User,
    request: Request,
    assistant: Assistant,
    from_row: PurchasedNumber,
    appointments: List[Appointment],
    job: Optional[MessageJob] = None,   # allow caller to pre-create job for SSE
    messages_per_recipient: int = 1,
    retry_count: int = 0,
    retry_delay_seconds: int = 60,
    per_message_delay_seconds: int = 0,
) -> str:
    client, _, _ = _twilio_client_for_user_sync(db_user)
    system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful SMS assistant. Keep replies short and useful."

    total_attempts = len(appointments) * max(1, messages_per_recipient) * (1 + max(0, retry_count))
    if job is None:
        job = await MessageJob.create(
            user=db_user,
            assistant=assistant,
            from_number=from_row.phone_number,
            status="running",
            total=total_attempts,
            sent=0,
            failed=0,
        )
    else:
        job.total = total_attempts
        job.status = "running"
        job.sent = job.sent or 0
        job.failed = job.failed or 0
        await job.save()

    status_cb = _build_status_callback_url(request)

    for appt in appointments:
        # Dedupe by appointment unless explicitly allowed to repeat
        if not (getattr(request, "allow_repeat_to_same_number", False)):
            already = await MessageRecord.filter(appointment=appt, success=True).exists()
            if already:
                continue

        a = await _prefer_assistant_for_appt(db_user.id, appt, assistant)

        user_message = (
            f"Create a friendly, concise SMS to the customer about their appointment. "
            f"Include title '{appt.title}', time {appt.start_at.isoformat()} ({appt.timezone}), "
            f"and brief next step. Ask to reply YES to confirm or NO to reschedule."
        )
        generated = await _generate_via_vapi_or_openai(
            system_prompt if not a else getattr(a, "systemPrompt", system_prompt),
            user_message,
            db_user
        ) or (
            f"Hi! Reminder for '{appt.title}' on {appt.start_at.isoformat()} ({appt.timezone}). "
            f"Reply YES to confirm or NO to reschedule."
        )

        # For each recipient, send messages_per_recipient times, with retries for each attempt
        for msg_index in range(max(1, messages_per_recipient)):
            attempt_body = generated[:1000]
            attempts_remaining = 1 + max(0, retry_count)
            while attempts_remaining > 0:
                try:
                    logger.info(f"[bulk] send attempt job_id={job.id} to={_sanitize_phone(appt.phone)} msg_ix={msg_index} remaining={attempts_remaining}")
                    msg = await _twilio_send_message(
                        client=client,
                        body=attempt_body,
                        from_number=from_row.phone_number,
                        to_number=appt.phone,
                        status_callback=status_cb,
                    )
                    await _store_record_outbound(
                        job=job, user=db_user, assistant=a or assistant, appointment=appt,
                        to_number=appt.phone, from_number=from_row.phone_number, body=attempt_body, sid=getattr(msg, "sid", None), success=True
                    )
                    job.sent += 1
                    break
                except Exception as e:
                    logger.error(f"[bulk] send failed job_id={job.id} to={_sanitize_phone(appt.phone)} err={e}")
                    await _store_record_outbound(
                        job=job, user=db_user, assistant=a or assistant, appointment=appt,
                        to_number=appt.phone, from_number=from_row.phone_number, body=attempt_body, sid=None, success=False, error=str(e)
                    )
                    job.failed += 1
                    attempts_remaining -= 1
                    if attempts_remaining > 0:
                        logger.info(f"[bulk] retrying in {retry_delay_seconds}s job_id={job.id} to={_sanitize_phone(appt.phone)}")
                        await asyncio.sleep(max(0, retry_delay_seconds))
            # optional delay between multiple messages to same recipient
            if per_message_delay_seconds and msg_index < max(1, messages_per_recipient) - 1:
                logger.info(f"[bulk] pause between messages {per_message_delay_seconds}s job_id={job.id} to={_sanitize_phone(appt.phone)}")
                await asyncio.sleep(max(0, per_message_delay_seconds))

    job.status = "completed"
    await job.save()
    return str(job.id)

async def _resolve_from_number(db_user: User, assistant: Optional[Assistant], explicit_from: Optional[str]) -> PurchasedNumber:
    if explicit_from:
        row = await PurchasedNumber.filter(user=db_user, phone_number=explicit_from).first()
        if not row:
            raise HTTPException(status_code=400, detail="Provided from_number is not one of user's purchased numbers.")
        return row
    if assistant:
        row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first()
        if row:
            return row
    row = await PurchasedNumber.filter(user=db_user).first()
    if not row:
        raise HTTPException(status_code=400, detail="No purchased phone number available.")
    return row

@router.post("/text/message-scheduled")
async def message_scheduled_appointments(
    request: Request,
    payload: MessageScheduledRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        db_user = await User.get(id=user.id)
        # choose assistant
        if payload.assistant_id:
            assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
            if not assistant:
                raise HTTPException(status_code=404, detail="Assistant not found")
        else:
            assistant = await _pick_assistant_for_flow(db_user, "scheduled")
            if not assistant:
                raise HTTPException(status_code=404, detail="No enabled assistant found")
        from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

        # pull appointments and restrict to upcoming window
        # Optionally include unowned (user_id is null) to handle legacy data
        if payload.include_unowned:
            appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
                Q(user=db_user) | Q(user_id=None)
            )
        else:
            appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED)
        appts = [a for a in appts_all if _in_scheduled_window(a, horizon_hours=payload.horizon_hours, include_past_minutes=payload.include_past_minutes or 0)]
        if payload.limit and payload.limit > 0:
            appts = appts[: payload.limit]

        if not appts:
            total_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).count()
            total_user = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).count()
            return {
                "success": True,
                "sent": 0,
                "results": [],
                "detail": "No appointments matched filters",
                "stats": {
                    "total_scheduled_all": total_all,
                    "total_scheduled_for_user": total_user,
                    "include_unowned": bool(payload.include_unowned),
                    "horizon_hours": payload.horizon_hours if payload.horizon_hours is not None else os.getenv("SCHEDULED_HORIZON_HOURS", "48"),
                    "include_past_minutes": payload.include_past_minutes or 0,
                }
            }

        if payload.background is False:
            job_id = await _bulk_message_appointments_core(
                db_user=db_user,
                request=request,
                assistant=assistant,
                from_row=from_row,
                appointments=appts,
                messages_per_recipient=payload.messages_per_recipient or 1,
                retry_count=payload.retry_count or 0,
                retry_delay_seconds=payload.retry_delay_seconds or 60,
                per_message_delay_seconds=payload.per_message_delay_seconds or 0,
            )
            return {"success": True, "job_id": job_id}
        else:
            # pre-create job so UI can subscribe immediately
            pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
            job = await MessageJob.create(
                user=db_user, assistant=assistant, from_number=from_row.phone_number,
                status="running", total=pre_total, sent=0, failed=0
            )
            background_tasks.add_task(
                _bulk_message_appointments_core,
                db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts, job=job,
                messages_per_recipient=payload.messages_per_recipient or 1,
                retry_count=payload.retry_count or 0,
                retry_delay_seconds=payload.retry_delay_seconds or 60,
                per_message_delay_seconds=payload.per_message_delay_seconds or 0,
            )
            sse_token = _make_sse_token(db_user.id, str(job.id))
            return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started. Subscribe via /text/message-progress-sse"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error messaging scheduled appointments: {str(e)}")

@router.post("/text/message-unscheduled")
async def message_unscheduled_appointments(
    request: Request,
    payload: MessageScheduledRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Treat UNSCHEDULED as any appointment that's NOT SCHEDULED.
    """
    try:
        db_user = await User.get(id=user.id)
        if payload.assistant_id:
            assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
            if not assistant:
                raise HTTPException(status_code=404, detail="Assistant not found")
        else:
            assistant = await _pick_assistant_for_flow(db_user, "unscheduled")
            if not assistant:
                raise HTTPException(status_code=404, detail="No enabled assistant found")
        from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

        appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED)
        # dedup + optional backoff per phone
        try:
            backoff_h = (
                payload.unscheduled_backoff_hours
                if payload.unscheduled_backoff_hours is not None
                else int(os.getenv("UNSCHEDULED_BACKOFF_HOURS", "0"))
            )
        except Exception:
            backoff_h = 0

        filtered: List[Appointment] = []
        for a in appts_all:
            if not (payload.allow_repeat_to_same_number or False):
                if await MessageRecord.filter(appointment=a, success=True).exists():
                    continue
            if backoff_h > 0 and not await _unscheduled_backoff_ok_async(a.phone, db_user, backoff_h):
                continue
            filtered.append(a)
        appts = filtered

        if payload.limit and payload.limit > 0:
            appts = appts[: payload.limit]

        if not appts:
            return {"success": True, "sent": 0, "results": []}

        if payload.background is False:
            job_id = await _bulk_message_appointments_core(
                db_user=db_user,
                request=request,
                assistant=assistant,
                from_row=from_row,
                appointments=appts,
                messages_per_recipient=payload.messages_per_recipient or 1,
                retry_count=payload.retry_count or 0,
                retry_delay_seconds=payload.retry_delay_seconds or 60,
                per_message_delay_seconds=payload.per_message_delay_seconds or 0,
            )
            return {"success": True, "job_id": job_id}
        else:
            pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
            job = await MessageJob.create(
                user=db_user, assistant=assistant, from_number=from_row.phone_number,
                status="running", total=pre_total, sent=0, failed=0
            )
            background_tasks.add_task(
                _bulk_message_appointments_core,
                db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts, job=job,
                messages_per_recipient=payload.messages_per_recipient or 1,
                retry_count=payload.retry_count or 0,
                retry_delay_seconds=payload.retry_delay_seconds or 60,
                per_message_delay_seconds=payload.per_message_delay_seconds or 0,
            )
            sse_token = _make_sse_token(db_user.id, str(job.id))
            return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started. Subscribe via /text/message-progress-sse"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error messaging unscheduled appointments: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Scheduler (scheduled + unscheduled)
# ─────────────────────────────────────────────────────────────────────────────

async def _send_scheduled_for_user(user_id: int, request: Optional[Request] = None):
    db_user = await User.get(id=user_id)
    assistant = await _pick_assistant_for_flow(db_user, "scheduled")
    if not assistant:
        return
    from_row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first() \
               or await PurchasedNumber.filter(user=db_user).first()
    if not from_row:
        return
    include_unowned = _env_bool("SCHEDULED_INCLUDE_UNOWNED", False)
    include_past_min = 0
    try:
        include_past_min = int(os.getenv("SCHEDULED_INCLUDE_PAST_MINUTES", "0"))
    except Exception:
        include_past_min = 0
    if include_unowned:
        appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
            Q(user=db_user) | Q(user_id=None)
        ).all()
    else:
        appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).all()
    appts = [a for a in appts_all if _in_scheduled_window(a, include_past_minutes=include_past_min)]
    if not appts:
        return
    class _DummyReq:
        base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    # Allow scheduler to control dedupe via env
    setattr(_DummyReq, "allow_repeat_to_same_number", _env_bool("ALLOW_REPEAT_TO_SAME_NUMBER", True))
    dummy_req = request or _DummyReq()
    await _bulk_message_appointments_core(
        db_user=db_user, request=dummy_req, assistant=assistant, from_row=from_row, appointments=appts
    )

async def run_texting_job():
    user_ids = await Appointment.filter(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
    seen = set()
    for uid in user_ids:
        if uid and uid not in seen:
            seen.add(uid)
            try:
                await _send_scheduled_for_user(uid)
            except Exception:
                continue

async def run_unscheduled_texting_job():
    user_ids = await Appointment.exclude(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
    seen = set()
    for uid in user_ids:
        if uid and uid not in seen:
            seen.add(uid)
            try:
                db_user = await User.get(id=uid)
                assistant = await _pick_assistant_for_flow(db_user, "unscheduled")
                if not assistant:
                    continue
                from_row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first() \
                           or await PurchasedNumber.filter(user=db_user).first()
                if not from_row:
                    continue
                class _DummyReq:
                    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
                dummy_req = _DummyReq()
                setattr(dummy_req, "allow_repeat_to_same_number", _env_bool("ALLOW_REPEAT_TO_SAME_NUMBER", True))
                appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED)
                try:
                    backoff_h = int(os.getenv("UNSCHEDULED_BACKOFF_HOURS", "0"))
                except Exception:
                    backoff_h = 0
                filtered: List[Appointment] = []
                async for a in appts_all:  # in case QuerySet is async-iterable
                    if not _env_bool("ALLOW_REPEAT_TO_SAME_NUMBER", True):
                        if await MessageRecord.filter(appointment=a, success=True).exists():
                            continue
                    if backoff_h > 0 and not await _unscheduled_backoff_ok_async(a.phone, db_user, backoff_h):
                        continue
                    filtered.append(a)
                if filtered:
                    await _bulk_message_appointments_core(
                        db_user=db_user, request=dummy_req, assistant=assistant, from_row=from_row, appointments=filtered
                    )
            except Exception:
                continue

def schedule_texting_job(timezone: str = "UTC"):
    # Every minute for scheduled (upcoming within window)
    schedule_minutely_job("texting-scheduled-appointments", timezone, run_texting_job)
    # Also scan unscheduled periodically (you can adjust cadence inside your scheduler if supported)
    schedule_minutely_job("texting-unscheduled-appointments", timezone, run_unscheduled_texting_job)
    # Nudge once shortly after startup
    nudge_once(run_texting_job, delay_seconds=3)
