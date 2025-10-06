# from datetime import datetime, timedelta, timezone
# from zoneinfo import ZoneInfo
# import asyncio
# import json
# import os
# from typing import Annotated, List, Optional, Tuple, Dict, Any, AsyncGenerator, Literal
# from urllib.parse import urlparse

# from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Form, Query
# import logging
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel, Field
# from starlette.concurrency import run_in_threadpool

# import httpx
# from twilio.rest import Client
# from twilio.request_validator import RequestValidator
# from twilio.base.exceptions import TwilioRestException

# from tortoise.expressions import Q

# from helpers.token_helper import get_current_user, decode_user_token, generate_user_token
# from helpers.vapi_helper import get_headers  # optional VAPI
# from models.auth import User
# from models.purchased_numbers import PurchasedNumber
# from models.assistant import Assistant
# from models.appointment import Appointment, AppointmentStatus
# from models.message import MessageJob, MessageRecord
# from scheduler.campaign_scheduler import schedule_minutely_job, nudge_once

# # ─────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ─────────────────────────────────────────────────────────────────────────────

# class TextMessageRequest(BaseModel):
#     to_number: str
#     body: str
#     from_number: Optional[str] = None
#     status_webhook: Optional[str] = None

# class TextAssistantCreate(BaseModel):
#     name: str
#     provider: str
#     model: str
#     voice_provider: Optional[str] = None
#     voice: Optional[str] = None
#     system_prompt: str
#     language: Optional[str] = None
#     forwardingPhoneNumber: Optional[str] = None
#     assistant_toggle: Optional[bool] = True

# class MessageScheduledRequest(BaseModel):
#     assistant_id: Optional[int] = None
#     from_number: Optional[str] = None
#     limit: Optional[int] = None
#     background: Optional[bool] = True

#     # send/retry knobs
#     messages_per_recipient: Optional[int] = Field(default=1, ge=1, le=10)
#     retry_count: Optional[int] = Field(default=0, ge=0, le=5)
#     retry_delay_seconds: Optional[int] = Field(default=60, ge=5, le=3600)
#     per_message_delay_seconds: Optional[int] = Field(default=0, ge=0, le=3600)

#     # scheduled-selection knobs
#     include_unowned: Optional[bool] = Field(default=True, description="Include appts with null user_id")
#     # backoff (Scheduled logic ONLY uses this)
#     repeat_backoff_hours: Optional[int] = Field(default=None, description="Default 7 (via REPEAT_BACKOFF_HOURS if set)")

#     # unscheduled backoff (only for unscheduled endpoint)
#     unscheduled_backoff_hours: Optional[int] = Field(default=None)

# class AttachAssistantRequest(BaseModel):
#     phone_number: str
#     assistant_id: Optional[int] = None
#     kind: Optional[str] = Field(default=None, description="scheduled|unscheduled (advisory only)")

# # === NEW: Daemon config/state schemas
# Kind = Literal["scheduled", "unscheduled"]

# class DaemonConfigRequest(BaseModel):
#     kind: Kind
#     enabled: Optional[bool] = None
#     tick_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
#     include_unowned: Optional[bool] = None  # scheduled only
#     repeat_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)  # scheduled
#     unscheduled_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)

# # ─────────────────────────────────────────────────────────────────────────────
# # Router / logger
# # ─────────────────────────────────────────────────────────────────────────────

# router = APIRouter()
# logger = logging.getLogger("text_assistant")
# if not logger.handlers:
#     handler = logging.StreamHandler()
#     handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
#     logger.addHandler(handler)
# logger.setLevel(logging.INFO)

# # ─────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────────────────────────────────────

# def _env_bool(name: str, default: bool = False) -> bool:
#     v = os.getenv(name)
#     if v is None:
#         return default
#     return str(v).strip().lower() in ("1", "true", "y", "yes", "on")

# def _env_int(name: str, default: int) -> int:
#     try:
#         return int(os.getenv(name, str(default)))
#     except Exception:
#         return default

# def _sanitize_phone(s: Optional[str]) -> str:
#     return (s or "").strip()

# def _twilio_client_from_values(account_sid: Optional[str], auth_token: Optional[str]) -> Tuple[Client, str, str]:
#     sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
#     token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
#     if not sid or not token:
#         raise HTTPException(status_code=400, detail="No Twilio credentials found. Set via POST /twilio/credentials.")
#     return Client(sid, token), sid, token

# def _twilio_client_for_user_sync(user: User) -> Tuple[Client, str, str]:
#     return _twilio_client_from_values(
#         getattr(user, "twilio_account_sid", None),
#         getattr(user, "twilio_auth_token", None),
#     )

# def _build_status_callback_url(request: Request, override_url: Optional[str] = None) -> Optional[str]:
#     """Return a public StatusCallback URL or None (if localhost)."""
#     def _is_public(u: str) -> bool:
#         try:
#             p = urlparse(u)
#             if p.scheme not in ("http", "https"): return False
#             if not p.netloc: return False
#             host = p.hostname or ""
#             if host in ("localhost", "127.0.0.1", "::1"): return False
#             return True
#         except Exception:
#             return False

#     if override_url and _is_public(override_url):
#         return override_url

#     base = os.getenv("PUBLIC_BASE_URL")
#     if not base:
#         return None
#     candidate = f"{base.rstrip('/')}/api/text/sms-status"
#     return candidate if _is_public(candidate) else None

# async def _generate_via_vapi_or_openai(system_prompt: str, user_message: str, user: Optional[User] = None) -> Optional[str]:
#     vapi_url = os.getenv("VAPI_URL")
#     if vapi_url:
#         try:
#             headers = get_headers(user=user)
#             async with httpx.AsyncClient(timeout=30) as client:
#                 res = await client.post(
#                     f"{vapi_url.rstrip('/')}/v1/chat/completions",
#                     headers=headers,
#                     json={
#                         "model": os.getenv("VAPI_MODEL", "gpt-4o-mini"),
#                         "temperature": 0.4,
#                         "messages": [
#                             {"role": "system", "content": system_prompt},
#                             {"role": "user", "content": user_message},
#                         ],
#                     },
#                 )
#                 res.raise_for_status()
#                 data = res.json()
#                 text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
#                 if text:
#                     return text
#         except Exception:
#             pass
#     # fallback to OpenAI
#     try:
#         api_key = os.getenv("OPENAI_API_KEY")
#         if not api_key:
#             return None
#         try:
#             from openai import OpenAI  # type: ignore
#             client = OpenAI(api_key=api_key)
#             resp = client.chat.completions.create(
#                 model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
#                 temperature=0.4,
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_message},
#                 ],
#             )
#             return (resp.choices[0].message.content or "").strip()
#         except Exception:
#             import openai  # type: ignore
#             openai.api_key = api_key
#             resp = openai.ChatCompletion.create(
#                 model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
#                 temperature=0.4,
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_message},
#                 ],
#             )
#             return (resp["choices"][0]["message"]["content"] or "").strip()
#     except Exception:
#         return None

# async def _twilio_send_message(
#     client: Client,
#     body: str,
#     from_number: str,
#     to_number: str,
#     status_callback: Optional[str] = None,
# ) -> Any:
#     def _send():
#         return client.messages.create(
#             body=body,
#             from_=from_number,
#             to=to_number,
#             status_callback=status_callback if status_callback else None,
#         )
#     return await run_in_threadpool(_send)

# async def _store_record_outbound(
#     *,
#     job: Optional[MessageJob],
#     user: User,
#     assistant: Optional[Assistant],
#     appointment: Optional[Appointment],
#     to_number: str,
#     from_number: str,
#     body: str,
#     sid: Optional[str],
#     success: bool,
#     error: Optional[str] = None,
# ):
#     if job is None:
#         job = await MessageJob.create(
#             user=user,
#             assistant=assistant,
#             from_number=from_number,
#             status="completed",
#             total=1,
#             sent=1 if success else 0,
#             failed=0 if success else 1,
#         )
#     await MessageRecord.create(
#         job=job,
#         user=user,
#         assistant=assistant,
#         appointment=appointment,
#         to_number=to_number,
#         from_number=from_number,
#         body=(body or "")[:1000],
#         sid=sid,
#         success=success,
#         error=error,
#     )

# async def _store_record_inbound(
#     *,
#     user: User,
#     purchased_to: str,
#     from_external: str,
#     body: str,
#     sid: Optional[str],
#     ok: bool = True,
#     error: Optional[str] = None,
# ):
#     job = await MessageJob.create(
#         user=user,
#         assistant=None,
#         from_number=purchased_to,
#         status="completed",
#         total=1,
#         sent=1 if ok else 0,
#         failed=0 if ok else 1,
#     )
#     await MessageRecord.create(
#         job=job,
#         user=user,
#         assistant=None,
#         appointment=None,
#         to_number=purchased_to,
#         from_number=from_external,
#         body=(body or "")[:1000],
#         sid=sid,
#         success=ok,
#         error=error,
#     )

# # ─────────────────────────────────────────────────────────────────────────────
# # Backoff logic (the ONLY gate for SCHEDULED selection)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _recent_success_outbound_exists(phone: str, user: User, within_hours: int) -> bool:
#     if not phone:
#         return False
#     since = datetime.now(timezone.utc) - timedelta(hours=max(0, within_hours))
#     return await MessageRecord.filter(
#         user=user, to_number=phone, success=True, created_at__gte=since
#     ).exists()

# async def _eligible_scheduled_appointments(
#     *,
#     db_user: User,
#     include_unowned: bool,
#     backoff_hours: int,
# ) -> List[Appointment]:
#     if include_unowned:
#         appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
#             Q(user=db_user) | Q(user_id=None)
#         ).all()
#     else:
#         appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).all()

#     result: List[Appointment] = []
#     for a in appts_all:
#         already = await _recent_success_outbound_exists(a.phone, db_user, backoff_hours)
#         if already:
#             continue
#         result.append(a)
#     return result

# # ─────────────────────────────────────────────────────────────────────────────
# # SSE progress (per-job, existing)
# # ─────────────────────────────────────────────────────────────────────────────

# def _make_sse_token(user_id: int, job_id: str, ttl_seconds: int = 600) -> str:
#     exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
#     payload = {"id": user_id, "job_id": job_id, "kind": "sse", "exp": exp}
#     return generate_user_token(payload)

# def _validate_sse_token(token: str, expected_job_id: str) -> Optional[int]:
#     try:
#         claims = decode_user_token(token)
#         if not isinstance(claims, dict): return None
#         if claims.get("kind") != "sse": return None
#         if claims.get("job_id") != expected_job_id: return None
#         uid = claims.get("id")
#         return uid if isinstance(uid, int) else None
#     except Exception:
#         return None

# @router.get("/text/message-progress")
# async def get_message_progress(
#     job_id: Optional[str] = None,
#     user: Annotated[User, Depends(get_current_user)] = None
# ):
#     job = await (MessageJob.filter(user=user).order_by("-created_at").first() if not job_id
#                 else MessageJob.get_or_none(id=job_id, user=user))
#     if not job:
#         return {"success": True, "found": False}
#     return {
#         "success": True,
#         "found": True,
#         "job": {
#             "id": str(job.id),
#             "status": job.status,
#             "from_number": job.from_number,
#             "assistant_id": job.assistant_id,
#             "total": job.total,
#             "sent": job.sent,
#             "failed": job.failed,
#             "created_at": job.created_at,
#         }
#     }

# @router.get("/text/message-progress-sse")
# async def stream_message_progress_sse(
#     request: Request,
#     job_id: str = Query(...),
#     token: Optional[str] = Query(default=None),
#     sse: Optional[str] = Query(default=None)
# ):
#     auth_user: Optional[User] = None
#     try:
#         if sse:
#             uid = _validate_sse_token(sse, job_id)
#             if uid is not None:
#                 auth_user = await User.get_or_none(id=uid)
#         if not auth_user:
#             auth_header = request.headers.get("Authorization")
#             raw = None
#             if auth_header and auth_header.lower().startswith("bearer "):
#                 raw = auth_header.split(" ", 1)[1]
#             elif token:
#                 raw = token
#             else:
#                 raw = request.cookies.get("token") or request.cookies.get("access_token") or request.cookies.get("Authorization")
#             if raw:
#                 creds = decode_user_token(raw)
#                 uid = creds.get("id") if isinstance(creds, dict) else None
#                 if uid is not None:
#                     auth_user = await User.get_or_none(id=uid)
#     except Exception:
#         auth_user = None

#     if not auth_user:
#         raise HTTPException(status_code=403, detail="Not authenticated")

#     async def event_stream() -> AsyncGenerator[bytes, None]:
#         last: Dict[str, Any] = {}
#         while True:
#             if await request.is_disconnected():
#                 break
#             job = await MessageJob.get_or_none(id=job_id, user=auth_user)
#             if not job:
#                 yield b"event: done\ndata: {\"error\":\"not_found\"}\n\n"
#                 break
#             payload = {
#                 "id": str(job.id),
#                 "status": job.status,
#                 "total": job.total,
#                 "sent": job.sent,
#                 "failed": job.failed,
#                 "from_number": job.from_number,
#                 "assistant_id": job.assistant_id,
#                 "created_at": job.created_at.isoformat() if job.created_at else None,
#             }
#             if payload != last:
#                 yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
#                 last = payload
#             if job.status in ("completed", "failed", "canceled"):
#                 yield b"event: done\ndata: {}\n\n"
#                 break
#             await asyncio.sleep(1.0)

#     headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream", "Connection": "keep-alive"}
#     return StreamingResponse(event_stream(), headers=headers)

# # ─────────────────────────────────────────────────────────────────────────────
# # Messages / Threads / Jobs (unchanged)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.get("/text/messages")
# async def list_messages(
#     limit: int = 100,
#     offset: int = 0,
#     success: Optional[bool] = None,
#     job_id: Optional[str] = None,
#     assistant_id: Optional[int] = None,
#     to_like: Optional[str] = None,
#     from_like: Optional[str] = None,
#     start: Optional[str] = None,
#     end: Optional[str] = None,
#     peer_number: Optional[str] = None,
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     q = MessageRecord.filter(user=user).order_by("-created_at")
#     if success is not None: q = q.filter(success=success)
#     if job_id: q = q.filter(job_id=job_id)
#     if assistant_id: q = q.filter(assistant_id=assistant_id)
#     if to_like: q = q.filter(to_number__icontains=to_like)
#     if from_like: q = q.filter(from_number__icontains=from_like)
#     if start:
#         try:
#             q = q.filter(created_at__gte=datetime.fromisoformat(start))
#         except Exception:
#             pass
#     if end:
#         try:
#             q = q.filter(created_at__lte=datetime.fromisoformat(end))
#         except Exception:
#             pass
#     if peer_number:
#         q = q.filter(Q(to_number__icontains=peer_number) | Q(from_number__icontains=peer_number))

#     total = await q.count()
#     purchased_set = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))
#     rows = await q.offset(offset).limit(limit)
#     def _direction(r) -> str:
#         return "inbound" if r.to_number in purchased_set else "outbound"

#     return {
#         "total": total,
#         "limit": limit,
#         "offset": offset,
#         "items": [
#             {
#                 "id": r.id,
#                 "job_id": str(r.job_id) if r.job_id else None,
#                 "assistant_id": r.assistant_id,
#                 "appointment_id": str(r.appointment_id) if r.appointment_id else None,
#                 "from_number": r.from_number,
#                 "to_number": r.to_number,
#                 "sid": r.sid,
#                 "success": r.success,
#                 "error": r.error,
#                 "body": r.body,
#                 "created_at": r.created_at,
#                 "direction": _direction(r),
#             } for r in rows
#         ],
#     }

# @router.get("/text/threads")
# async def list_threads(
#     limit: int = 50,
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     purchased = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))
#     rows = await MessageRecord.filter(user=user).order_by("-created_at").limit(1000)
#     threads: Dict[str, Dict[str, Any]] = {}
#     for r in rows:
#         a, b = r.from_number, r.to_number
#         if a in purchased and b not in purchased:
#             peer, mynum = b, a
#         elif b in purchased and a not in purchased:
#             peer, mynum = a, b
#         else:
#             continue
#         t = threads.get(peer)
#         if not t:
#             threads[peer] = {
#                 "peer_number": peer,
#                 "my_number": mynum,
#                 "last_message_at": r.created_at,
#                 "last_body": r.body,
#                 "last_direction": "inbound" if r.to_number in purchased else "outbound",
#                 "count": 1,
#             }
#         else:
#             t["count"] += 1
#             if r.created_at and (t["last_message_at"] is None or r.created_at > t["last_message_at"]):
#                 t["last_message_at"] = r.created_at
#                 t["last_body"] = r.body
#                 t["last_direction"] = "inbound" if r.to_number in purchased else "outbound"
#     items = sorted(threads.values(), key=lambda x: (x["last_message_at"] or datetime.min), reverse=True)[:limit]
#     return {"items": items, "total": len(items)}

# @router.get("/text/message-jobs")
# async def list_message_jobs(
#     limit: int = 50,
#     offset: int = 0,
#     status: Optional[str] = None,
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     q = MessageJob.filter(user=user).order_by("-created_at")
#     if status: q = q.filter(status=status)
#     total = await q.count()
#     rows = await q.offset(offset).limit(limit)
#     return {
#         "total": total,
#         "limit": limit,
#         "offset": offset,
#         "items": [
#             {
#                 "id": str(j.id),
#                 "status": j.status,
#                 "from_number": j.from_number,
#                 "assistant_id": j.assistant_id,
#                 "total": j.total,
#                 "sent": j.sent,
#                 "failed": j.failed,
#                 "created_at": j.created_at,
#             } for j in rows
#         ],
#     }

# @router.get("/text/message-job/{job_id}")
# async def get_message_job(job_id: str, user: Annotated[User, Depends(get_current_user)] = None):
#     job = await MessageJob.get_or_none(id=job_id, user=user)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")
#     success_count = await MessageRecord.filter(job=job, success=True).count()
#     fail_count = await MessageRecord.filter(job=job, success=False).count()
#     return {
#         "id": str(job.id),
#         "status": job.status,
#         "from_number": job.from_number,
#         "assistant_id": job.assistant_id,
#         "total": job.total,
#         "sent": job.sent,
#         "failed": job.failed,
#         "success_count": success_count,
#         "fail_count": fail_count,
#         "created_at": job.created_at,
#     }

# # ─────────────────────────────────────────────────────────────────────────────
# # Assistants + Attach (unchanged)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.post("/text-assistants")
# async def create_text_assistant(assistant: TextAssistantCreate, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         required = ["name", "provider", "model", "system_prompt"]
#         empty = [f for f in required if not getattr(assistant, f, None)]
#         if empty:
#             raise HTTPException(status_code=400, detail=f"Missing required: {', '.join(empty)}")
#         new_a = await Assistant.create(
#             user=user,
#             name=assistant.name,
#             provider=assistant.provider,
#             model=assistant.model,
#             voice_provider=assistant.voice_provider,
#             voice=assistant.voice,
#             systemPrompt=assistant.system_prompt,
#             languages=[assistant.language] if assistant.language else None,
#             first_message="",
#             forwardingPhoneNumber=assistant.forwardingPhoneNumber,
#             assistant_toggle=assistant.assistant_toggle,
#         )
#         return {"success": True, "id": new_a.id, "name": new_a.name}
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Create failed: {e}")

# @router.get("/text-assistants")
# async def get_all_text_assistants(user: Annotated[User, Depends(get_current_user)]):
#     arr = await Assistant.filter(user=user).all()
#     return [
#         {
#             "id": a.id,
#             "name": a.name,
#             "provider": a.provider,
#             "model": a.model,
#             "languages": a.languages,
#             "voice_provider": a.voice_provider,
#             "voice": a.voice,
#             "system_prompt": a.systemPrompt,
#             "assistant_toggle": a.assistant_toggle,
#         } for a in arr
#     ]

# @router.put("/toggle-text-assistant/{assistant_id}")
# async def toggle_text_assistant(
#     assistant_id: int,
#     assistant_toggle: bool = Query(...),
#     user: Annotated[User, Depends(get_current_user)] = None
# ):
#     a = await Assistant.get_or_none(id=assistant_id, user=user)
#     if not a:
#         raise HTTPException(status_code=404, detail="Assistant not found")
#     a.assistant_toggle = assistant_toggle
#     await a.save()
#     return {"success": True, "assistant_id": a.id, "assistant_toggle": a.assistant_toggle}

# @router.post("/text/attach-assistant")
# async def attach_assistant_to_number(payload: AttachAssistantRequest, user: Annotated[User, Depends(get_current_user)]):
#     row = await PurchasedNumber.get_or_none(user=user, phone_number=payload.phone_number)
#     if not row:
#         raise HTTPException(status_code=404, detail="Purchased number not found")
#     if payload.assistant_id:
#         a = await Assistant.get_or_none(id=payload.assistant_id, user=user)
#         if not a:
#             raise HTTPException(status_code=404, detail="Assistant not found")
#         row.attached_assistant = a.id
#     else:
#         row.attached_assistant = None
#     await row.save()
#     return {"success": True, "phone_number": row.phone_number, "attached_assistant": row.attached_assistant, "kind": payload.kind}

# # ─────────────────────────────────────────────────────────────────────────────
# # Send + Status + Inbound (unchanged)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _resolve_from_number(db_user: User, assistant: Optional[Assistant], explicit_from: Optional[str]) -> PurchasedNumber:
#     if explicit_from:
#         row = await PurchasedNumber.filter(user=db_user, phone_number=explicit_from).first()
#         if not row:
#             raise HTTPException(status_code=400, detail="Provided from_number is not one of user's purchased numbers.")
#         return row
#     if assistant:
#         row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first()
#         if row:
#             return row
#     row = await PurchasedNumber.filter(user=db_user).first()
#     if not row:
#         raise HTTPException(status_code=400, detail="No purchased phone number available.")
#     return row

# @router.post("/send-text-message")
# async def send_text_message(
#     request: Request,
#     payload: TextMessageRequest,
#     user: Annotated[User, Depends(get_current_user)]
# ):
#     try:
#         db_user = await User.get(id=user.id)
#         client, _, _ = _twilio_client_for_user_sync(db_user)
#         from_row = await _resolve_from_number(db_user, None, payload.from_number)
#         status_cb = _build_status_callback_url(request, payload.status_webhook)

#         to_num = _sanitize_phone(payload.to_number)
#         from_num = _sanitize_phone(from_row.phone_number)
#         logger.info(f"[send] to={to_num} from={from_num}")

#         msg = await _twilio_send_message(
#             client=client,
#             body=(payload.body or "")[:1000],
#             from_number=from_num,
#             to=to_num,
#             status_callback=status_cb,
#         )

#         await _store_record_outbound(
#             job=None, user=db_user, assistant=None, appointment=None,
#             to_number=to_num, from_number=from_num, body=payload.body, sid=getattr(msg, "sid", None), success=True
#         )
#         return {"success": True, "message_sid": getattr(msg, "sid", None)}
#     except TwilioRestException as e:
#         detail = {"message": getattr(e, "msg", str(e)), "status": getattr(e, "status", None), "code": getattr(e, "code", None), "more_info": getattr(e, "more_info", None)}
#         logger.error(f"[send] twilio_error to={_sanitize_phone(payload.to_number)} code={detail['code']} msg={detail['message']}")
#         raise HTTPException(status_code=400, detail={"twilio_error": detail})
#     except Exception as e:
#         logger.exception(f"[send] unexpected_error: {e}")
#         raise HTTPException(status_code=400, detail=f"Error sending message: {e}")

# def _validate_twilio_signature(request: Request, form_data: Dict[str, str]) -> bool:
#     if os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() != "true":
#         return True
#     auth_token = os.getenv("TWILIO_AUTH_TOKEN")
#     if not auth_token:
#         return False
#     try:
#         signature = request.headers.get("X-Twilio-Signature", "")
#         validator = RequestValidator(auth_token)
#         base_url = os.getenv("PUBLIC_BASE_URL")
#         url = str(request.url)
#         if base_url:
#             path_q = request.url.path
#             if request.url.query:
#                 path_q += f"?{request.url.query}"
#             url = f"{base_url.rstrip('/')}{path_q}"
#         return validator.validate(url, form_data, signature)
#     except Exception:
#         return False

# @router.post("/text/sms-status")
# async def twilio_status_webhook(
#     MessageSid: str = Form(...),
#     MessageStatus: str = Form(...),
# ):
#     rec = await MessageRecord.get_or_none(sid=MessageSid)
#     if not rec:
#         return {"ok": True}
#     if MessageStatus in ("delivered", "sent", "queued"):
#         rec.success = True
#         rec.error = None
#     elif MessageStatus in ("failed", "undelivered"):
#         rec.success = False
#         rec.error = MessageStatus
#     await rec.save()
#     return {"ok": True}

# @router.post("/text/sms-webhook")
# async def twilio_sms_webhook(
#     request: Request,
#     From: str = Form(alias="From"),
#     To: str = Form(alias="To"),
#     Body: str = Form(alias="Body"),
#     MessageSid: Optional[str] = Form(default=None, alias="MessageSid"),
# ):
#     try:
#         form_dict = {"From": From, "To": To, "Body": Body or ""}
#         if MessageSid: form_dict["MessageSid"] = MessageSid
#         if not _validate_twilio_signature(request, form_dict):
#             return {"success": False, "error": "twilio_signature_invalid"}

#         to_row = await PurchasedNumber.filter(phone_number=To).first()
#         if not to_row:
#             return {"status": "ignored"}

#         user = await User.get(id=to_row.user_id)
#         client, _, _ = _twilio_client_for_user_sync(user)

#         logger.info(f"[inbound] to={_sanitize_phone(To)} from={_sanitize_phone(From)}")
#         await _store_record_inbound(
#             user=user, purchased_to=To, from_external=From, body=Body or "", sid=MessageSid, ok=True
#         )

#         assistant = None
#         if to_row.attached_assistant:
#             assistant = await Assistant.get_or_none(id=to_row.attached_assistant, user=user)
#         if not assistant:
#             assistant = await Assistant.filter(user=user, assistant_toggle=True).first()

#         if not assistant:
#             msg_text = Body or "Thanks for your message."
#             await _twilio_send_message(client, msg_text, To, From, None)
#             await _store_record_outbound(
#                 job=None, user=user, assistant=None, appointment=None,
#                 to_number=From, from_number=To, body=msg_text, sid=None, success=True
#             )
#             return {"status": "echoed"}

#         system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful SMS assistant. Keep replies short and useful."
#         generated = await _generate_via_vapi_or_openai(system_prompt, Body or "", user=user)
#         reply_text = generated or "Thanks for your message. We'll get back to you shortly."

#         status_cb = _build_status_callback_url(request)
#         msg = await _twilio_send_message(client, reply_text[:1000], To, From, status_cb)

#         await _store_record_outbound(
#             job=None, user=user, assistant=assistant, appointment=None,
#             to_number=From, from_number=To, body=reply_text, sid=getattr(msg, "sid", None), success=True
#         )
#         return {"success": True}
#     except Exception as e:
#         logger.exception(f"[inbound] error: {e}")
#         return {"success": False, "error": str(e)}

# # ─────────────────────────────────────────────────────────────────────────────
# # BULK sending (shared core)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _prefer_assistant_for_appt(user_id: int, appt: Appointment, default_assistant: Optional[Assistant]) -> Optional[Assistant]:
#     try:
#         if getattr(appt, "assistant_id", None):
#             return await Assistant.get_or_none(id=appt.assistant_id, user_id=user_id)
#     except Exception:
#         pass
#     return default_assistant

# async def _bulk_message_appointments_core(
#     *,
#     db_user: User,
#     request: Request,
#     assistant: Assistant,
#     from_row: PurchasedNumber,
#     appointments: List[Appointment],
#     job: Optional[MessageJob] = None,
#     messages_per_recipient: int = 1,
#     retry_count: int = 0,
#     retry_delay_seconds: int = 60,
#     per_message_delay_seconds: int = 0,
# ) -> str:
#     client, _, _ = _twilio_client_for_user_sync(db_user)
#     system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful SMS assistant. Keep replies short and useful."

#     total_attempts = len(appointments) * max(1, messages_per_recipient) * (1 + max(0, retry_count))
#     if job is None:
#         job = await MessageJob.create(
#             user=db_user, assistant=assistant, from_number=from_row.phone_number,
#             status="running", total=total_attempts, sent=0, failed=0
#         )
#     else:
#         job.total = total_attempts
#         job.status = "running"
#         job.sent = job.sent or 0
#         job.failed = job.failed or 0
#         await job.save()

#     status_cb = _build_status_callback_url(request)

#     for appt in appointments:
#         a = await _prefer_assistant_for_appt(db_user.id, appt, assistant)

#         user_message = (
#             f"Create a friendly, concise SMS about an appointment. "
#             f"Include title '{appt.title}', time {appt.start_at.isoformat()} ({appt.timezone}), "
#             f"and ask to reply YES to confirm or NO to reschedule."
#         )
#         generated = await _generate_via_vapi_or_openai(
#             system_prompt if not a else getattr(a, "systemPrompt", system_prompt),
#             user_message,
#             db_user
#         ) or (
#             f"Hi! Reminder for '{appt.title}' on {appt.start_at.isoformat()} ({appt.timezone}). "
#             f"Reply YES to confirm or NO to reschedule."
#         )

#         for msg_ix in range(max(1, messages_per_recipient)):
#             attempt_body = generated[:1000]
#             attempts_remaining = 1 + max(0, retry_count)
#             while attempts_remaining > 0:
#                 try:
#                     msg = await _twilio_send_message(
#                         client=client,
#                         body=attempt_body,
#                         from_number=_sanitize_phone(from_row.phone_number),
#                         to_number=_sanitize_phone(appt.phone),
#                         status_callback=status_cb,
#                     )
#                     await _store_record_outbound(
#                         job=job, user=db_user, assistant=a or assistant, appointment=appt,
#                         to_number=_sanitize_phone(appt.phone), from_number=_sanitize_phone(from_row.phone_number),
#                         body=attempt_body, sid=getattr(msg, "sid", None), success=True
#                     )
#                     job.sent += 1
#                     break
#                 except Exception as e:
#                     await _store_record_outbound(
#                         job=job, user=db_user, assistant=a or assistant, appointment=appt,
#                         to_number=_sanitize_phone(appt.phone), from_number=_sanitize_phone(from_row.phone_number),
#                         body=attempt_body, sid=None, success=False, error=str(e)
#                     )
#                     job.failed += 1
#                     attempts_remaining -= 1
#                     if attempts_remaining > 0:
#                         await asyncio.sleep(max(0, retry_delay_seconds))
#             if per_message_delay_seconds and msg_ix < max(1, messages_per_recipient) - 1:
#                 await asyncio.sleep(max(0, per_message_delay_seconds))

#     job.status = "completed"
#     await job.save()
#     return str(job.id)

# # ─────────────────────────────────────────────────────────────────────────────
# # SCHEDULED / UNSCHEDULED (existing one-off endpoints preserved)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.post("/text/message-scheduled")
# async def message_scheduled_appointments(
#     request: Request,
#     payload: MessageScheduledRequest,
#     background_tasks: BackgroundTasks,
#     user: Annotated[User, Depends(get_current_user)],
# ):
#     try:
#         db_user = await User.get(id=user.id)
#         if payload.assistant_id:
#             assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
#             if not assistant:
#                 raise HTTPException(status_code=404, detail="Assistant not found")
#         else:
#             assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#             if not assistant:
#                 raise HTTPException(status_code=404, detail="No enabled assistant found")

#         from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

#         backoff_h = payload.repeat_backoff_hours if payload.repeat_backoff_hours is not None else _env_int("REPEAT_BACKOFF_HOURS", 7)

#         appts = await _eligible_scheduled_appointments(
#             db_user=db_user,
#             include_unowned=bool(payload.include_unowned),
#             backoff_hours=max(0, backoff_h),
#         )
#         if payload.limit and payload.limit > 0:
#             appts = appts[: payload.limit]

#         if not appts:
#             total_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).count()
#             total_user = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).count()
#             return {
#                 "success": True,
#                 "sent": 0,
#                 "results": [],
#                 "detail": "No appointments eligible (likely due to backoff).",
#                 "stats": {
#                     "total_scheduled_all": total_all,
#                     "total_scheduled_for_user": total_user,
#                     "include_unowned": bool(payload.include_unowned),
#                     "repeat_backoff_hours": backoff_h,
#                 },
#             }

#         if payload.background is False:
#             job_id = await _bulk_message_appointments_core(
#                 db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts,
#                 messages_per_recipient=payload.messages_per_recipient or 1,
#                 retry_count=payload.retry_count or 0,
#                 retry_delay_seconds=payload.retry_delay_seconds or 60,
#                 per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#             )
#             return {"success": True, "job_id": job_id}
#         else:
#             pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
#             job = await MessageJob.create(
#                 user=db_user, assistant=assistant, from_number=from_row.phone_number,
#                 status="running", total=pre_total, sent=0, failed=0
#             )
#             background_tasks.add_task(
#                 _bulk_message_appointments_core,
#                 db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts, job=job,
#                 messages_per_recipient=payload.messages_per_recipient or 1,
#                 retry_count=payload.retry_count or 0,
#                 retry_delay_seconds=payload.retry_delay_seconds or 60,
#                 per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#             )
#             sse_token = _make_sse_token(db_user.id, str(job.id))
#             return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error messaging scheduled appointments: {e}")

# @router.post("/text/message-unscheduled")
# async def message_unscheduled_appointments(
#     request: Request,
#     payload: MessageScheduledRequest,
#     background_tasks: BackgroundTasks,
#     user: Annotated[User, Depends(get_current_user)],
# ):
#     try:
#         db_user = await User.get(id=user.id)
#         if payload.assistant_id:
#             assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
#             if not assistant:
#                 raise HTTPException(status_code=404, detail="Assistant not found")
#         else:
#             assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#             if not assistant:
#                 raise HTTPException(status_code=404, detail="No enabled assistant found")

#         from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

#         appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
#         # effective unscheduled backoff hours
#         if payload.unscheduled_backoff_hours is not None:
#             backoff_h = max(0, payload.unscheduled_backoff_hours)
#         else:
#             env_unsched = _env_int("UNSCHEDULED_BACKOFF_HOURS", -1)
#             backoff_h = env_unsched if env_unsched >= 0 else _env_int("REPEAT_BACKOFF_HOURS", 7)

#         appts: List[Appointment] = []
#         for a in appts_all:
#             if backoff_h > 0:
#                 already = await _recent_success_outbound_exists(a.phone, db_user, backoff_h)
#                 if already:
#                     continue
#             appts.append(a)

#         if payload.limit and payload.limit > 0:
#             appts = appts[: payload.limit]

#         if not appts:
#             return {"success": True, "sent": 0, "results": []}

#         if payload.background is False:
#             job_id = await _bulk_message_appointments_core(
#                 db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts,
#                 messages_per_recipient=payload.messages_per_recipient or 1,
#                 retry_count=payload.retry_count or 0,
#                 retry_delay_seconds=payload.retry_delay_seconds or 60,
#                 per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#             )
#             return {"success": True, "job_id": job_id}
#         else:
#             pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
#             job = await MessageJob.create(
#                 user=db_user, assistant=assistant, from_number=from_row.phone_number,
#                 status="running", total=pre_total, sent=0, failed=0
#             )
#             background_tasks.add_task(
#                 _bulk_message_appointments_core,
#                 db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts, job=job,
#                 messages_per_recipient=payload.messages_per_recipient or 1,
#                 retry_count=payload.retry_count or 0,
#                 retry_delay_seconds=payload.retry_delay_seconds or 60,
#                 per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#             )
#             sse_token = _make_sse_token(db_user.id, str(job.id))
#             return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error messaging unscheduled appointments: {e}")

# # ─────────────────────────────────────────────────────────────────────────────
# # Debug (unchanged rule text)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.get("/text/debug/scheduled-selection")
# async def debug_scheduled_selection(
#     include_unowned: bool = Query(default=True),
#     repeat_backoff_hours: Optional[int] = Query(default=None, description="defaults to 7 via REPEAT_BACKOFF_HOURS"),
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     db_user = await User.get(id=user.id)
#     backoff_h = repeat_backoff_hours if repeat_backoff_hours is not None else _env_int("REPEAT_BACKOFF_HOURS", 7)

#     if include_unowned:
#         appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
#             Q(user=db_user) | Q(user_id=None)
#         ).all()
#     else:
#         appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).all()

#     eligible = []
#     samples = []
#     now = datetime.now(timezone.utc)

#     for a in appts_all:
#         recent = await _recent_success_outbound_exists(a.phone, db_user, backoff_h)
#         ok = not recent
#         if ok:
#             eligible.append(a)
#         samples.append({
#             "id": str(a.id),
#             "phone": a.phone,
#             "tz": getattr(a, "timezone", None),
#             "start_at": (a.start_at.replace(tzinfo=ZoneInfo(a.timezone)) if (a.start_at and getattr(a, "timezone", None)) else a.start_at),
#             "now": now,
#             "backoff_ok": ok,
#             "eligible": ok,
#         })

#     info = {
#         "total": len(appts_all),
#         "eligible": len(eligible),
#         "include_unowned": include_unowned,
#         "repeat_backoff_hours": backoff_h,
#         "rule": "Scheduled = eligible unless already messaged successfully within backoff window.",
#     }
#     logger.info(f"[debug] scheduled_selection: {info}")
#     return {"info": info, "samples": samples[:50]}

# # ─────────────────────────────────────────────────────────────────────────────
# # === NEW: Always-on Texting Daemons (scheduled & unscheduled)
# # ─────────────────────────────────────────────────────────────────────────────

# class _DaemonState:
#     def __init__(self, *, enabled: bool, tick_interval_seconds: int, include_unowned: bool,
#                  repeat_backoff_hours: int, unscheduled_backoff_hours: int):
#         self.enabled = enabled
#         self.tick_interval_seconds = tick_interval_seconds
#         self.include_unowned = include_unowned
#         self.repeat_backoff_hours = repeat_backoff_hours
#         self.unscheduled_backoff_hours = unscheduled_backoff_hours

#         # live metrics
#         self.status: str = "idle"          # idle|running|paused|error
#         self.last_tick_at: Optional[datetime] = None
#         self.last_error: Optional[str] = None

#         # last cycle
#         self.last_queue_size: int = 0
#         self.last_sent: int = 0
#         self.last_failed: int = 0

#         # cumulative (since process start)
#         self.total_sent: int = 0
#         self.total_failed: int = 0

# # per-process in-memory maps: DAEMONS[kind][user_id] = _DaemonState
# DAEMONS: Dict[Kind, Dict[int, _DaemonState]] = {"scheduled": {}, "unscheduled": {}}
# _DAEMON_TASKS: Dict[Kind, Optional[asyncio.Task]] = {"scheduled": None, "unscheduled": None}

# def _get_default_state(kind: Kind) -> _DaemonState:
#     return _DaemonState(
#         enabled=True,
#         tick_interval_seconds=_env_int("TEXTING_TICK_INTERVAL_SECONDS", 120),
#         include_unowned=_env_bool("SCHEDULED_INCLUDE_UNOWNED", True),
#         repeat_backoff_hours=_env_int("REPEAT_BACKOFF_HOURS", 7),
#         unscheduled_backoff_hours=_env_int("UNSCHEDULED_BACKOFF_HOURS", _env_int("REPEAT_BACKOFF_HOURS", 7)),
#     )

# def _user_daemon_state(kind: Kind, user_id: int) -> _DaemonState:
#     if user_id not in DAEMONS[kind]:
#         DAEMONS[kind][user_id] = _get_default_state(kind)
#     return DAEMONS[kind][user_id]

# async def _users_with(kind: Kind) -> List[int]:
#     if kind == "scheduled":
#         ids = await Appointment.filter(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
#     else:
#         ids = await Appointment.exclude(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
#     return [uid for uid in set(ids) if uid]

# async def _daemon_tick_for_user(kind: Kind, uid: int):
#     state = _user_daemon_state(kind, uid)
#     if not state.enabled:
#         state.status = "paused"
#         return

#     db_user = await User.get_or_none(id=uid)
#     if not db_user:
#         return

#     try:
#         state.status = "running"
#         state.last_error = None
#         state.last_sent = 0
#         state.last_failed = 0
#         state.last_queue_size = 0

#         # pick assistant + number once per tick
#         assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#         if not assistant:
#             state.status = "idle"
#             return
#         from_row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first() \
#                    or await PurchasedNumber.filter(user=db_user).first()
#         if not from_row:
#             state.status = "idle"
#             return

#         # select appointments by kind
#         if kind == "scheduled":
#             appts = await _eligible_scheduled_appointments(
#                 db_user=db_user,
#                 include_unowned=state.include_unowned,
#                 backoff_hours=max(0, state.repeat_backoff_hours),
#             )
#         else:
#             appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
#             appts = []
#             bh = max(0, state.unscheduled_backoff_hours)
#             for a in appts_all:
#                 if bh > 0 and await _recent_success_outbound_exists(a.phone, db_user, bh):
#                     continue
#                 appts.append(a)

#         state.last_queue_size = len(appts)
#         if not appts:
#             state.status = "idle"
#             return

#         # create a job for this tick (for audit/history)
#         # NOTE: we’ll send with default single message, no extra retries here.
#         # You can parameterize these if you want per-daemon knobs.
#         job = await MessageJob.create(
#             user=db_user, assistant=assistant, from_number=from_row.phone_number,
#             status="running", total=len(appts), sent=0, failed=0
#         )

#         # minimal Request substitute for callbacks if not available
#         class _DummyReq:
#             # allows _build_status_callback_url to construct callback from PUBLIC_BASE_URL
#             url = type("U", (), {"path": "/api/text/sms-status", "query": ""})()
#         request_like = _DummyReq()

#         # send
#         await _bulk_message_appointments_core(
#             db_user=db_user, request=request_like, assistant=assistant, from_row=from_row, appointments=appts, job=job,
#             messages_per_recipient=1, retry_count=0, retry_delay_seconds=60, per_message_delay_seconds=0,
#         )

#         # update metrics
#         state.last_sent = job.sent or 0
#         state.last_failed = job.failed or 0
#         state.total_sent += state.last_sent
#         state.total_failed += state.last_failed
#         state.status = "idle"
#     except Exception as e:
#         state.last_error = str(e)
#         state.status = "error"

#     state.last_tick_at = datetime.now(timezone.utc)

# async def _daemon_loop(kind: Kind):
#     logger.info(f"[daemon] starting loop for {kind}")
#     while True:
#         try:
#             user_ids = await _users_with(kind)
#             # ensure we have state for any user we see
#             for uid in user_ids:
#                 _user_daemon_state(kind, uid)

#             # tick each user (serially to avoid hammering Twilio);
#             # you can asyncio.gather in small batches if you want parallelism per user.
#             for uid in user_ids:
#                 await _daemon_tick_for_user(kind, uid)

#             # sleep = min per-user interval across all present users
#             if user_ids:
#                 intervals = [max(5, _user_daemon_state(kind, uid).tick_interval_seconds) for uid in user_ids]
#                 sleep_for = min(intervals) if intervals else _env_int("TEXTING_TICK_INTERVAL_SECONDS", 120)
#             else:
#                 sleep_for = _env_int("TEXTING_TICK_INTERVAL_SECONDS", 120)
#             await asyncio.sleep(sleep_for)
#         except asyncio.CancelledError:
#             logger.info(f"[daemon] loop for {kind} cancelled")
#             break
#         except Exception as e:
#             logger.exception(f"[daemon] loop error for {kind}: {e}")
#             await asyncio.sleep(5)

# def _start_daemon_if_needed(kind: Kind):
#     if _DAEMON_TASKS[kind] is None or _DAEMON_TASKS[kind].done():
#         _DAEMON_TASKS[kind] = asyncio.create_task(_daemon_loop(kind))

# # ─────────────────────────────────────────────────────────────────────────────
# # === NEW: Daemon control + SSE
# # ─────────────────────────────────────────────────────────────────────────────

# def _make_daemon_token(user_id: int, kind: Kind, ttl_seconds: int = 600) -> str:
#     exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
#     payload = {"id": user_id, "daemon_kind": kind, "kind": "daemon_sse", "exp": exp}
#     return generate_user_token(payload)

# def _validate_daemon_token(token: str, expected_kind: Kind) -> Optional[int]:
#     try:
#         claims = decode_user_token(token)
#         if not isinstance(claims, dict): return None
#         if claims.get("kind") != "daemon_sse": return None
#         if claims.get("daemon_kind") != expected_kind: return None
#         uid = claims.get("id")
#         return uid if isinstance(uid, int) else None
#     except Exception:
#         return None

# @router.get("/text/daemon/state")
# async def get_daemon_state(
#     kind: Kind = Query(...),
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     st = _user_daemon_state(kind, user.id)
#     return {
#         "kind": kind,
#         "enabled": st.enabled,
#         "status": st.status,
#         "tick_interval_seconds": st.tick_interval_seconds,
#         "include_unowned": st.include_unowned,
#         "repeat_backoff_hours": st.repeat_backoff_hours,
#         "unscheduled_backoff_hours": st.unscheduled_backoff_hours,
#         "last_tick_at": st.last_tick_at,
#         "last_error": st.last_error,
#         "last_queue_size": st.last_queue_size,
#         "last_sent": st.last_sent,
#         "last_failed": st.last_failed,
#         "total_sent": st.total_sent,
#         "total_failed": st.total_failed,
#         "sse_token": _make_daemon_token(user.id, kind),
#     }

# @router.put("/text/daemon/config")
# async def update_daemon_config(
#     payload: DaemonConfigRequest,
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     st = _user_daemon_state(payload.kind, user.id)
#     if payload.enabled is not None:
#         st.enabled = bool(payload.enabled)
#         st.status = "paused" if not st.enabled else "idle"
#     if payload.tick_interval_seconds is not None:
#         st.tick_interval_seconds = int(payload.tick_interval_seconds)
#     if payload.kind == "scheduled":
#         if payload.include_unowned is not None:
#             st.include_unowned = bool(payload.include_unowned)
#         if payload.repeat_backoff_hours is not None:
#             st.repeat_backoff_hours = int(payload.repeat_backoff_hours)
#     else:
#         if payload.unscheduled_backoff_hours is not None:
#             st.unscheduled_backoff_hours = int(payload.unscheduled_backoff_hours)

#     # ensure loop is running
#     _start_daemon_if_needed(payload.kind)
#     return {"success": True, "state": await get_daemon_state(kind=payload.kind, user=user)}  # reuse serializer

# @router.get("/text/daemon-progress-sse")
# async def daemon_progress_sse(
#     request: Request,
#     kind: Kind = Query(...),
#     token: Optional[str] = Query(default=None),
#     sse: Optional[str] = Query(default=None),
# ):
#     auth_user: Optional[User] = None
#     try:
#         if sse:
#             uid = _validate_daemon_token(sse, kind)
#             if uid is not None:
#                 auth_user = await User.get_or_none(id=uid)
#         if not auth_user:
#             auth_header = request.headers.get("Authorization")
#             raw = None
#             if auth_header and auth_header.lower().startswith("bearer "):
#                 raw = auth_header.split(" ", 1)[1]
#             elif token:
#                 raw = token
#             else:
#                 raw = request.cookies.get("token") or request.cookies.get("access_token") or request.cookies.get("Authorization")
#             if raw:
#                 creds = decode_user_token(raw)
#                 uid = creds.get("id") if isinstance(creds, dict) else None
#                 if uid is not None:
#                     auth_user = await User.get_or_none(id=uid)
#     except Exception:
#         auth_user = None

#     if not auth_user:
#         raise HTTPException(status_code=403, detail="Not authenticated")

#     # make sure loop is running so user sees updates
#     _start_daemon_if_needed(kind)

#     async def event_stream() -> AsyncGenerator[bytes, None]:
#         last: Dict[str, Any] = {}
#         while True:
#             if await request.is_disconnected():
#                 break
#             st = _user_daemon_state(kind, auth_user.id)
#             payload = {
#                 "kind": kind,
#                 "enabled": st.enabled,
#                 "status": st.status,
#                 "tick_interval_seconds": st.tick_interval_seconds,
#                 "include_unowned": st.include_unowned,
#                 "repeat_backoff_hours": st.repeat_backoff_hours,
#                 "unscheduled_backoff_hours": st.unscheduled_backoff_hours,
#                 "last_tick_at": st.last_tick_at.isoformat() if st.last_tick_at else None,
#                 "last_error": st.last_error,
#                 "last_queue_size": st.last_queue_size,
#                 "last_sent": st.last_sent,
#                 "last_failed": st.last_failed,
#                 "total_sent": st.total_sent,
#                 "total_failed": st.total_failed,
#             }
#             if payload != last:
#                 yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
#                 last = payload
#             await asyncio.sleep(1.0)

#     headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream", "Connection": "keep-alive"}
#     return StreamingResponse(event_stream(), headers=headers)

# # ─────────────────────────────────────────────────────────────────────────────
# # Scheduler wiring
# # ─────────────────────────────────────────────────────────────────────────────

# # (compat) these previously existed; keep them as wrappers if something calls them.
# async def run_texting_job():
#     # Trigger a single scheduled tick for all users (compat)
#     for uid in await _users_with("scheduled"):
#         await _daemon_tick_for_user("scheduled", uid)

# async def run_unscheduled_texting_job():
#     # Trigger a single unscheduled tick for all users (compat)
#     for uid in await _users_with("unscheduled"):
#         await _daemon_tick_for_user("unscheduled", uid)

# def schedule_texting_job(timezone: str = "UTC"):
#     """
#     Old code scheduled minutely jobs. We now start the long-running daemon loops
#     once at startup. Keeping these calls so existing startup code still works.
#     """
#     # kick off the loops once the event loop is alive
#     nudge_once(lambda: _start_daemon_if_needed("scheduled"), delay_seconds=0)
#     nudge_once(lambda: _start_daemon_if_needed("unscheduled"), delay_seconds=0)
#     # (Optional) also keep a periodic nudge in case the loop ever dies
#     schedule_minutely_job("texting-daemon-nudge-scheduled", timezone, lambda: _start_daemon_if_needed("scheduled"))
#     schedule_minutely_job("texting-daemon-nudge-unscheduled", timezone, lambda: _start_daemon_if_needed("unscheduled"))
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
import json
import os
import re
from typing import Annotated, List, Optional, Tuple, Dict, Any, AsyncGenerator, Literal
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

import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

from tortoise.expressions import Q

from helpers.token_helper import get_current_user, decode_user_token, generate_user_token
from helpers.vapi_helper import get_headers  # optional VAPI
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
    status_webhook: Optional[str] = None

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

class MessageScheduledRequest(BaseModel):
    assistant_id: Optional[int] = None
    from_number: Optional[str] = None
    limit: Optional[int] = None
    background: Optional[bool] = True

    # send/retry knobs
    messages_per_recipient: Optional[int] = Field(default=1, ge=1, le=10)
    retry_count: Optional[int] = Field(default=0, ge=0, le=5)
    retry_delay_seconds: Optional[int] = Field(default=60, ge=5, le=3600)
    per_message_delay_seconds: Optional[int] = Field(default=0, ge=0, le=3600)

    # scheduled-selection knobs
    include_unowned: Optional[bool] = Field(default=True, description="Include appts with null user_id")
    # backoff (Scheduled logic ONLY uses this)
    repeat_backoff_hours: Optional[int] = Field(default=None, description="Default 7 (via REPEAT_BACKOFF_HOURS if set)")

    # unscheduled backoff (only for unscheduled endpoint)
    unscheduled_backoff_hours: Optional[int] = Field(default=None)

class AttachAssistantRequest(BaseModel):
    phone_number: str
    assistant_id: Optional[int] = None
    kind: Optional[str] = Field(default=None, description="scheduled|unscheduled (advisory only)")

# === Daemon config/state schemas
Kind = Literal["scheduled", "unscheduled"]

class DaemonConfigRequest(BaseModel):
    kind: Kind
    enabled: Optional[bool] = None
    tick_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    include_unowned: Optional[bool] = None  # scheduled only
    repeat_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)  # scheduled
    unscheduled_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)

# ─────────────────────────────────────────────────────────────────────────────
# Router / logger
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter()
logger = logging.getLogger("text_assistant")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "y", "yes", "on")

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _sanitize_phone(s: Optional[str]) -> str:
    return (s or "").strip()

def _default_region() -> str:
    return (os.getenv("DEFAULT_SMS_REGION") or "US").upper()

def _parse_to_e164(raw: Optional[str], region: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Returns (ok, e164, error). Accepts local formats and normalizes to +E.164.
    """
    s = (raw or "").strip()
    if not s:
        return (False, None, "empty_number")
    try:
        region = (region or _default_region()).upper()
        num = phonenumbers.parse(s, region)
        if not phonenumbers.is_possible_number(num):
            return (False, None, "not_possible")
        if not phonenumbers.is_valid_number(num):
            return (False, None, "not_valid")
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        return (True, e164, None)
    except NumberParseException as e:
        return (False, None, f"parse_error:{e.error_type}")

def _format_dt_local(dt: datetime, tz: Optional[str]) -> str:
    try:
        if tz:
            return dt.astimezone(ZoneInfo(tz)).strftime("%b %d, %I:%M %p")
    except Exception:
        pass
    return dt.strftime("%b %d, %I:%M %p")

# —— SMS copy cleanup ——
_COMPACT_RE = [
    (re.compile(r"^sure!.*?:\s*", re.I | re.S), ""),
    (re.compile(r"^here(?:'s| is).{0,80}:\s*", re.I | re.S), ""),
    (re.compile(r"^[-–—\s]*$", re.M), ""),
    (re.compile(r"[`*_#>]+"), ""),
    (re.compile(r"[^\S\r\n]+"), " "),
    (re.compile(r"\n{3,}"), "\n\n"),
    (re.compile(r"[^\w\s.,:;!?+\-()/]"), ""),  # strip emojis/odd unicode
]
def _compact_sms(text: str, hard_limit: int = 240) -> str:
    s = (text or "").strip()
    for pat, rep in _COMPACT_RE:
        s = pat.sub(rep, s)
    s = s.replace("\r", "")
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    s = " ".join(lines)  # single paragraph
    if len(s) > hard_limit:
        s = s[:hard_limit].rstrip(". ,;:") + "..."
    return s

def _fallback_appt_sms(appt: Appointment) -> str:
    when = _format_dt_local(appt.start_at, getattr(appt, "timezone", None))
    title = (appt.title or "your appointment").strip()
    return f"{title} on {when}. Reply YES to confirm or NO to reschedule."

def _twilio_client_from_values(account_sid: Optional[str], auth_token: Optional[str]) -> Tuple[Client, str, str]:
    sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
    token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise HTTPException(status_code=400, detail="No Twilio credentials found. Set via POST /twilio/credentials.")
    return Client(sid, token), sid, token

def _twilio_client_for_user_sync(user: User) -> Tuple[Client, str, str]:
    return _twilio_client_from_values(
        getattr(user, "twilio_account_sid", None),
        getattr(user, "twilio_auth_token", None),
    )

def _build_status_callback_url(request: Request, override_url: Optional[str] = None) -> Optional[str]:
    """Return a public StatusCallback URL or None (if localhost)."""
    def _is_public(u: str) -> bool:
        try:
            p = urlparse(u)
            if p.scheme not in ("http", "https"): return False
            if not p.netloc: return False
            host = p.hostname or ""
            if host in ("localhost", "127.0.0.1", "::1"): return False
            return True
        except Exception:
            return False

    if override_url and _is_public(override_url):
        return override_url

    base = os.getenv("PUBLIC_BASE_URL")
    if not base:
        return None
    candidate = f"{base.rstrip('/')}/api/text/sms-status"
    return candidate if _is_public(candidate) else None

async def _generate_via_vapi_or_openai(system_prompt: str, user_message: str, user: Optional[User] = None) -> Optional[str]:
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
    # fallback to OpenAI
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
        body=(body or "")[:1000],
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
        body=(body or "")[:1000],
        sid=sid,
        success=ok,
        error=error,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Backoff logic (the ONLY gate for SCHEDULED selection)
# ─────────────────────────────────────────────────────────────────────────────

async def _recent_success_outbound_exists(phone: str, user: User, within_hours: int) -> bool:
    if not phone:
        return False
    since = datetime.now(timezone.utc) - timedelta(hours=max(0, within_hours))
    return await MessageRecord.filter(
        user=user, to_number=phone, success=True, created_at__gte=since
    ).exists()

async def _eligible_scheduled_appointments(
    *,
    db_user: User,
    include_unowned: bool,
    backoff_hours: int,
) -> List[Appointment]:
    if include_unowned:
        appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
            Q(user=db_user) | Q(user_id=None)
        ).all()
    else:
        appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).all()

    result: List[Appointment] = []
    for a in appts_all:
        already = await _recent_success_outbound_exists(a.phone, db_user, backoff_hours)
        if already:
            continue
        result.append(a)
    return result

# ─────────────────────────────────────────────────────────────────────────────
# SSE progress (per-job, existing)
# ─────────────────────────────────────────────────────────────────────────────

def _make_sse_token(user_id: int, job_id: str, ttl_seconds: int = 600) -> str:
    exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    payload = {"id": user_id, "job_id": job_id, "kind": "sse", "exp": exp}
    return generate_user_token(payload)

def _validate_sse_token(token: str, expected_job_id: str) -> Optional[int]:
    try:
        claims = decode_user_token(token)
        if not isinstance(claims, dict): return None
        if claims.get("kind") != "sse": return None
        if claims.get("job_id") != expected_job_id: return None
        uid = claims.get("id")
        return uid if isinstance(uid, int) else None
    except Exception:
        return None

@router.get("/text/message-progress")
async def get_message_progress(
    job_id: Optional[str] = None,
    user: Annotated[User, Depends(get_current_user)] = None
):
    job = await (MessageJob.filter(user=user).order_by("-created_at").first() if not job_id
                else MessageJob.get_or_none(id=job_id, user=user))
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
    job_id: str = Query(...),
    token: Optional[str] = Query(default=None),
    sse: Optional[str] = Query(default=None)
):
    auth_user: Optional[User] = None
    try:
        if sse:
            uid = _validate_sse_token(sse, job_id)
            if uid is not None:
                auth_user = await User.get_or_none(id=uid)
        if not auth_user:
            auth_header = request.headers.get("Authorization")
            raw = None
            if auth_header and auth_header.lower().startswith("bearer "):
                raw = auth_header.split(" ", 1)[1]
            elif token:
                raw = token
            else:
                raw = request.cookies.get("token") or request.cookies.get("access_token") or request.cookies.get("Authorization")
            if raw:
                creds = decode_user_token(raw)
                uid = creds.get("id") if isinstance(creds, dict) else None
                if uid is not None:
                    auth_user = await User.get_or_none(id=uid)
    except Exception:
        auth_user = None

    if not auth_user:
        raise HTTPException(status_code=403, detail="Not authenticated")

    async def event_stream() -> AsyncGenerator[bytes, None]:
        last: Dict[str, Any] = {}
        while True:
            if await request.is_disconnected():
                break
            job = await MessageJob.get_or_none(id=job_id, user=auth_user)
            if not job:
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
                yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
                last = payload
            if job.status in ("completed", "failed", "canceled"):
                yield b"event: done\ndata: {}\n\n"
                break
            await asyncio.sleep(1.0)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream", "Connection": "keep-alive"}
    return StreamingResponse(event_stream(), headers=headers)

# ─────────────────────────────────────────────────────────────────────────────
# Messages / Threads / Jobs
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
    peer_number: Optional[str] = None,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    q = MessageRecord.filter(user=user).order_by("-created_at")
    if success is not None: q = q.filter(success=success)
    if job_id: q = q.filter(job_id=job_id)
    if assistant_id: q = q.filter(assistant_id=assistant_id)
    if to_like: q = q.filter(to_number__icontains=to_like)
    if from_like: q = q.filter(from_number__icontains=from_like)
    if start:
        try:
            q = q.filter(created_at__gte=datetime.fromisoformat(start))
        except Exception:
            pass
    if end:
        try:
            q = q.filter(created_at__lte=datetime.fromisoformat(end))
        except Exception:
            pass
    if peer_number:
        q = q.filter(Q(to_number__icontains=peer_number) | Q(from_number__icontains=peer_number))

    total = await q.count()
    purchased_set = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))
    rows = await q.offset(offset).limit(limit)
    def _direction(r) -> str:
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
            } for r in rows
        ],
    }

@router.get("/text/threads")
async def list_threads(
    limit: int = 50,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    purchased = set(await PurchasedNumber.filter(user=user).values_list("phone_number", flat=True))
    rows = await MessageRecord.filter(user=user).order_by("-created_at").limit(1000)
    threads: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a, b = r.from_number, r.to_number
        if a in purchased and b not in purchased:
            peer, mynum = b, a
        elif b in purchased and a not in purchased:
            peer, mynum = a, b
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

@router.get("/text/message-jobs")
async def list_message_jobs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    q = MessageJob.filter(user=user).order_by("-created_at")
    if status: q = q.filter(status=status)
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
            } for j in rows
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
# Assistants + Attach
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/text-assistants")
async def create_text_assistant(assistant: TextAssistantCreate, user: Annotated[User, Depends(get_current_user)]):
    try:
        required = ["name", "provider", "model", "system_prompt"]
        empty = [f for f in required if not getattr(assistant, f, None)]
        if empty:
            raise HTTPException(status_code=400, detail=f"Missing required: {', '.join(empty)}")
        new_a = await Assistant.create(
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
        return {"success": True, "id": new_a.id, "name": new_a.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Create failed: {e}")

@router.get("/text-assistants")
async def get_all_text_assistants(user: Annotated[User, Depends(get_current_user)]):
    arr = await Assistant.filter(user=user).all()
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
        } for a in arr
    ]

@router.put("/toggle-text-assistant/{assistant_id}")
async def toggle_text_assistant(
    assistant_id: int,
    assistant_toggle: bool = Query(...),
    user: Annotated[User, Depends(get_current_user)] = None
):
    a = await Assistant.get_or_none(id=assistant_id, user=user)
    if not a:
        raise HTTPException(status_code=404, detail="Assistant not found")
    a.assistant_toggle = assistant_toggle
    await a.save()
    return {"success": True, "assistant_id": a.id, "assistant_toggle": a.assistant_toggle}

@router.post("/text/attach-assistant")
async def attach_assistant_to_number(payload: AttachAssistantRequest, user: Annotated[User, Depends(get_current_user)]):
    row = await PurchasedNumber.get_or_none(user=user, phone_number=payload.phone_number)
    if not row:
        raise HTTPException(status_code=404, detail="Purchased number not found")
    if payload.assistant_id:
        a = await Assistant.get_or_none(id=payload.assistant_id, user=user)
        if not a:
            raise HTTPException(status_code=404, detail="Assistant not found")
        row.attached_assistant = a.id
    else:
        row.attached_assistant = None
    await row.save()
    return {"success": True, "phone_number": row.phone_number, "attached_assistant": row.attached_assistant, "kind": payload.kind}

# ─────────────────────────────────────────────────────────────────────────────
# Send + Status + Inbound
# ─────────────────────────────────────────────────────────────────────────────

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

@router.post("/send-text-message")
async def send_text_message(
    request: Request,
    payload: TextMessageRequest,
    user: Annotated[User, Depends(get_current_user)]
):
    try:
        db_user = await User.get(id=user.id)
        client, _, _ = _twilio_client_for_user_sync(db_user)
        from_row = await _resolve_from_number(db_user, None, payload.from_number)
        status_cb = _build_status_callback_url(request, payload.status_webhook)

        ok_to, to_num, to_err = _parse_to_e164(payload.to_number)
        if not ok_to:
            await _store_record_outbound(
                job=None, user=db_user, assistant=None, appointment=None,
                to_number=_sanitize_phone(payload.to_number), from_number="", body=payload.body,
                sid=None, success=False, error=f"invalid_to_number:{to_err}"
            )
            raise HTTPException(status_code=400, detail={"twilio_error": {"code": 21211, "message": f"Invalid To number ({to_err})"}})

        ok_from, from_num, from_err = _parse_to_e164(from_row.phone_number)
        if not ok_from:
            raise HTTPException(status_code=400, detail=f"Invalid from_number ({from_err}) in your PurchasedNumber")

        body = _compact_sms(payload.body)

        logger.info(f"[send] to={to_num} from={from_num}")
        msg = await _twilio_send_message(
            client=client,
            body=(body or "")[:1000],
            from_number=from_num,
            to=to_num,
            status_callback=status_cb,
        )

        await _store_record_outbound(
            job=None, user=db_user, assistant=None, appointment=None,
            to_number=to_num, from_number=from_num, body=body, sid=getattr(msg, "sid", None), success=True
        )
        return {"success": True, "message_sid": getattr(msg, "sid", None)}
    except TwilioRestException as e:
        code = getattr(e, "code", None)
        msg  = getattr(e, "msg", str(e))
        if code == 21211:
            detail = {"code": 21211, "message": "Invalid To number"}
        elif code in (21612, 21610):
            detail = {"code": code, "message": msg}
        else:
            detail = {"code": code, "message": msg}
        logger.error(f"[send] twilio_error to={_sanitize_phone(payload.to_number)} code={detail['code']} msg={detail['message']}")
        raise HTTPException(status_code=400, detail={"twilio_error": detail})
    except Exception as e:
        logger.exception(f"[send] unexpected_error: {e}")
        raise HTTPException(status_code=400, detail=f"Error sending message: {e}")

def _validate_twilio_signature(request: Request, form_data: Dict[str, str]) -> bool:
    if os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() != "true":
        return True
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        return False
    try:
        signature = request.headers.get("X-Twilio-Signature", "")
        validator = RequestValidator(auth_token)
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

@router.post("/text/sms-status")
async def twilio_status_webhook(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
):
    rec = await MessageRecord.get_or_none(sid=MessageSid)
    if not rec:
        return {"ok": True}
    if MessageStatus in ("delivered", "sent", "queued"):
        rec.success = True
        rec.error = None
    elif MessageStatus in ("failed", "undelivered"):
        rec.success = False
        rec.error = MessageStatus
    await rec.save()
    return {"ok": True}

@router.post("/text/sms-webhook")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(alias="From"),
    To: str = Form(alias="To"),
    Body: str = Form(alias="Body"),
    MessageSid: Optional[str] = Form(default=None, alias="MessageSid"),
):
    try:
        form_dict = {"From": From, "To": To, "Body": Body or ""}
        if MessageSid: form_dict["MessageSid"] = MessageSid
        if not _validate_twilio_signature(request, form_dict):
            return {"success": False, "error": "twilio_signature_invalid"}

        to_row = await PurchasedNumber.filter(phone_number=To).first()
        if not to_row:
            return {"status": "ignored"}

        user = await User.get(id=to_row.user_id)
        client, _, _ = _twilio_client_for_user_sync(user)

        logger.info(f"[inbound] to={_sanitize_phone(To)} from={_sanitize_phone(From)}")
        await _store_record_inbound(
            user=user, purchased_to=To, from_external=From, body=Body or "", sid=MessageSid, ok=True
        )

        assistant = None
        if to_row.attached_assistant:
            assistant = await Assistant.get_or_none(id=to_row.attached_assistant, user=user)
        if not assistant:
            assistant = await Assistant.filter(user=user, assistant_toggle=True).first()

        if not assistant:
            msg_text = _compact_sms(Body or "Thanks for your message.")
            await _twilio_send_message(client, msg_text, To, From, None)
            await _store_record_outbound(
                job=None, user=user, assistant=None, appointment=None,
                to_number=From, from_number=To, body=msg_text, sid=None, success=True
            )
            return {"status": "echoed"}

        system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful SMS assistant. Keep replies short and useful."
        generated = await _generate_via_vapi_or_openai(system_prompt, Body or "", user=user)
        reply_text = _compact_sms(generated or "Thanks for your message. We'll get back to you shortly.")

        status_cb = _build_status_callback_url(request)
        msg = await _twilio_send_message(client, reply_text[:1000], To, From, status_cb)

        await _store_record_outbound(
            job=None, user=user, assistant=assistant, appointment=None,
            to_number=From, from_number=To, body=reply_text, sid=getattr(msg, "sid", None), success=True
        )
        return {"success": True}
    except Exception as e:
        logger.exception(f"[inbound] error: {e}")
        return {"success": False, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# BULK sending (shared core)
# ─────────────────────────────────────────────────────────────────────────────

async def _prefer_assistant_for_appt(user_id: int, appt: Appointment, default_assistant: Optional[Assistant]) -> Optional[Assistant]:
    try:
        if getattr(appt, "assistant_id", None):
            return await Assistant.get_or_none(id=appt.assistant_id, user_id=user_id)
    except Exception:
        pass
    return default_assistant

async def _bulk_message_appointments_core(
    *,
    db_user: User,
    request: Request,
    assistant: Assistant,
    from_row: PurchasedNumber,
    appointments: List[Appointment],
    job: Optional[MessageJob] = None,
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
            user=db_user, assistant=assistant, from_number=from_row.phone_number,
            status="running", total=total_attempts, sent=0, failed=0
        )
    else:
        job.total = total_attempts
        job.status = "running"
        job.sent = job.sent or 0
        job.failed = job.failed or 0
        await job.save()

    status_cb = _build_status_callback_url(request)

    # normalize FROM once
    ok_from, e164_from, from_err = _parse_to_e164(from_row.phone_number)
    if not ok_from:
        # config issue: mark whole job as failed-ish but continue per appt to log errors
        e164_from = None

    for appt in appointments:
        a = await _prefer_assistant_for_appt(db_user.id, appt, assistant)

        # validate destination before generating text
        ok_to, e164_to, to_err = _parse_to_e164(appt.phone)
        if not ok_to or not e164_from:
            await _store_record_outbound(
                job=job, user=db_user, assistant=a or assistant, appointment=appt,
                to_number=_sanitize_phone(appt.phone), from_number=_sanitize_phone(from_row.phone_number),
                body="", sid=None, success=False,
                error=f"{'invalid_from_number:'+from_err if not e164_from else ''}{' ' if (not e164_from and not ok_to) else ''}{'invalid_to_number:'+to_err if not ok_to else ''}".strip()
            )
            job.failed += 1
            continue

        user_message = (
            "Write a short SMS (max ~2 sentences) to remind about an appointment.\n"
            f"Title: {appt.title}\n"
            f"When: {_format_dt_local(appt.start_at, getattr(appt, 'timezone', None))}\n"
            "Tone: clear, friendly, professional.\n"
            "Constraints: Plain text only. No emojis, no headings, no code fences, no markdown.\n"
            "End with: 'Reply YES to confirm or NO to reschedule.'\n"
            "Output ONLY the message, no preface."
        )
        generated = await _generate_via_vapi_or_openai(
            system_prompt if not a else getattr(a, "systemPrompt", system_prompt),
            user_message,
            db_user
        )
        attempt_body = _compact_sms(generated or _fallback_appt_sms(appt))[:1000]

        for msg_ix in range(max(1, messages_per_recipient)):
            attempts_remaining = 1 + max(0, retry_count)
            while attempts_remaining > 0:
                try:
                    msg = await _twilio_send_message(
                        client=client,
                        body=attempt_body,
                        from_number=e164_from,
                        to_number=e164_to,
                        status_callback=status_cb,
                    )
                    await _store_record_outbound(
                        job=job, user=db_user, assistant=a or assistant, appointment=appt,
                        to_number=e164_to, from_number=e164_from,
                        body=attempt_body, sid=getattr(msg, "sid", None), success=True
                    )
                    job.sent += 1
                    break
                except Exception as e:
                    await _store_record_outbound(
                        job=job, user=db_user, assistant=a or assistant, appointment=appt,
                        to_number=e164_to, from_number=e164_from,
                        body=attempt_body, sid=None, success=False, error=str(e)
                    )
                    job.failed += 1
                    attempts_remaining -= 1
                    if attempts_remaining > 0:
                        await asyncio.sleep(max(0, retry_delay_seconds))
            if per_message_delay_seconds and msg_ix < max(1, messages_per_recipient) - 1:
                await asyncio.sleep(max(0, per_message_delay_seconds))

    job.status = "completed"
    await job.save()
    return str(job.id)

# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED / UNSCHEDULED
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/text/message-scheduled")
async def message_scheduled_appointments(
    request: Request,
    payload: MessageScheduledRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        db_user = await User.get(id=user.id)
        if payload.assistant_id:
            assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
            if not assistant:
                raise HTTPException(status_code=404, detail="Assistant not found")
        else:
            assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
            if not assistant:
                raise HTTPException(status_code=404, detail="No enabled assistant found")

        from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

        backoff_h = payload.repeat_backoff_hours if payload.repeat_backoff_hours is not None else _env_int("REPEAT_BACKOFF_HOURS", 7)

        appts = await _eligible_scheduled_appointments(
            db_user=db_user,
            include_unowned=bool(payload.include_unowned),
            backoff_hours=max(0, backoff_h),
        )
        if payload.limit and payload.limit > 0:
            appts = appts[: payload.limit]

        if not appts:
            total_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).count()
            total_user = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).count()
            return {
                "success": True,
                "sent": 0,
                "results": [],
                "detail": "No appointments eligible (likely due to backoff).",
                "stats": {
                    "total_scheduled_all": total_all,
                    "total_scheduled_for_user": total_user,
                    "include_unowned": bool(payload.include_unowned),
                    "repeat_backoff_hours": backoff_h,
                },
            }

        if payload.background is False:
            job_id = await _bulk_message_appointments_core(
                db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts,
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
            return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error messaging scheduled appointments: {e}")

@router.post("/text/message-unscheduled")
async def message_unscheduled_appointments(
    request: Request,
    payload: MessageScheduledRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        db_user = await User.get(id=user.id)
        if payload.assistant_id:
            assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
            if not assistant:
                raise HTTPException(status_code=404, detail="Assistant not found")
        else:
            assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
            if not assistant:
                raise HTTPException(status_code=404, detail="No enabled assistant found")

        from_row = await _resolve_from_number(db_user, assistant, payload.from_number)

        appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
        # effective unscheduled backoff hours
        if payload.unscheduled_backoff_hours is not None:
            backoff_h = max(0, payload.unscheduled_backoff_hours)
        else:
            env_unsched = _env_int("UNSCHEDULED_BACKOFF_HOURS", -1)
            backoff_h = env_unsched if env_unsched >= 0 else _env_int("REPEAT_BACKOFF_HOURS", 7)

        appts: List[Appointment] = []
        for a in appts_all:
            if backoff_h > 0:
                already = await _recent_success_outbound_exists(a.phone, db_user, backoff_h)
                if already:
                    continue
            appts.append(a)

        if payload.limit and payload.limit > 0:
            appts = appts[: payload.limit]

        if not appts:
            return {"success": True, "sent": 0, "results": []}

        if payload.background is False:
            job_id = await _bulk_message_appointments_core(
                db_user=db_user, request=request, assistant=assistant, from_row=from_row, appointments=appts,
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
            return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error messaging unscheduled appointments: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Debug (unchanged rule text)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/text/debug/scheduled-selection")
async def debug_scheduled_selection(
    include_unowned: bool = Query(default=True),
    repeat_backoff_hours: Optional[int] = Query(default=None, description="defaults to 7 via REPEAT_BACKOFF_HOURS"),
    user: Annotated[User, Depends(get_current_user)] = None,
):
    db_user = await User.get(id=user.id)
    backoff_h = repeat_backoff_hours if repeat_backoff_hours is not None else _env_int("REPEAT_BACKOFF_HOURS", 7)

    if include_unowned:
        appts_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).filter(
            Q(user=db_user) | Q(user_id=None)
        ).all()
    else:
        appts_all = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).all()

    eligible = []
    samples = []
    now = datetime.now(timezone.utc)

    for a in appts_all:
        recent = await _recent_success_outbound_exists(a.phone, db_user, backoff_h)
        ok = not recent
        if ok:
            eligible.append(a)
        samples.append({
            "id": str(a.id),
            "phone": a.phone,
            "tz": getattr(a, "timezone", None),
            "start_at": (a.start_at.replace(tzinfo=ZoneInfo(a.timezone)) if (a.start_at and getattr(a, "timezone", None)) else a.start_at),
            "now": now,
            "backoff_ok": ok,
            "eligible": ok,
        })

    info = {
        "total": len(appts_all),
        "eligible": len(eligible),
        "include_unowned": include_unowned,
        "repeat_backoff_hours": backoff_h,
        "rule": "Scheduled = eligible unless already messaged successfully within backoff window.",
    }
    logger.info(f"[debug] scheduled_selection: {info}")
    return {"info": info, "samples": samples[:50]}

# ─────────────────────────────────────────────────────────────────────────────
# Always-on Texting Daemons (scheduled & unscheduled)
# ─────────────────────────────────────────────────────────────────────────────

class _DaemonState:
    def __init__(self, *, enabled: bool, tick_interval_seconds: int, include_unowned: bool,
                 repeat_backoff_hours: int, unscheduled_backoff_hours: int):
        self.enabled = enabled
        self.tick_interval_seconds = tick_interval_seconds
        self.include_unowned = include_unowned
        self.repeat_backoff_hours = repeat_backoff_hours
        self.unscheduled_backoff_hours = unscheduled_backoff_hours

        # live metrics
        self.status: str = "idle"          # idle|running|paused|error
        self.last_tick_at: Optional[datetime] = None
        self.last_error: Optional[str] = None

        # last cycle
        self.last_queue_size: int = 0
        self.last_sent: int = 0
        self.last_failed: int = 0

        # cumulative (since process start)
        self.total_sent: int = 0
        self.total_failed: int = 0

DAEMONS: Dict[Kind, Dict[int, _DaemonState]] = {"scheduled": {}, "unscheduled": {}}
_DAEMON_TASKS: Dict[Kind, Optional[asyncio.Task]] = {"scheduled": None, "unscheduled": None}

def _get_default_state(kind: Kind) -> _DaemonState:
    return _DaemonState(
        enabled=True,
        tick_interval_seconds=_env_int("TEXTING_TICK_INTERVAL_SECONDS", 120),
        include_unowned=_env_bool("SCHEDULED_INCLUDE_UNOWNED", True),
        repeat_backoff_hours=_env_int("REPEAT_BACKOFF_HOURS", 7),
        unscheduled_backoff_hours=_env_int("UNSCHEDULED_BACKOFF_HOURS", _env_int("REPEAT_BACKOFF_HOURS", 7)),
    )

def _user_daemon_state(kind: Kind, user_id: int) -> _DaemonState:
    if user_id not in DAEMONS[kind]:
        DAEMONS[kind][user_id] = _get_default_state(kind)
    return DAEMONS[kind][user_id]

async def _users_with(kind: Kind) -> List[int]:
    if kind == "scheduled":
        ids = await Appointment.filter(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
    else:
        ids = await Appointment.exclude(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
    return [uid for uid in set(ids) if uid]

async def _daemon_tick_for_user(kind: Kind, uid: int):
    state = _user_daemon_state(kind, uid)
    if not state.enabled:
        state.status = "paused"
        return

    db_user = await User.get_or_none(id=uid)
    if not db_user:
        return

    try:
        state.status = "running"
        state.last_error = None
        state.last_sent = 0
        state.last_failed = 0
        state.last_queue_size = 0

        assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
        if not assistant:
            state.status = "idle"
            return
        from_row = await PurchasedNumber.filter(user=db_user, attached_assistant=assistant.id).first() \
                   or await PurchasedNumber.filter(user=db_user).first()
        if not from_row:
            state.status = "idle"
            return

        if kind == "scheduled":
            appts = await _eligible_scheduled_appointments(
                db_user=db_user,
                include_unowned=state.include_unowned,
                backoff_hours=max(0, state.repeat_backoff_hours),
            )
        else:
            appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
            appts = []
            bh = max(0, state.unscheduled_backoff_hours)
            for a in appts_all:
                if bh > 0 and await _recent_success_outbound_exists(a.phone, db_user, bh):
                    continue
                appts.append(a)

        state.last_queue_size = len(appts)
        if not appts:
            state.status = "idle"
            return

        job = await MessageJob.create(
            user=db_user, assistant=assistant, from_number=from_row.phone_number,
            status="running", total=len(appts), sent=0, failed=0
        )

        class _DummyReq:
            url = type("U", (), {"path": "/api/text/sms-status", "query": ""})()
        request_like = _DummyReq()

        await _bulk_message_appointments_core(
            db_user=db_user, request=request_like, assistant=assistant, from_row=from_row, appointments=appts, job=job,
            messages_per_recipient=1, retry_count=0, retry_delay_seconds=60, per_message_delay_seconds=0,
        )

        state.last_sent = job.sent or 0
        state.last_failed = job.failed or 0
        state.total_sent += state.last_sent
        state.total_failed += state.last_failed
        state.status = "idle"
    except Exception as e:
        state.last_error = str(e)
        state.status = "error"

    state.last_tick_at = datetime.now(timezone.utc)

async def _daemon_loop(kind: Kind):
    logger.info(f"[daemon] starting loop for {kind}")
    while True:
        try:
            user_ids = await _users_with(kind)
            for uid in user_ids:
                _user_daemon_state(kind, uid)
            for uid in user_ids:
                await _daemon_tick_for_user(kind, uid)

            if user_ids:
                intervals = [max(5, _user_daemon_state(kind, uid).tick_interval_seconds) for uid in user_ids]
                sleep_for = min(intervals) if intervals else _env_int("TEXTING_TICK_INTERVAL_SECONDS", 120)
            else:
                sleep_for = _env_int("TEXTING_TICK_INTERVAL_SECONDS", 120)
            await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            logger.info(f"[daemon] loop for {kind} cancelled")
            break
        except Exception as e:
            logger.exception(f"[daemon] loop error for {kind}: {e}")
            await asyncio.sleep(5)

def _start_daemon_if_needed(kind: Kind):
    if _DAEMON_TASKS[kind] is None or _DAEMON_TASKS[kind].done():
        _DAEMON_TASKS[kind] = asyncio.create_task(_daemon_loop(kind))

# ─────────────────────────────────────────────────────────────────────────────
# Daemon control + SSE
# ─────────────────────────────────────────────────────────────────────────────

def _make_daemon_token(user_id: int, kind: Kind, ttl_seconds: int = 600) -> str:
    exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    payload = {"id": user_id, "daemon_kind": kind, "kind": "daemon_sse", "exp": exp}
    return generate_user_token(payload)

def _validate_daemon_token(token: str, expected_kind: Kind) -> Optional[int]:
    try:
        claims = decode_user_token(token)
        if not isinstance(claims, dict): return None
        if claims.get("kind") != "daemon_sse": return None
        if claims.get("daemon_kind") != expected_kind: return None
        uid = claims.get("id")
        return uid if isinstance(uid, int) else None
    except Exception:
        return None

@router.get("/text/daemon/state")
async def get_daemon_state(
    kind: Kind = Query(...),
    user: Annotated[User, Depends(get_current_user)] = None,
):
    st = _user_daemon_state(kind, user.id)
    return {
        "kind": kind,
        "enabled": st.enabled,
        "status": st.status,
        "tick_interval_seconds": st.tick_interval_seconds,
        "include_unowned": st.include_unowned,
        "repeat_backoff_hours": st.repeat_backoff_hours,
        "unscheduled_backoff_hours": st.unscheduled_backoff_hours,
        "last_tick_at": st.last_tick_at,
        "last_error": st.last_error,
        "last_queue_size": st.last_queue_size,
        "last_sent": st.last_sent,
        "last_failed": st.last_failed,
        "total_sent": st.total_sent,
        "total_failed": st.total_failed,
        "sse_token": _make_daemon_token(user.id, kind),
    }

@router.put("/text/daemon/config")
async def update_daemon_config(
    payload: DaemonConfigRequest,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    st = _user_daemon_state(payload.kind, user.id)
    if payload.enabled is not None:
        st.enabled = bool(payload.enabled)
        st.status = "paused" if not st.enabled else "idle"
    if payload.tick_interval_seconds is not None:
        st.tick_interval_seconds = int(payload.tick_interval_seconds)
    if payload.kind == "scheduled":
        if payload.include_unowned is not None:
            st.include_unowned = bool(payload.include_unowned)
        if payload.repeat_backoff_hours is not None:
            st.repeat_backoff_hours = int(payload.repeat_backoff_hours)
    else:
        if payload.unscheduled_backoff_hours is not None:
            st.unscheduled_backoff_hours = int(payload.unscheduled_backoff_hours)

    _start_daemon_if_needed(payload.kind)
    return {"success": True, "state": await get_daemon_state(kind=payload.kind, user=user)}

@router.get("/text/daemon-progress-sse")
async def daemon_progress_sse(
    request: Request,
    kind: Kind = Query(...),
    token: Optional[str] = Query(default=None),
    sse: Optional[str] = Query(default=None),
):
    auth_user: Optional[User] = None
    try:
        if sse:
            uid = _validate_daemon_token(sse, kind)
            if uid is not None:
                auth_user = await User.get_or_none(id=uid)
        if not auth_user:
            auth_header = request.headers.get("Authorization")
            raw = None
            if auth_header and auth_header.lower().startswith("bearer "):
                raw = auth_header.split(" ", 1)[1]
            elif token:
                raw = token
            else:
                raw = request.cookies.get("token") or request.cookies.get("access_token") or request.cookies.get("Authorization")
            if raw:
                creds = decode_user_token(raw)
                uid = creds.get("id") if isinstance(creds, dict) else None
                if uid is not None:
                    auth_user = await User.get_or_none(id=uid)
    except Exception:
        auth_user = None

    if not auth_user:
        raise HTTPException(status_code=403, detail="Not authenticated")

    _start_daemon_if_needed(kind)

    async def event_stream() -> AsyncGenerator[bytes, None]:
        last: Dict[str, Any] = {}
        while True:
            if await request.is_disconnected():
                break
            st = _user_daemon_state(kind, auth_user.id)
            payload = {
                "kind": kind,
                "enabled": st.enabled,
                "status": st.status,
                "tick_interval_seconds": st.tick_interval_seconds,
                "include_unowned": st.include_unowned,
                "repeat_backoff_hours": st.repeat_backoff_hours,
                "unscheduled_backoff_hours": st.unscheduled_backoff_hours,
                "last_tick_at": st.last_tick_at.isoformat() if st.last_tick_at else None,
                "last_error": st.last_error,
                "last_queue_size": st.last_queue_size,
                "last_sent": st.last_sent,
                "last_failed": st.last_failed,
                "total_sent": st.total_sent,
                "total_failed": st.total_failed,
            }
            if payload != last:
                yield f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")
                last = payload
            await asyncio.sleep(1.0)

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream", "Connection": "keep-alive"}
    return StreamingResponse(event_stream(), headers=headers)

# ─────────────────────────────────────────────────────────────────────────────
# Scheduler wiring
# ─────────────────────────────────────────────────────────────────────────────

async def run_texting_job():
    for uid in await _users_with("scheduled"):
        await _daemon_tick_for_user("scheduled", uid)

async def run_unscheduled_texting_job():
    for uid in await _users_with("unscheduled"):
        await _daemon_tick_for_user("unscheduled", uid)

def schedule_texting_job(timezone: str = "UTC"):
    """
    Start long-running daemon loops once at startup. Keep periodic nudges for resiliency.
    """
    nudge_once(lambda: _start_daemon_if_needed("scheduled"), delay_seconds=0)
    nudge_once(lambda: _start_daemon_if_needed("unscheduled"), delay_seconds=0)
    schedule_minutely_job("texting-daemon-nudge-scheduled", timezone, lambda: _start_daemon_if_needed("scheduled"))
    schedule_minutely_job("texting-daemon-nudge-unscheduled", timezone, lambda: _start_daemon_if_needed("unscheduled"))
