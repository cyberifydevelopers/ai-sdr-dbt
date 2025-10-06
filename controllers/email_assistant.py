# # controllers/email_assistant.py
# from __future__ import annotations
# import os
# import re
# import json
# import asyncio
# import logging
# from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator, Literal
# from datetime import datetime, timedelta, timezone
# from zoneinfo import ZoneInfo

# from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Query, Form
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel, Field
# from starlette.concurrency import run_in_threadpool
# from tortoise.expressions import Q
# from models.auth import User
# from models.assistant import Assistant
# from models.appointment import Appointment, AppointmentStatus
# from models.email import EmailCredential, EmailJob, EmailRecord
# from helpers.token_helper import get_current_user, decode_user_token, generate_user_token
# from helpers.vapi_helper import get_headers  

# import smtplib
# from email.message import EmailMessage

# router = APIRouter()
# logger = logging.getLogger("email_assistant")
# if not logger.handlers:
#     h = logging.StreamHandler()
#     h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
#     logger.addHandler(h)
# logger.setLevel(logging.INFO)

# Kind = Literal["scheduled", "unscheduled"]

# # ─────────────────────────────────────────────────────────────────────────────
# # Helpers (env, OpenAI, VAPI)
# # ─────────────────────────────────────────────────────────────────────────────

# def _env_bool(name: str, default: bool = False) -> bool:
#     v = os.getenv(name)
#     if v is None: return default
#     return str(v).strip().lower() in ("1","true","y","yes","on")

# def _env_int(name: str, default: int) -> int:
#     try:
#         return int(os.getenv(name, str(default)))
#     except Exception:
#         return default

# def _sanitize_email(s: Optional[str]) -> str:
#     return (s or "").strip()

# EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# async def _generate_via_vapi_or_openai(system_prompt: str, user_message: str, user: Optional[User] = None) -> Optional[str]:
#     vapi_url = os.getenv("VAPI_URL")
#     if vapi_url:
#         try:
#             headers = get_headers(user=user)
#             import httpx
#             async with httpx.AsyncClient(timeout=30) as client:
#                 res = await client.post(
#                     f"{vapi_url.rstrip('/')}/v1/chat/completions",
#                     headers=headers,
#                     json={
#                         "model": os.getenv("VAPI_MODEL", "gpt-4o-mini"),
#                         "temperature": 0.4,
#                         "messages": [{"role":"system","content":system_prompt},{"role":"user","content":user_message}],
#                     },
#                 )
#                 res.raise_for_status()
#                 data = res.json()
#                 text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
#                 if text: return text
#         except Exception:
#             pass

#     # OpenAI fallback
#     try:
#         api_key = os.getenv("OPENAI_API_KEY")
#         if not api_key: return None
#         try:
#             from openai import OpenAI
#             client = OpenAI(api_key=api_key)
#             resp = client.chat.completions.create(
#                 model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
#                 temperature=0.4,
#                 messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_message}],
#             )
#             return (resp.choices[0].message.content or "").strip()
#         except Exception:
#             import openai
#             openai.api_key = api_key
#             resp = openai.ChatCompletion.create(
#                 model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
#                 temperature=0.4,
#                 messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_message}],
#             )
#             return (resp["choices"][0]["message"]["content"] or "").strip()
#     except Exception:
#         return None

# # ─────────────────────────────────────────────────────────────────────────────
# # SMTP sending
# # ─────────────────────────────────────────────────────────────────────────────

# async def _smtp_send(
#     *,
#     cred: EmailCredential,
#     subject: str,
#     body: str,
#     from_email: str,
#     to_email: str,
# ) -> Tuple[bool, Optional[str], Optional[str]]:
#     """
#     Returns (ok, provider_message_id, error)
#     """
#     def _send() -> Tuple[bool, Optional[str], Optional[str]]:
#         try:
#             msg = EmailMessage()
#             msg["Subject"] = subject
#             msg["From"] = from_email
#             msg["To"] = to_email
#             msg.set_content(body)
#             if cred.smtp_use_tls:
#                 with smtplib.SMTP(cred.smtp_host, cred.smtp_port) as s:
#                     s.starttls()
#                     if cred.smtp_username:
#                         s.login(cred.smtp_username, cred.smtp_password or "")
#                     r = s.send_message(msg)
#             else:
#                 with smtplib.SMTP(cred.smtp_host, cred.smtp_port) as s:
#                     if cred.smtp_username:
#                         s.login(cred.smtp_username, cred.smtp_password or "")
#                     r = s.send_message(msg)
#             # r is a dict of failures {rcpt: err}; empty means ok
#             if isinstance(r, dict) and len(r) > 0:
#                 return (False, None, json.dumps(r))
#             # try to surface message-id if any
#             mid = msg.get("Message-Id")
#             return (True, mid, None)
#         except Exception as e:
#             return (False, None, str(e))
#     return await run_in_threadpool(_send)

# async def _get_credential_for_user(user: User) -> EmailCredential:
#     cred = await EmailCredential.filter(user=user).first()
#     if not cred:
#         # As a convenience, allow env-level SMTP if no row found
#         host = os.getenv("SMTP_HOST")
#         if not host:
#             raise HTTPException(status_code=400, detail="No EmailCredential configured for user (and no SMTP_HOST in env).")
#         cred = EmailCredential(
#             user=user,
#             provider="smtp",
#             api_key=None,
#             smtp_host=host,
#             smtp_port=int(os.getenv("SMTP_PORT", "587")),
#             smtp_username=os.getenv("SMTP_USERNAME"),
#             smtp_password=os.getenv("SMTP_PASSWORD"),
#             smtp_use_tls=_env_bool("SMTP_USE_TLS", True),
#             from_email=os.getenv("SMTP_FROM_EMAIL"),
#         )
#     return cred

# # ─────────────────────────────────────────────────────────────────────────────
# # Backoff / selection (mirrors texting; uses appointment.email)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _recent_success_email_exists(email: str, user: User, within_hours: int) -> bool:
#     if not email:
#         return False
#     since = datetime.now(timezone.utc) - timedelta(hours=max(0, within_hours))
#     return await EmailRecord.filter(user=user, to_email=email, success=True, created_at__gte=since).exists()

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
#         email = getattr(a, "email", None)
#         if not email or not EMAIL_RE.match(email.strip()):
#             continue
#         already = await _recent_success_email_exists(email, db_user, backoff_hours)
#         if already:
#             continue
#         result.append(a)
#     return result

# # ─────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ─────────────────────────────────────────────────────────────────────────────

# class SendEmailRequest(BaseModel):
#     to_email: str
#     subject: str
#     body: str
#     from_email: Optional[str] = None  # override default from credential

# class EmailScheduledRequest(BaseModel):
#     assistant_id: Optional[int] = None
#     from_email: Optional[str] = None
#     limit: Optional[int] = None
#     background: Optional[bool] = True

#     messages_per_recipient: Optional[int] = Field(default=1, ge=1, le=5)
#     retry_count: Optional[int] = Field(default=0, ge=0, le=3)
#     retry_delay_seconds: Optional[int] = Field(default=60, ge=5, le=3600)
#     per_message_delay_seconds: Optional[int] = Field(default=0, ge=0, le=3600)

#     include_unowned: Optional[bool] = Field(default=True)
#     repeat_backoff_hours: Optional[int] = Field(default=None)
#     unscheduled_backoff_hours: Optional[int] = Field(default=None)

# # ─────────────────────────────────────────────────────────────────────────────
# # Storing records
# # ─────────────────────────────────────────────────────────────────────────────

# async def _store_email_outbound(
#     *,
#     job: Optional[EmailJob],
#     user: User,
#     assistant: Optional[Assistant],
#     appointment: Optional[Appointment],
#     to_email: str,
#     from_email: Optional[str],
#     subject: Optional[str],
#     body: str,
#     provider_message_id: Optional[str],
#     success: bool,
#     error: Optional[str] = None,
# ):
#     if job is None:
#         job = await EmailJob.create(
#             user=user,
#             assistant=assistant,
#             from_email=from_email,
#             subject_template=subject,
#             status="completed",
#             total=1,
#             sent=1 if success else 0,
#             failed=0 if success else 1,
#         )
#     await EmailRecord.create(
#         job=job,
#         user=user,
#         assistant=assistant,
#         appointment=appointment,
#         to_email=to_email,
#         from_email=from_email,
#         subject=(subject or "")[:255] if subject else None,
#         body=(body or "")[:10000],
#         provider_message_id=provider_message_id,
#         success=success,
#         error=error,
#     )

# # ─────────────────────────────────────────────────────────────────────────────
# # Single send
# # ─────────────────────────────────────────────────────────────────────────────

# @router.post("/email/send")
# async def send_email(payload: SendEmailRequest, user: User = Depends(get_current_user)):
#     email = _sanitize_email(payload.to_email)
#     if not EMAIL_RE.match(email):
#         raise HTTPException(status_code=400, detail="Invalid to_email")
#     subject = (payload.subject or "").strip() or "(no subject)"
#     body = (payload.body or "").strip()
#     if not body:
#         raise HTTPException(status_code=400, detail="Empty body")

#     cred = await _get_credential_for_user(user)
#     from_email = (payload.from_email or cred.from_email or "").strip()
#     if not from_email:
#         raise HTTPException(status_code=400, detail="Missing from_email (set default in EmailCredential or payload)")

#     ok, mid, err = await _smtp_send(cred=cred, subject=subject, body=body, from_email=from_email, to_email=email)
#     await _store_email_outbound(
#         job=None, user=user, assistant=None, appointment=None,
#         to_email=email, from_email=from_email, subject=subject, body=body,
#         provider_message_id=mid, success=ok, error=err
#     )
#     if not ok:
#         raise HTTPException(status_code=400, detail=f"Send failed: {err}")
#     return {"success": True, "message_id": mid}

# # ─────────────────────────────────────────────────────────────────────────────
# # Bulk engine (appointments)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _assistant_for_appt(user_id: int, appt: Appointment, default_assistant: Optional[Assistant]) -> Optional[Assistant]:
#     try:
#         if getattr(appt, "assistant_id", None):
#             return await Assistant.get_or_none(id=appt.assistant_id, user_id=user_id)
#     except Exception:
#         pass
#     return default_assistant

# async def _bulk_email_appointments_core(
#     *,
#     db_user: User,
#     assistant: Assistant,
#     from_email: str,
#     cred: EmailCredential,
#     appointments: List[Appointment],
#     job: Optional[EmailJob] = None,
#     messages_per_recipient: int = 1,
#     retry_count: int = 0,
#     retry_delay_seconds: int = 60,
#     per_message_delay_seconds: int = 0,
# ) -> str:
#     system_prompt = getattr(assistant, "systemPrompt", None) or "You are a helpful email assistant. Keep messages short, clear and friendly."

#     total_attempts = len(appointments) * max(1, messages_per_recipient) * (1 + max(0, retry_count))
#     if job is None:
#         job = await EmailJob.create(
#             user=db_user, assistant=assistant, from_email=from_email,
#             status="running", total=total_attempts, sent=0, failed=0
#         )
#     else:
#         job.total = total_attempts
#         job.status = "running"
#         job.sent = job.sent or 0
#         job.failed = job.failed or 0
#         await job.save()

#     for appt in appointments:
#         a = await _assistant_for_appt(db_user.id, appt, assistant)

#         user_message = (
#             "Write a concise, friendly appointment email.\n"
#             f"Title: {appt.title}\n"
#             f"When: {appt.start_at.isoformat()} ({appt.timezone})\n"
#             "Ask them to reply YES to confirm or suggest a better time.\n"
#         )
#         generated = await _generate_via_vapi_or_openai(
#             system_prompt if not a else getattr(a, "systemPrompt", system_prompt),
#             user_message,
#             db_user
#         ) or f"Hi! This is a reminder for '{appt.title}' on {appt.start_at.isoformat()} ({appt.timezone}). Please reply YES to confirm or suggest another time."

#         subject = f"Reminder: {appt.title} on {appt.start_at.strftime('%b %d, %Y %I:%M %p %Z')}"
#         recipient = (getattr(appt, "email", None) or "").strip()

#         for msg_ix in range(max(1, messages_per_recipient)):
#             attempt_body = generated[:10000]
#             attempts_remaining = 1 + max(0, retry_count)
#             while attempts_remaining > 0:
#                 try:
#                     ok, mid, err = await _smtp_send(
#                         cred=cred, subject=subject, body=attempt_body, from_email=from_email, to_email=recipient
#                     )
#                     await _store_email_outbound(
#                         job=job, user=db_user, assistant=a or assistant, appointment=appt,
#                         to_email=recipient, from_email=from_email, subject=subject, body=attempt_body,
#                         provider_message_id=mid, success=ok, error=err
#                     )
#                     if ok:
#                         job.sent += 1
#                         break
#                     else:
#                         job.failed += 1
#                         attempts_remaining -= 1
#                         if attempts_remaining > 0:
#                             await asyncio.sleep(max(0, retry_delay_seconds))
#                 except Exception as e:
#                     await _store_email_outbound(
#                         job=job, user=db_user, assistant=a or assistant, appointment=appt,
#                         to_email=recipient, from_email=from_email, subject=subject, body=attempt_body,
#                         provider_message_id=None, success=False, error=str(e)
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
# # Public endpoints (list, jobs, sse, scheduled/unscheduled)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.get("/email/messages")
# async def list_email_messages(
#     limit: int = 100,
#     offset: int = 0,
#     success: Optional[bool] = None,
#     job_id: Optional[str] = None,
#     assistant_id: Optional[int] = None,
#     to_like: Optional[str] = None,
#     from_like: Optional[str] = None,
#     start: Optional[str] = None,
#     end: Optional[str] = None,
#     user: User = Depends(get_current_user),
# ):
#     q = EmailRecord.filter(user=user).order_by("-created_at")
#     if success is not None: q = q.filter(success=success)
#     if job_id: q = q.filter(job_id=job_id)
#     if assistant_id: q = q.filter(assistant_id=assistant_id)
#     if to_like: q = q.filter(to_email__icontains=to_like)
#     if from_like: q = q.filter(from_email__icontains=from_like)
#     if start:
#         try: q = q.filter(created_at__gte=datetime.fromisoformat(start))
#         except Exception: pass
#     if end:
#         try: q = q.filter(created_at__lte=datetime.fromisoformat(end))
#         except Exception: pass

#     total = await q.count()
#     rows = await q.offset(offset).limit(limit)
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
#                 "from_email": r.from_email,
#                 "to_email": r.to_email,
#                 "subject": r.subject,
#                 "provider_message_id": r.provider_message_id,
#                 "success": r.success,
#                 "error": r.error,
#                 "created_at": r.created_at,
#             } for r in rows
#         ],
#     }

# @router.get("/email/jobs")
# async def list_email_jobs(
#     limit: int = 50,
#     offset: int = 0,
#     status: Optional[str] = None,
#     user: User = Depends(get_current_user),
# ):
#     q = EmailJob.filter(user=user).order_by("-created_at")
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
#                 "from_email": j.from_email,
#                 "assistant_id": j.assistant_id,
#                 "subject_template": j.subject_template,
#                 "total": j.total,
#                 "sent": j.sent,
#                 "failed": j.failed,
#                 "created_at": j.created_at,
#             } for j in rows
#         ],
#     }

# @router.get("/email/job/{job_id}")
# async def get_email_job(job_id: str, user: User = Depends(get_current_user)):
#     job = await EmailJob.get_or_none(id=job_id, user=user)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")
#     success_count = await EmailRecord.filter(job=job, success=True).count()
#     fail_count = await EmailRecord.filter(job=job, success=False).count()
#     return {
#         "id": str(job.id),
#         "status": job.status,
#         "from_email": job.from_email,
#         "assistant_id": job.assistant_id,
#         "subject_template": job.subject_template,
#         "total": job.total,
#         "sent": job.sent,
#         "failed": job.failed,
#         "success_count": success_count,
#         "fail_count": fail_count,
#         "created_at": job.created_at,
#     }

# # ─────────────────────────────────────────────────────────────────────────────
# # SSE for a single job (same shape as SMS)
# # ─────────────────────────────────────────────────────────────────────────────

# def _make_sse_token(user_id: int, job_id: str, ttl_seconds: int = 600) -> str:
#     exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
#     payload = {"id": user_id, "job_id": job_id, "kind": "email_sse", "exp": exp}
#     return generate_user_token(payload)

# def _validate_sse_token(token: str, expected_job_id: str) -> Optional[int]:
#     try:
#         claims = decode_user_token(token)
#         if not isinstance(claims, dict): return None
#         if claims.get("kind") != "email_sse": return None
#         if claims.get("job_id") != expected_job_id: return None
#         uid = claims.get("id")
#         return uid if isinstance(uid, int) else None
#     except Exception:
#         return None

# @router.get("/email/job-progress-sse")
# async def email_job_progress_sse(
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
#             job = await EmailJob.get_or_none(id=job_id, user=auth_user)
#             if not job:
#                 yield b"event: done\ndata: {\"error\":\"not_found\"}\n\n"
#                 break
#             payload = {
#                 "id": str(job.id),
#                 "status": job.status,
#                 "total": job.total,
#                 "sent": job.sent,
#                 "failed": job.failed,
#                 "from_email": job.from_email,
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
# # Scheduled / Unscheduled endpoints (background or blocking)
# # ─────────────────────────────────────────────────────────────────────────────

# @router.post("/email/message-scheduled")
# async def email_message_scheduled(
#     payload: EmailScheduledRequest,
#     background_tasks: BackgroundTasks,
#     user: User = Depends(get_current_user),
# ):
#     db_user = await User.get(id=user.id)

#     if payload.assistant_id:
#         assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")
#     else:
#         assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#         if not assistant:
#             raise HTTPException(status_code=404, detail="No enabled assistant found")

#     cred = await _get_credential_for_user(db_user)
#     from_email = (payload.from_email or cred.from_email or "").strip()
#     if not from_email:
#         raise HTTPException(status_code=400, detail="Missing from_email (set default in EmailCredential or payload)")

#     backoff_h = payload.repeat_backoff_hours if payload.repeat_backoff_hours is not None else _env_int("REPEAT_BACKOFF_HOURS", 7)

#     appts = await _eligible_scheduled_appointments(
#         db_user=db_user,
#         include_unowned=bool(payload.include_unowned),
#         backoff_hours=max(0, backoff_h),
#     )
#     if payload.limit and payload.limit > 0:
#         appts = appts[: payload.limit]

#     if not appts:
#         total_all = await Appointment.filter(status=AppointmentStatus.SCHEDULED).count()
#         total_user = await Appointment.filter(user=db_user, status=AppointmentStatus.SCHEDULED).count()
#         return {
#             "success": True,
#             "sent": 0,
#             "results": [],
#             "detail": "No eligible scheduled appointments (likely backoff or missing emails).",
#             "stats": {
#                 "total_scheduled_all": total_all,
#                 "total_scheduled_for_user": total_user,
#                 "include_unowned": bool(payload.include_unowned),
#                 "repeat_backoff_hours": backoff_h,
#             },
#         }

#     if payload.background is False:
#         job_id = await _bulk_email_appointments_core(
#             db_user=db_user, assistant=assistant, from_email=from_email, cred=cred, appointments=appts,
#             messages_per_recipient=payload.messages_per_recipient or 1,
#             retry_count=payload.retry_count or 0,
#             retry_delay_seconds=payload.retry_delay_seconds or 60,
#             per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#         )
#         return {"success": True, "job_id": job_id}
#     else:
#         pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
#         job = await EmailJob.create(
#             user=db_user, assistant=assistant, from_email=from_email,
#             status="running", total=pre_total, sent=0, failed=0
#         )
#         background_tasks.add_task(
#             _bulk_email_appointments_core,
#             db_user=db_user, assistant=assistant, from_email=from_email, cred=cred, appointments=appts, job=job,
#             messages_per_recipient=payload.messages_per_recipient or 1,
#             retry_count=payload.retry_count or 0,
#             retry_delay_seconds=payload.retry_delay_seconds or 60,
#             per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#         )
#         sse_token = _make_sse_token(db_user.id, str(job.id))
#         return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}

# @router.post("/email/message-unscheduled")
# async def email_message_unscheduled(
#     payload: EmailScheduledRequest,
#     background_tasks: BackgroundTasks,
#     user: User = Depends(get_current_user),
# ):
#     db_user = await User.get(id=user.id)

#     if payload.assistant_id:
#         assistant = await Assistant.get_or_none(id=payload.assistant_id, user=db_user)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")
#     else:
#         assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#         if not assistant:
#             raise HTTPException(status_code=404, detail="No enabled assistant found")

#     cred = await _get_credential_for_user(db_user)
#     from_email = (payload.from_email or cred.from_email or "").strip()
#     if not from_email:
#         raise HTTPException(status_code=400, detail="Missing from_email (set default in EmailCredential or payload)")

#     appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
#     # effective unscheduled backoff
#     if payload.unscheduled_backoff_hours is not None:
#         backoff_h = max(0, payload.unscheduled_backoff_hours)
#     else:
#         env_unsched = _env_int("UNSCHEDULED_BACKOFF_HOURS", -1)
#         backoff_h = env_unsched if env_unsched >= 0 else _env_int("REPEAT_BACKOFF_HOURS", 7)

#     appts: List[Appointment] = []
#     for a in appts_all:
#         email = (getattr(a, "email", None) or "").strip()
#         if not email or not EMAIL_RE.match(email):
#             continue
#         if backoff_h > 0 and await _recent_success_email_exists(email, db_user, backoff_h):
#             continue
#         appts.append(a)

#     if payload.limit and payload.limit > 0:
#         appts = appts[: payload.limit]

#     if not appts:
#         return {"success": True, "sent": 0, "results": []}

#     if payload.background is False:
#         job_id = await _bulk_email_appointments_core(
#             db_user=db_user, assistant=assistant, from_email=from_email, cred=cred, appointments=appts,
#             messages_per_recipient=payload.messages_per_recipient or 1,
#             retry_count=payload.retry_count or 0,
#             retry_delay_seconds=payload.retry_delay_seconds or 60,
#             per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#         )
#         return {"success": True, "job_id": job_id}
#     else:
#         pre_total = len(appts) * max(1, payload.messages_per_recipient or 1) * (1 + max(0, payload.retry_count or 0))
#         job = await EmailJob.create(
#             user=db_user, assistant=assistant, from_email=from_email,
#             status="running", total=pre_total, sent=0, failed=0
#         )
#         background_tasks.add_task(
#             _bulk_email_appointments_core,
#             db_user=db_user, assistant=assistant, from_email=from_email, cred=cred, appointments=appts, job=job,
#             messages_per_recipient=payload.messages_per_recipient or 1,
#             retry_count=payload.retry_count or 0,
#             retry_delay_seconds=payload.retry_delay_seconds or 60,
#             per_message_delay_seconds=payload.per_message_delay_seconds or 0,
#         )
#         sse_token = _make_sse_token(db_user.id, str(job.id))
#         return {"success": True, "job_id": str(job.id), "sse_token": sse_token, "detail": "Background job started"}

# # ─────────────────────────────────────────────────────────────────────────────
# # Always-on daemons (scheduled/unscheduled), mirroring your SMS setup
# # ─────────────────────────────────────────────────────────────────────────────

# class _DaemonState:
#     def __init__(self, *, enabled: bool, tick_interval_seconds: int,
#                  include_unowned: bool, repeat_backoff_hours: int, unscheduled_backoff_hours: int):
#         self.enabled = enabled
#         self.tick_interval_seconds = tick_interval_seconds
#         self.include_unowned = include_unowned
#         self.repeat_backoff_hours = repeat_backoff_hours
#         self.unscheduled_backoff_hours = unscheduled_backoff_hours

#         self.status: str = "idle"   # idle|running|paused|error
#         self.last_tick_at: Optional[datetime] = None
#         self.last_error: Optional[str] = None

#         self.last_queue_size: int = 0
#         self.last_sent: int = 0
#         self.last_failed: int = 0

#         self.total_sent: int = 0
#         self.total_failed: int = 0

# DAEMONS: Dict[Kind, Dict[int, _DaemonState]] = {"scheduled": {}, "unscheduled": {}}
# _DAEMON_TASKS: Dict[Kind, Optional[asyncio.Task]] = {"scheduled": None, "unscheduled": None}

# def _default_state(kind: Kind) -> _DaemonState:
#     return _DaemonState(
#         enabled=True,
#         tick_interval_seconds=_env_int("EMAIL_TICK_INTERVAL_SECONDS", 180),
#         include_unowned=_env_bool("SCHEDULED_INCLUDE_UNOWNED", True),
#         repeat_backoff_hours=_env_int("REPEAT_BACKOFF_HOURS", 7),
#         unscheduled_backoff_hours=_env_int("UNSCHEDULED_BACKOFF_HOURS", _env_int("REPEAT_BACKOFF_HOURS", 7)),
#     )

# def _state(kind: Kind, uid: int) -> _DaemonState:
#     if uid not in DAEMONS[kind]:
#         DAEMONS[kind][uid] = _default_state(kind)
#     return DAEMONS[kind][uid]

# async def _users_with(kind: Kind) -> List[int]:
#     if kind == "scheduled":
#         ids = await Appointment.filter(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
#     else:
#         ids = await Appointment.exclude(status=AppointmentStatus.SCHEDULED).values_list("user_id", flat=True)
#     return [i for i in set(ids) if i]

# async def _tick_user(kind: Kind, uid: int):
#     st = _state(kind, uid)
#     if not st.enabled:
#         st.status = "paused"
#         return

#     db_user = await User.get_or_none(id=uid)
#     if not db_user:
#         return
#     try:
#         st.status = "running"
#         st.last_error = None
#         st.last_sent = 0
#         st.last_failed = 0
#         st.last_queue_size = 0

#         assistant = await Assistant.filter(user=db_user, assistant_toggle=True).first()
#         if not assistant:
#             st.status = "idle"
#             return

#         cred = await _get_credential_for_user(db_user)
#         from_email = (cred.from_email or "").strip()
#         if not from_email:
#             st.status = "idle"
#             st.last_error = "missing from_email"
#             return

#         if kind == "scheduled":
#             appts = await _eligible_scheduled_appointments(
#                 db_user=db_user,
#                 include_unowned=st.include_unowned,
#                 backoff_hours=max(0, st.repeat_backoff_hours),
#             )
#         else:
#             appts_all = await Appointment.filter(user=db_user).exclude(status=AppointmentStatus.SCHEDULED).all()
#             appts = []
#             bh = max(0, st.unscheduled_backoff_hours)
#             for a in appts_all:
#                 em = (getattr(a, "email", None) or "").strip()
#                 if not em or not EMAIL_RE.match(em):
#                     continue
#                 if bh > 0 and await _recent_success_email_exists(em, db_user, bh):
#                     continue
#                 appts.append(a)

#         st.last_queue_size = len(appts)
#         if not appts:
#             st.status = "idle"
#             return

#         job = await EmailJob.create(
#             user=db_user, assistant=assistant, from_email=from_email,
#             status="running", total=len(appts), sent=0, failed=0
#         )

#         await _bulk_email_appointments_core(
#             db_user=db_user, assistant=assistant, from_email=from_email, cred=cred, appointments=appts, job=job,
#             messages_per_recipient=1, retry_count=0, retry_delay_seconds=60, per_message_delay_seconds=0,
#         )

#         st.last_sent = job.sent or 0
#         st.last_failed = job.failed or 0
#         st.total_sent += st.last_sent
#         st.total_failed += st.last_failed
#         st.status = "idle"
#     except Exception as e:
#         st.last_error = str(e)
#         st.status = "error"
#     st.last_tick_at = datetime.now(timezone.utc)

# async def _daemon_loop(kind: Kind):
#     logger.info(f"[email-daemon] starting loop for {kind}")
#     while True:
#         try:
#             users = await _users_with(kind)
#             for uid in users:
#                 _state(kind, uid)  # ensure state exists
#             for uid in users:
#                 await _tick_user(kind, uid)

#             if users:
#                 intervals = [max(5, _state(kind, u).tick_interval_seconds) for u in users]
#                 sleep_for = min(intervals) if intervals else _env_int("EMAIL_TICK_INTERVAL_SECONDS", 180)
#             else:
#                 sleep_for = _env_int("EMAIL_TICK_INTERVAL_SECONDS", 180)
#             await asyncio.sleep(sleep_for)
#         except asyncio.CancelledError:
#             logger.info(f"[email-daemon] loop for {kind} cancelled")
#             break
#         except Exception as e:
#             logger.exception(f"[email-daemon] loop error for {kind}: {e}")
#             await asyncio.sleep(5)

# def _start_daemon_if_needed(kind: Kind):
#     if _DAEMON_TASKS[kind] is None or _DAEMON_TASKS[kind].done():
#         _DAEMON_TASKS[kind] = asyncio.create_task(_daemon_loop(kind))

# # Control + SSE
# class DaemonConfigRequest(BaseModel):
#     kind: Kind
#     enabled: Optional[bool] = None
#     tick_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
#     include_unowned: Optional[bool] = None
#     repeat_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)
#     unscheduled_backoff_hours: Optional[int] = Field(default=None, ge=0, le=72)

# def _make_daemon_token(user_id: int, kind: Kind, ttl_seconds: int = 600) -> str:
#     exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
#     payload = {"id": user_id, "daemon_kind": kind, "kind": "email_daemon_sse", "exp": exp}
#     return generate_user_token(payload)

# def _validate_daemon_token(token: str, expected_kind: Kind) -> Optional[int]:
#     try:
#         claims = decode_user_token(token)
#         if not isinstance(claims, dict): return None
#         if claims.get("kind") != "email_daemon_sse": return None
#         if claims.get("daemon_kind") != expected_kind: return None
#         uid = claims.get("id")
#         return uid if isinstance(uid, int) else None
#     except Exception:
#         return None

# @router.get("/email/daemon/state")
# async def get_email_daemon_state(kind: Kind = Query(...), user: User = Depends(get_current_user)):
#     st = _state(kind, user.id)
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

# @router.put("/email/daemon/config")
# async def update_email_daemon_config(payload: DaemonConfigRequest, user: User = Depends(get_current_user)):
#     st = _state(payload.kind, user.id)
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

#     _start_daemon_if_needed(payload.kind)
#     return {"success": True, "state": await get_email_daemon_state(kind=payload.kind, user=user)}

# @router.get("/email/daemon-progress-sse")
# async def email_daemon_progress_sse(
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

#     _start_daemon_if_needed(kind)

#     async def event_stream() -> AsyncGenerator[bytes, None]:
#         last: Dict[str, Any] = {}
#         while True:
#             if await request.is_disconnected():
#                 break
#             st = _state(kind, auth_user.id)
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
# # Scheduler wiring (compat)
# # ─────────────────────────────────────────────────────────────────────────────

# async def run_email_job():
#     for uid in await _users_with("scheduled"):
#         await _tick_user("scheduled", uid)

# async def run_unscheduled_email_job():
#     for uid in await _users_with("unscheduled"):
#         await _tick_user("unscheduled", uid)

# def schedule_email_job(timezone: str = "UTC"):
#     # start long-running loops; keep a periodic nudge for resiliency
#     from scheduler.campaign_scheduler import schedule_minutely_job, nudge_once
#     nudge_once(lambda: _start_daemon_if_needed("scheduled"), delay_seconds=0)
#     nudge_once(lambda: _start_daemon_if_needed("unscheduled"), delay_seconds=0)
#     schedule_minutely_job("email-daemon-nudge-scheduled", timezone, lambda: _start_daemon_if_needed("scheduled"))
#     schedule_minutely_job("email-daemon-nudge-unscheduled", timezone, lambda: _start_daemon_if_needed("unscheduled"))





# # --- Credentials schemas & helpers ------------------------------------------
# class EmailCredentialUpsertRequest(BaseModel):
#     provider: Optional[str] = Field(default="smtp")   # keep "smtp" for now
#     from_email: str

#     smtp_host: str
#     smtp_port: int = 587
#     smtp_username: Optional[str] = None
#     smtp_password: Optional[str] = None
#     smtp_use_tls: bool = True

# def _mask(s: Optional[str], keep: int = 2) -> Optional[str]:
#     if not s:
#         return s
#     if len(s) <= keep:
#         return "*" * len(s)
#     return s[:keep] + "*" * (len(s) - keep)

# async def _serialize_cred_masked(cred: EmailCredential) -> Dict[str, Any]:
#     return {
#         "id": cred.id,
#         "provider": cred.provider,
#         "from_email": cred.from_email,
#         "smtp_host": cred.smtp_host,
#         "smtp_port": cred.smtp_port,
#         "smtp_username": _mask(cred.smtp_username, 2),
#         # never return raw password
#         "smtp_password": "********" if cred.smtp_password else None,
#         "smtp_use_tls": cred.smtp_use_tls,
#         "created_at": cred.created_at,
#         "updated_at": cred.updated_at,
#     }


# async def _validate_smtp_connection(
#     *,
#     host: str,
#     port: int,
#     username: Optional[str],
#     password: Optional[str],
#     use_tls: bool
# ) -> None:
#     """Raises HTTPException if connection/login fails."""
#     def _probe():
#         try:
#             if use_tls:
#                 with smtplib.SMTP(host, port, timeout=15) as s:
#                     s.starttls()
#                     if username:
#                         s.login(username, password or "")
#             else:
#                 with smtplib.SMTP(host, port, timeout=15) as s:
#                     if username:
#                         s.login(username, password or "")
#         except Exception as e:
#             raise e
#     try:
#         await run_in_threadpool(_probe)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"SMTP connection failed: {e}")

# # --- Credentials routes ------------------------------------------------------

# @router.get("/email/credentials")
# async def get_email_credentials(user: User = Depends(get_current_user)):
#     cred = await EmailCredential.filter(user=user).first()
#     if not cred:
#         # If you want to *hide* env fallback here, just return {"configured": False}
#         configured = False
#         if os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"):
#             configured = True  # environment fallback available
#         return {"configured": configured, "credential": None}
#     return {"configured": True, "credential": await _serialize_cred_masked(cred)}

# @router.post("/email/credentials")
# async def upsert_email_credentials(
#     payload: EmailCredentialUpsertRequest,
#     user: User = Depends(get_current_user)
# ):
#     # 1) quick validation
#     from_email = (payload.from_email or "").strip()
#     if not from_email or not EMAIL_RE.match(from_email):
#         raise HTTPException(status_code=400, detail="Invalid from_email")

#     # 2) probe SMTP first so we only save working creds
#     await _validate_smtp_connection(
#         host=payload.smtp_host,
#         port=payload.smtp_port,
#         username=payload.smtp_username,
#         password=payload.smtp_password,
#         use_tls=payload.smtp_use_tls,
#     )

#     # 3) upsert (1 per user is fine; extend to multiple if you want)
#     cred = await EmailCredential.filter(user=user).first()
#     if not cred:
#         cred = await EmailCredential.create(
#             user=user,
#             provider=payload.provider or "smtp",
#             from_email=from_email,
#             smtp_host=payload.smtp_host,
#             smtp_port=payload.smtp_port,
#             smtp_username=payload.smtp_username,
#             smtp_password=payload.smtp_password,
#             smtp_use_tls=payload.smtp_use_tls,
#         )
#     else:
#         cred.provider = payload.provider or "smtp"
#         cred.from_email = from_email
#         cred.smtp_host = payload.smtp_host
#         cred.smtp_port = payload.smtp_port
#         cred.smtp_username = payload.smtp_username
#         # only overwrite password if provided (allow leaving blank to keep old one)
#         if payload.smtp_password is not None:
#             cred.smtp_password = payload.smtp_password
#         cred.smtp_use_tls = payload.smtp_use_tls
#         await cred.save()

#     return {"success": True, "credential": await _serialize_cred_masked(cred)}

# @router.delete("/email/credentials")
# async def delete_email_credentials(user: User = Depends(get_current_user)):
#     cred = await EmailCredential.filter(user=user).first()
#     if not cred:
#         return {"success": True, "deleted": False}
#     await cred.delete()
#     return {"success": True, "deleted": True}

# class EmailCredentialTestRequest(BaseModel):
#     # optional: send a real test email too
#     to_email: Optional[str] = None
#     subject: Optional[str] = "SMTP test"
#     body: Optional[str] = "This is a test email."

# @router.post("/email/credentials/test")
# async def test_email_credentials(
#     payload: EmailCredentialTestRequest,
#     user: User = Depends(get_current_user)
# ):
#     cred = await EmailCredential.filter(user=user).first()
#     if not cred:
#         raise HTTPException(status_code=400, detail="No saved EmailCredential for this user")

#     # probe connection/login
#     await _validate_smtp_connection(
#         host=cred.smtp_host,
#         port=cred.smtp_port or 587,
#         username=cred.smtp_username,
#         password=cred.smtp_password,
#         use_tls=cred.smtp_use_tls,
#     )

#     # optional: send a real test email
#     if payload.to_email:
#         to_email = _sanitize_email(payload.to_email)
#         if not EMAIL_RE.match(to_email):
#             raise HTTPException(status_code=400, detail="Invalid to_email")
#         from_email = (cred.from_email or "").strip()
#         if not from_email:
#             raise HTTPException(status_code=400, detail="Missing from_email in credentials")
#         ok, mid, err = await _smtp_send(
#             cred=cred,
#             subject=(payload.subject or "SMTP test"),
#             body=(payload.body or "This is a test email."),
#             from_email=from_email,
#             to_email=to_email
#         )
#         await _store_email_outbound(
#             job=None, user=user, assistant=None, appointment=None,
#             to_email=to_email, from_email=from_email, subject=payload.subject or "SMTP test",
#             body=payload.body or "This is a test email.", provider_message_id=mid,
#             success=ok, error=err
#         )
#         if not ok:
#             raise HTTPException(status_code=400, detail=f"Test send failed: {err}")
#         return {"success": True, "sent": True, "message_id": mid}

#     return {"success": True, "connected": True, "sent": False}
