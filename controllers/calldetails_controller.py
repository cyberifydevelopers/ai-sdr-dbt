
# from __future__ import annotations

# from fastapi import APIRouter, HTTPException, Depends, Query
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel, Field
# from typing import Any, Literal, Optional
# from datetime import datetime, date, timezone
# import io
# import os
# import httpx
# import json

# from models.auth import User
# from models.assistant import Assistant
# from models.purchased_numbers import PurchasedNumber
# from models.call_log import CallLog
# from models.call_detail import CallDetail  # only used when persist=true
# from helpers.token_helper import get_current_user
# from helpers.vapi_helper import get_headers

# router = APIRouter()



# class UserRef(BaseModel):
#     id: int
#     name: Optional[str] = None
#     email: Optional[str] = None


# class LocalCallLogModel(BaseModel):
#     id: int
#     lead_id: Optional[int] = None
#     call_started_at: Optional[datetime] = None
#     customer_number: Optional[str] = None
#     customer_name: Optional[str] = None
#     call_id: Optional[str] = None
#     call_ended_at: Optional[datetime] = None
#     call_ended_reason: Optional[str] = None
#     call_duration: Optional[float] = None
#     is_transferred: Optional[bool] = None
#     status: Optional[str] = None
#     criteria_satisfied: Optional[bool] = None
#     summary: Optional[str] = None
#     transcript: Optional[Any] = None
#     analysis: Optional[Any] = None
#     recording_url: Optional[str] = Field(default=None, alias="recordingUrl")

#     class Config:
#         populate_by_name = True


# class VapiCallLogModel(BaseModel):
#     id: Optional[str] = None
#     assistant_id: Optional[str] = Field(default=None, alias="assistantId")
#     phone_number_id: Optional[str] = Field(default=None, alias="phoneNumberId")
#     status: Optional[str] = None  # unified (OpenAI/heuristics)
#     started_at: Optional[str] = Field(default=None, alias="startedAt")
#     ended_at: Optional[str] = Field(default=None, alias="endedAt")
#     duration: Optional[float] = None
#     customer_number: Optional[str] = Field(default=None, alias="customerNumber")
#     customer_name: Optional[str] = Field(default=None, alias="customerName")
#     call_id: Optional[str] = Field(default=None, alias="callId")
#     ended_reason: Optional[str] = Field(default=None, alias="endedReason")
#     is_transferred: Optional[bool] = Field(default=None, alias="isTransferred")
#     criteria_satisfied: Optional[bool] = Field(default=None, alias="criteriaSatisfied")

#     summary: Optional[str] = None
#     transcript: Optional[Any] = None
#     analysis: Optional[Any] = None
#     recording_url: Optional[str] = Field(default=None, alias="recordingUrl")

#     created_at: Optional[str] = Field(default=None, alias="createdAt")
#     updated_at: Optional[str] = Field(default=None, alias="updatedAt")

#     class Config:
#         populate_by_name = True


# class Pagination(BaseModel):
#     page: int
#     page_size: int
#     total: int


# class LocalAggregates(BaseModel):
#     page_logs: int
#     page_duration_sum: float | None = None
#     overall_duration_sum: float | None = None


# class PaginatedLocalLogs(BaseModel):
#     success: bool
#     pagination: Pagination
#     logs: list[LocalCallLogModel]
#     aggregates: LocalAggregates
#     message: str


# class PaginatedVapiLogs(BaseModel):
#     success: bool
#     total: int
#     logs: list[VapiCallLogModel]
#     message: str


# class SingleLocalLogResponse(BaseModel):
#     success: bool
#     log: LocalCallLogModel
#     message: str


# # ─────────────────────────────────────────────────────────────
# # Allowed statuses + normalization
# # ─────────────────────────────────────────────────────────────

# ALLOWED_STATUSES = {
#     "Booked",
#     "Follow-up Needed",
#     "Not Interested",
#     "No Answer",
#     "Voice Mail",
#     "Failed to Call",
#     "Transferred to Human",
# }

# def _normalize_status(value: str | None) -> Optional[str]:
#     if not value:
#         return None
#     v = value.strip().lower()
#     norm_map = {
#         "booked": "Booked",
#         "follow-up needed": "Follow-up Needed",
#         "follow up needed": "Follow-up Needed",
#         "not interested": "Not Interested",
#         "no answer": "No Answer",
#         "voice mail": "Voice Mail",
#         "voicemail": "Voice Mail",
#         "failed to call": "Failed to Call",
#         "transferred to human": "Transferred to Human",
#         "transferred": "Transferred to Human",
#     }
#     return norm_map.get(v, None)

# # ─────────────────────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────────────────────

# def _require_vapi_env():
#     api_key = os.environ.get("VAPI_API_KEY")
#     org_id = os.environ.get("VAPI_ORG_ID")
#     if not api_key or not org_id:
#         raise HTTPException(status_code=500, detail="VAPI credentials not configured")
#     return api_key, org_id


# async def _user_assistant_and_phone_sets(user: User) -> tuple[set[str], set[str]]:
#     assistants = await Assistant.filter(user=user).all()
#     a_ids = {a.vapi_assistant_id for a in assistants if getattr(a, "vapi_assistant_id", None)}

#     numbers = await PurchasedNumber.filter(user=user).all()
#     p_ids = {n.vapi_phone_uuid for n in numbers if getattr(n, "vapi_phone_uuid", None)}

#     return a_ids, p_ids


# def _matches_user_vapi_scope(v: dict, a_ids: set[str], p_ids: set[str]) -> bool:
#     a = v.get("assistantId")
#     p = v.get("phoneNumberId")
#     return (a in a_ids) or (p in p_ids)


# def _parse_date(date_str: Optional[str]) -> Optional[date]:
#     if not date_str:
#         return None
#     try:
#         return datetime.fromisoformat(date_str.strip() + "T00:00:00").date()
#     except Exception:
#         try:
#             return datetime.fromisoformat(date_str).date()
#         except Exception:
#             return None

# def _safe_iso(dt_str: Optional[str]) -> Optional[datetime]:
#     if not dt_str:
#         return None
#     try:
#         return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
#     except Exception:
#         return None


# # ─────────────────────────────────────────────────────────────
# # OpenAI classifier (heuristics + LLM fallback)
# # ─────────────────────────────────────────────────────────────

# OPENAI_URL = "https://api.openai.com/v1/chat/completions"
# OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# def _heuristic_status(vapi: dict) -> Optional[str]:
#     er = (vapi.get("endedReason") or "").lower().strip()
#     dur = vapi.get("duration")
#     transcript = vapi.get("transcript")
#     summary = vapi.get("summary")

#     if vapi.get("isTransferred") is True:
#         return "Transferred to Human"

#     if (not transcript and not summary) and (not dur or float(dur) <= 0.0):
#         return "Failed to Call"

#     if er in {"customer-did-not-answer", "no-answer", "silence-timed-out", "ring-no-answer"}:
#         return "No Answer"

#     if er in {"left-voicemail", "voice-mail", "voicemail", "customer-voicemail"}:
#         return "Voice Mail"

#     return None

# async def _classify_status_with_openai(vapi: dict) -> str:
#     if not OPENAI_API_KEY:
#         return "Failed to Call"

#     system_msg = (
#         "You are a strict classifier for call outcomes. "
#         "Return ONLY a JSON object like {\"status\":\"<one>\"}. "
#         "Valid values: Booked | Follow-up Needed | Not Interested | No Answer | Voice Mail | Failed to Call | Transferred to Human."
#     )
#     user_payload = {
#         "endedReason": vapi.get("endedReason"),
#         "status": vapi.get("status"),
#         "duration": vapi.get("duration"),
#         "isTransferred": vapi.get("isTransferred"),
#         "criteriaSatisfied": vapi.get("criteriaSatisfied"),
#         "summary": vapi.get("summary"),
#         "analysis": vapi.get("analysis"),
#         "transcript": vapi.get("transcript"),
#         "customerNumber": vapi.get("customerNumber"),
#         "customerName": vapi.get("customerName"),
#     }
#     user_msg = (
#         "Classify this call into exactly one allowed status. "
#         "If there is no content and the call didn't connect, use 'Failed to Call'.\n"
#         + json.dumps(user_payload, ensure_ascii=False)
#     )

#     body = {
#         "model": OPENAI_MODEL,
#         "response_format": {"type": "json_object"},
#         "messages": [
#             {"role": "system", "content": system_msg},
#             {"role": "user", "content": user_msg},
#         ],
#         "temperature": 0.0,
#     }
#     headers = {
#         "Authorization": f"Bearer {OPENAI_API_KEY}",
#         "Content-Type": "application/json",
#     }

#     try:
#         async with httpx.AsyncClient(timeout=30) as client:
#             resp = await client.post(OPENAI_URL, headers=headers, json=body)
#         if resp.status_code != 200:
#             return "Failed to Call"
#         data = resp.json()
#         content = (data["choices"][0]["message"]["content"] or "").strip()
#         parsed = json.loads(content)
#         raw = parsed.get("status")
#         norm = _normalize_status(raw)
#         if norm in ALLOWED_STATUSES:
#             return norm
#     except Exception:
#         pass
#     return "Failed to Call"

# async def decide_status(vapi: dict) -> str:
#     h = _heuristic_status(vapi)
#     if h:
#         return h
#     if vapi.get("summary") or vapi.get("transcript") or vapi.get("analysis"):
#         return await _classify_status_with_openai(vapi)
#     return "Failed to Call"


# # ─────────────────────────────────────────────────────────────
# # Local DB Call Logs (scoped to current user) — cost removed
# # ─────────────────────────────────────────────────────────────

# @router.get(
#     "/me/call-logs",
#     response_model=PaginatedLocalLogs,
#     summary="Get my local call logs (DB) with filters & pagination",
# )
# async def get_my_call_logs(
#     current_user: User = Depends(get_current_user),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(25, ge=1, le=200),
#     # filters
#     status: Optional[str] = Query(None, description="Filter by status (case-insensitive)"),
#     statuses: Optional[list[str]] = Query(None, description="Repeatable ?statuses=... for multiple"),
#     transferred: Optional[bool] = Query(None, description="Filter is_transferred"),
#     date_from: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
#     date_to: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
#     q: Optional[str] = Query(None, description="Search name/number/call_id"),
#     has_recording: Optional[bool] = Query(None, description="Has recording url"),
#     min_duration: Optional[float] = Query(None, description="Minimum duration (seconds)"),
#     max_duration: Optional[float] = Query(None, description="Maximum duration (seconds)"),
#     ended_reason: Optional[str] = Query(None, description="Filter by call_ended_reason"),
#     criteria_satisfied: Optional[bool] = Query(None, description="Filter by criteria_satisfied"),
#     # sorting (no 'cost' now)
#     sort: Literal["latest", "oldest"] = Query("latest"),
#     sort_by: Literal["started", "duration"] = Query("started"),
# ):
#     qset = CallLog.filter(user=current_user)

#     # status filter (single or multiple)
#     status_vals: list[str] = []
#     if statuses:
#         status_vals.extend([s.strip() for s in statuses if s and s.strip()])
#     if status:
#         status_vals.append(status.strip())
#     if status_vals:
#         ors = None
#         from tortoise.expressions import Q as TQ
#         for s in status_vals:
#             cond = TQ(status__iexact=s)
#             ors = cond if ors is None else (ors | cond)
#         qset = qset.filter(ors)

#     if transferred is not None:
#         qset = qset.filter(is_transferred=transferred)

#     if criteria_satisfied is not None:
#         qset = qset.filter(criteria_satisfied=criteria_satisfied)

#     if ended_reason:
#         qset = qset.filter(call_ended_reason__icontains=ended_reason)

#     if has_recording is not None:
#         if has_recording:
#             qset = qset.filter(recording_url__isnull=False) | qset.filter(recordingUrl__isnull=False)
#         else:
#             qset = qset.filter(recording_url__isnull=True, recordingUrl__isnull=True)

#     df = _parse_date(date_from)
#     dt = _parse_date(date_to)
#     if df:
#         qset = qset.filter(call_started_at__gte=df)
#     if dt:
#         qset = qset.filter(call_started_at__lte=datetime.combine(dt, datetime.max.time()))

#     if min_duration is not None:
#         qset = qset.filter(call_duration__gte=min_duration)
#     if max_duration is not None:
#         qset = qset.filter(call_duration__lte=max_duration)

#     if q:
#         from tortoise.expressions import Q as TQ
#         s = q.strip()
#         qset = qset.filter(
#             TQ(customer_name__icontains=s) |
#             TQ(customer_number__icontains=s) |
#             TQ(call_id__icontains=s)
#         )

#     total = await qset.count()

#     # sorting
#     if sort_by == "duration":
#         order = "-call_duration" if sort == "latest" else "call_duration"
#     else:  # started
#         order = "-call_started_at" if sort == "latest" else "call_started_at"
#     qset = qset.order_by(order, "-id" if order.startswith("-") else "id")

#     offset = (page - 1) * page_size
#     rows = await qset.offset(offset).limit(page_size)

#     def to_payload(cl: CallLog) -> LocalCallLogModel:
#         duration = getattr(cl, "call_duration", None)
#         if isinstance(duration, int):
#             duration = float(duration)
#         return LocalCallLogModel(
#             id=cl.id,
#             lead_id=getattr(cl, "lead_id", None),
#             call_started_at=getattr(cl, "call_started_at", None),
#             customer_number=getattr(cl, "customer_number", None),
#             customer_name=getattr(cl, "customer_name", None),
#             call_id=getattr(cl, "call_id", None),
#             call_ended_at=getattr(cl, "call_ended_at", None),
#             call_ended_reason=getattr(cl, "call_ended_reason", None),
#             call_duration=duration,
#             is_transferred=getattr(cl, "is_transferred", None),
#             status=getattr(cl, "status", None),
#             criteria_satisfied=getattr(cl, "criteria_satisfied", None),
#             summary=getattr(cl, "summary", None),
#             transcript=getattr(cl, "transcript", None),
#             analysis=getattr(cl, "analysis", None),
#             recordingUrl=getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
#         )

#     payload = [to_payload(x) for x in rows]

#     # aggregates (page)
#     page_duration_sum = sum([p.call_duration for p in payload if isinstance(p.call_duration, (int, float))], 0.0)

#     # aggregates (overall)
#     overall_duration_sum = None
#     try:
#         from tortoise.functions import Sum
#         agg = await qset.clone().annotate(dur_sum=Sum("call_duration")).values("dur_sum")
#         if agg and len(agg) > 0:
#             overall_duration_sum = float(agg[0].get("dur_sum")) if agg[0].get("dur_sum") is not None else None
#     except Exception:
#         pass

#     return PaginatedLocalLogs(
#         success=True,
#         pagination=Pagination(page=page, page_size=page_size, total=total),
#         logs=payload,
#         aggregates=LocalAggregates(
#             page_logs=len(payload),
#             page_duration_sum=page_duration_sum if len(payload) else None,
#             overall_duration_sum=overall_duration_sum,
#         ),
#         message=f"Fetched {len(payload)} of {total} call logs",
#     )


# @router.get(
#     "/me/call-logs/{call_log_id}",
#     response_model=SingleLocalLogResponse,
#     summary="Get a single local call log by id (scoped to me)",
# )
# async def get_my_call_log_by_id(call_log_id: int, current_user: User = Depends(get_current_user)):
#     cl = await CallLog.get_or_none(id=call_log_id, user=current_user)
#     if not cl:
#         raise HTTPException(status_code=404, detail="Call log not found")

#     duration = getattr(cl, "call_duration", None)
#     if isinstance(duration, int):
#         duration = float(duration)

#     log = LocalCallLogModel(
#         id=cl.id,
#         lead_id=getattr(cl, "lead_id", None),
#         call_started_at=getattr(cl, "call_started_at", None),
#         customer_number=getattr(cl, "customer_number", None),
#         customer_name=getattr(cl, "customer_name", None),
#         call_id=getattr(cl, "call_id", None),
#         call_ended_at=getattr(cl, "call_ended_at", None),
#         call_ended_reason=getattr(cl, "call_ended_reason", None),
#         call_duration=duration,
#         is_transferred=getattr(cl, "is_transferred", None),
#         status=getattr(cl, "status", None),
#         criteria_satisfied=getattr(cl, "criteria_satisfied", None),
#         summary=getattr(cl, "summary", None),
#         transcript=getattr(cl, "transcript", None),
#         analysis=getattr(cl, "analysis", None),
#         recordingUrl=getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
#     )

#     return SingleLocalLogResponse(success=True, log=log, message="OK")


# @router.get(
#     "/me/call-logs/export.csv",
#     summary="Export my local call logs to CSV (no cost)",
#     response_description="text/csv",
# )
# async def export_my_call_logs_csv(
#     current_user: User = Depends(get_current_user),
#     status: Optional[str] = Query(None),
#     statuses: Optional[list[str]] = Query(None),
#     transferred: Optional[bool] = Query(None),
#     date_from: Optional[str] = Query(None),
#     date_to: Optional[str] = Query(None),
#     q: Optional[str] = Query(None),
#     has_recording: Optional[bool] = Query(None),
#     min_duration: Optional[float] = Query(None),
#     max_duration: Optional[float] = Query(None),
# ):
#     qset = CallLog.filter(user=current_user)

#     status_vals: list[str] = []
#     if statuses:
#         status_vals.extend([s.strip() for s in statuses if s and s.strip()])
#     if status:
#         status_vals.append(status.strip())
#     if status_vals:
#         from tortoise.expressions import Q as TQ
#         ors = None
#         for s in status_vals:
#             cond = TQ(status__iexact=s)
#             ors = cond if ors is None else (ors | cond)
#         qset = qset.filter(ors)

#     if transferred is not None:
#         qset = qset.filter(is_transferred=transferred)

#     if has_recording is not None:
#         if has_recording:
#             qset = qset.filter(recording_url__isnull=False) | qset.filter(recordingUrl__isnull=False)
#         else:
#             qset = qset.filter(recording_url__isnull=True, recordingUrl__isnull=True)

#     df = _parse_date(date_from)
#     dt = _parse_date(date_to)
#     if df:
#         qset = qset.filter(call_started_at__gte=df)
#     if dt:
#         qset = qset.filter(call_started_at__lte=datetime.combine(dt, datetime.max.time()))

#     if min_duration is not None:
#         qset = qset.filter(call_duration__gte=min_duration)
#     if max_duration is not None:
#         qset = qset.filter(call_duration__lte=max_duration)

#     if q:
#         from tortoise.expressions import Q as TQ
#         s = q.strip()
#         qset = qset.filter(
#             TQ(customer_name__icontains=s) |
#             TQ(customer_number__icontains=s) |
#             TQ(call_id__icontains=s)
#         )

#     logs = await qset.order_by("-call_started_at", "-id")

#     import csv
#     buf = io.StringIO()
#     writer = csv.writer(buf)
#     writer.writerow([
#         "id", "lead_id", "call_started_at", "customer_number", "customer_name",
#         "call_id", "call_ended_at", "call_ended_reason", "call_duration",
#         "is_transferred", "status", "criteria_satisfied", "recording_url"
#     ])
#     for cl in logs:
#         duration = getattr(cl, "call_duration", None)
#         writer.writerow([
#             cl.id,
#             getattr(cl, "lead_id", None),
#             getattr(cl, "call_started_at", None),
#             getattr(cl, "customer_number", None),
#             getattr(cl, "customer_name", None),
#             getattr(cl, "call_id", None),
#             getattr(cl, "call_ended_at", None),
#             getattr(cl, "call_ended_reason", None),
#             duration,
#             getattr(cl, "is_transferred", None),
#             getattr(cl, "status", None),
#             getattr(cl, "criteria_satisfied", None),
#             getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
#         ])

#     buf.seek(0)
#     return StreamingResponse(
#         io.BytesIO(buf.read().encode("utf-8")),
#         media_type="text/csv",
#         headers={"Content-Disposition": 'attachment; filename=\"my_call_logs.csv\"'},
#     )


# # ─────────────────────────────────────────────────────────────
# # VAPI Call Logs (with unified status) — NO COST anywhere
# # ─────────────────────────────────────────────────────────────

# @router.get(
#     "/me/vapi-call-logs",
#     response_model=PaginatedVapiLogs,
#     summary="Get my VAPI call logs (scoped to my assistants/phone numbers) with unified status",
# )
# async def get_my_vapi_call_logs(
#     current_user: User = Depends(get_current_user),
#     status: Optional[str] = Query(None, description="Filter by unified status (after classification)"),
#     transferred: Optional[bool] = Query(None, description="Filter by isTransferred (raw)"),
#     date_from: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt >=)"),
#     date_to: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt <=)"),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(50, ge=1, le=200),
#     persist: bool = Query(True, description="If true, upsert the unified status into local DB"),
# ):
#     _require_vapi_env()
#     a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

#     url = "https://api.vapi.ai/call/"
#     headers = get_headers()

#     async with httpx.AsyncClient(timeout=60) as client:
#         resp = await client.get(url, headers=headers)
#         if resp.status_code != 200:
#             raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
#         raw = resp.json()
#         all_calls: list[dict] = raw if isinstance(raw, list) else []

#     scoped = [c for c in all_calls if _matches_user_vapi_scope(c, a_ids, p_ids)]

#     df = _parse_date(date_from)
#     dt = _parse_date(date_to)
#     if df:
#         scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] >= df.isoformat())]
#     if dt:
#         scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] <= dt.isoformat())]

#     if transferred is not None:
#         scoped = [c for c in scoped if bool(c.get("isTransferred")) is transferred]

#     def sort_key(x: dict):
#         return (x.get("startedAt") or "", x.get("id") or "")
#     scoped.sort(key=sort_key, reverse=True)

#     unified: list[dict] = []
#     for v in scoped:
#         v_for_ai = {
#             "status": v.get("status"),
#             "endedReason": v.get("endedReason"),
#             "duration": v.get("duration"),
#             "isTransferred": v.get("isTransferred"),
#             "criteriaSatisfied": v.get("criteriaSatisfied"),
#             "summary": v.get("summary"),
#             "analysis": v.get("analysis"),
#             "transcript": v.get("transcript"),
#             "customerNumber": v.get("customerNumber"),
#             "customerName": v.get("customerName"),
#         }
#         final_status = await decide_status(v_for_ai)
#         v_out = dict(v)
#         v_out["status"] = final_status
#         # strip cost if vendor sent it (we don't expose it)
#         v_out.pop("cost", None)
#         unified.append(v_out)

#         if persist:
#             cl = await CallLog.get_or_none(call_id=v.get("id"), user=current_user)
#             if not cl:
#                 cl = CallLog(user=current_user, call_id=v.get("id"))

#             started_local = _safe_iso(v.get("startedAt"))
#             ended_local = _safe_iso(v.get("endedAt"))
#             dur = v.get("duration")

#             cl.call_started_at = started_local
#             cl.call_ended_at = ended_local
#             cl.call_duration = float(dur) if dur is not None else None

#             cl.customer_number = v.get("customerNumber")
#             cl.customer_name = v.get("customerName")
#             # DO NOT read or write cost
#             cl.call_ended_reason = v.get("endedReason")
#             cl.is_transferred = v.get("isTransferred")
#             cl.criteria_satisfied = v.get("criteriaSatisfied")
#             cl.status = final_status

#             cl.summary = v.get("summary")
#             cl.transcript = v.get("transcript")
#             cl.analysis = v.get("analysis")
#             cl.recording_url = v.get("recordingUrl") or v.get("recording_url")

#             await cl.save()

#             cd = await CallDetail.get_or_none(call_id=v.get("id"), user=current_user)
#             if not cd:
#                 cd = CallDetail(user=current_user, call_id=v.get("id"), call_log=cl)

#             cd.call_log = cl
#             cd.assistant_id = v.get("assistantId")
#             cd.phone_number_id = v.get("phoneNumberId")
#             cd.customer_number = v.get("customerNumber")
#             cd.customer_name = v.get("customerName")
#             cd.status = final_status
#             cd.started_at = started_local
#             cd.ended_at = ended_local
#             cd.duration = int(float(dur)) if dur not in (None, "") else None
#             # DO NOT read or write cost
#             cd.ended_reason = v.get("endedReason")
#             cd.is_transferred = v.get("isTransferred")
#             cd.criteria_satisfied = v.get("criteriaSatisfied")
#             cd.summary = v.get("summary")
#             cd.transcript = v.get("transcript")
#             cd.analysis = v.get("analysis")
#             cd.recording_url = v.get("recordingUrl") or v.get("recording_url")
#             cd.vapi_created_at = _safe_iso(v.get("createdAt"))
#             cd.vapi_updated_at = _safe_iso(v.get("updatedAt"))
#             cd.last_synced_at = datetime.now(timezone.utc)
#             await cd.save()

#     if status:
#         want = _normalize_status(status)
#         if want:
#             unified = [c for c in unified if c.get("status") == want]
#         else:
#             unified = []

#     total = len(unified)
#     offset = (page - 1) * page_size
#     paged = unified[offset: offset + page_size]

#     models = [VapiCallLogModel(**c) for c in paged]
#     return PaginatedVapiLogs(
#         success=True,
#         total=total,
#         logs=models,
#         message=f"Fetched {len(models)} of {total} VAPI call logs (unified status applied){' and persisted' if persist else ''}",
#     )


# @router.get(
#     "/me/vapi-call-logs/{call_id}",
#     response_model=VapiCallLogModel,
#     summary="Get a single VAPI call (scoped to me) with unified status",
# )
# async def get_my_vapi_call(call_id: str, current_user: User = Depends(get_current_user)):
#     _require_vapi_env()
#     a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

#     url = f"https://api.vapi.ai/call/{call_id}"
#     headers = get_headers()

#     async with httpx.AsyncClient(timeout=60) as client:
#         resp = await client.get(url, headers=headers)
#         if resp.status_code != 200:
#             raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
#         data = resp.json()

#     if not _matches_user_vapi_scope(data, a_ids, p_ids):
#         raise HTTPException(status_code=404, detail="Call not found")

#     v_for_ai = {
#         "status": data.get("status"),
#         "endedReason": data.get("endedReason"),
#         "duration": data.get("duration"),
#         "isTransferred": data.get("isTransferred"),
#         "criteriaSatisfied": data.get("criteriaSatisfied"),
#         "summary": data.get("summary"),
#         "analysis": data.get("analysis"),
#         "transcript": data.get("transcript"),
#         "customerNumber": data.get("customerNumber"),
#         "customerName": data.get("customerName"),
#     }
#     final_status = await decide_status(v_for_ai)
#     data["status"] = final_status
#     data.pop("cost", None)

#     return VapiCallLogModel(**data)


from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from datetime import datetime, date, timezone
import io
import os
import httpx
import json

from models.auth import User
from models.assistant import Assistant
from models.purchased_numbers import PurchasedNumber
from models.call_log import CallLog
from models.call_detail import CallDetail  # always used (we persist unconditionally)
from helpers.token_helper import get_current_user
from helpers.vapi_helper import get_headers

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Schemas (NO COST anywhere)
# ─────────────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[str] = None


class LocalCallLogModel(BaseModel):
    id: int
    lead_id: Optional[int] = None
    call_started_at: Optional[datetime] = None
    customer_number: Optional[str] = None
    customer_name: Optional[str] = None
    call_id: Optional[str] = None
    call_ended_at: Optional[datetime] = None
    call_ended_reason: Optional[str] = None
    call_duration: Optional[float] = None
    is_transferred: Optional[bool] = None
    status: Optional[str] = None
    criteria_satisfied: Optional[bool] = None
    summary: Optional[str] = None
    transcript: Optional[Any] = None
    analysis: Optional[Any] = None
    recording_url: Optional[str] = Field(default=None, alias="recordingUrl")

    class Config:
        populate_by_name = True


class VapiCallLogModel(BaseModel):
    id: Optional[str] = None
    assistant_id: Optional[str] = Field(default=None, alias="assistantId")
    phone_number_id: Optional[str] = Field(default=None, alias="phoneNumberId")
    status: Optional[str] = None  # unified (OpenAI/heuristics)
    started_at: Optional[str] = Field(default=None, alias="startedAt")
    ended_at: Optional[str] = Field(default=None, alias="endedAt")
    duration: Optional[float] = None
    customer_number: Optional[str] = Field(default=None, alias="customerNumber")
    customer_name: Optional[str] = Field(default=None, alias="customerName")
    call_id: Optional[str] = Field(default=None, alias="callId")
    ended_reason: Optional[str] = Field(default=None, alias="endedReason")
    is_transferred: Optional[bool] = Field(default=None, alias="isTransferred")
    criteria_satisfied: Optional[bool] = Field(default=None, alias="criteriaSatisfied")

    summary: Optional[str] = None
    transcript: Optional[Any] = None
    analysis: Optional[Any] = None
    recording_url: Optional[str] = Field(default=None, alias="recordingUrl")

    created_at: Optional[str] = Field(default=None, alias="createdAt")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")

    class Config:
        populate_by_name = True


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class LocalAggregates(BaseModel):
    page_logs: int
    page_duration_sum: float | None = None
    overall_duration_sum: float | None = None


class PaginatedLocalLogs(BaseModel):
    success: bool
    pagination: Pagination
    logs: list[LocalCallLogModel]
    aggregates: LocalAggregates
    message: str


class PaginatedVapiLogs(BaseModel):
    success: bool
    total: int
    logs: list[VapiCallLogModel]
    message: str


class SingleLocalLogResponse(BaseModel):
    success: bool
    log: LocalCallLogModel
    message: str


# ─────────────────────────────────────────────────────────────
# Allowed statuses + normalization
# ─────────────────────────────────────────────────────────────

ALLOWED_STATUSES = {
    "Booked",
    "Follow-up Needed",
    "Not Interested",
    "No Answer",
    "Voice Mail",
    "Failed to Call",
    "Transferred to Human",
}

def _normalize_status(value: str | None) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    norm_map = {
        "booked": "Booked",
        "follow-up needed": "Follow-up Needed",
        "follow up needed": "Follow-up Needed",
        "not interested": "Not Interested",
        "no answer": "No Answer",
        "voice mail": "Voice Mail",
        "voicemail": "Voice Mail",
        "failed to call": "Failed to Call",
        "transferred to human": "Transferred to Human",
        "transferred": "Transferred to Human",
    }
    return norm_map.get(v, None)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _require_vapi_env():
    api_key = os.environ.get("VAPI_API_KEY")
    org_id = os.environ.get("VAPI_ORG_ID")
    if not api_key or not org_id:
        raise HTTPException(status_code=500, detail="VAPI credentials not configured")
    return api_key, org_id


async def _user_assistant_and_phone_sets(user: User) -> tuple[set[str], set[str]]:
    assistants = await Assistant.filter(user=user).all()
    a_ids = {a.vapi_assistant_id for a in assistants if getattr(a, "vapi_assistant_id", None)}

    numbers = await PurchasedNumber.filter(user=user).all()
    p_ids = {n.vapi_phone_uuid for n in numbers if getattr(n, "vapi_phone_uuid", None)}

    return a_ids, p_ids


def _matches_user_vapi_scope(v: dict, a_ids: set[str], p_ids: set[str]) -> bool:
    a = v.get("assistantId")
    p = v.get("phoneNumberId")
    return (a in a_ids) or (p in p_ids)


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.strip() + "T00:00:00").date()
    except Exception:
        try:
            return datetime.fromisoformat(date_str).date()
        except Exception:
            return None

def _safe_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def _to_text(val: Any) -> Optional[str]:
    """
    Coerce any summary/transcript-like value to a single text string.
    Dicts/lists -> compact JSON string; numbers/bools -> str(); None -> None.
    """
    if val is None:
        return None
    if isinstance(val, str):
        return val
    try:
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)
    except Exception:
        return None

def _to_json_or_wrap(val: Any) -> Any:
    """
    For JSONField: accept dict/list primitives; parse JSON strings; wrap plain strings.
    """
    if val is None:
        return None
    if isinstance(val, (dict, list, bool, int, float)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {"text": val}
    return None

def _compute_duration_seconds(v: dict) -> Optional[float]:
    """
    Prefer Vapi's duration (if present). Otherwise compute from endedAt-startedAt.
    Returns seconds (float).
    """
    dur = v.get("duration")
    try:
        if dur is not None and dur != "":
            return float(dur)
    except Exception:
        pass

    started = _safe_iso(v.get("startedAt"))
    ended = _safe_iso(v.get("endedAt"))
    if started and ended:
        try:
            secs = (ended - started).total_seconds()
            return float(secs) if secs >= 0 else 0.0
        except Exception:
            return None
    return None

def _extract_customer(v: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Extract customer number/name across different shapes Vapi may return.
    Priority:
      1) top-level customerNumber / customerName
      2) nested customer.number / customer.name
      3) common fallbacks (fromNumber/from/callerNumber, and customer.displayName/phone)
    """
    number = v.get("customerNumber") or None
    name = v.get("customerName") or None

    cust = v.get("customer") or {}
    if not number:
        number = cust.get("number") or cust.get("phone") or cust.get("phoneNumber")
    if not name:
        name = cust.get("name") or cust.get("displayName")

    # additional loose fallbacks seen in some transports
    if not number:
        number = v.get("fromNumber") or v.get("from") or v.get("callerNumber")

    # normalize trivial blanks
    if isinstance(number, str) and not number.strip():
        number = None
    if isinstance(name, str) and not name.strip():
        name = None

    return number, name

# ─────────────────────────────────────────────────────────────
# OpenAI classifier (heuristics + LLM fallback)
# ─────────────────────────────────────────────────────────────

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

def _heuristic_status(vapi: dict) -> Optional[str]:
    er = (vapi.get("endedReason") or "").lower().strip()
    dur = vapi.get("duration")
    transcript = vapi.get("transcript")
    summary = vapi.get("summary")

    if vapi.get("isTransferred") is True:
        return "Transferred to Human"

    if (not transcript and not summary) and (not dur or float(dur) <= 0.0):
        return "Failed to Call"

    if er in {"customer-did-not-answer", "no-answer", "silence-timed-out", "ring-no-answer"}:
        return "No Answer"

    if er in {"left-voicemail", "voice-mail", "voicemail", "customer-voicemail"}:
        return "Voice Mail"

    return None

async def _classify_status_with_openai(vapi: dict) -> str:
    if not OPENAI_API_KEY:
        return "Failed to Call"

    system_msg = (
        "You are a strict classifier for call outcomes. "
        "Return ONLY a JSON object like {\"status\":\"<one>\"}. "
        "Valid values: Booked | Follow-up Needed | Not Interested | No Answer | Voice Mail | Failed to Call | Transferred to Human."
    )
    user_payload = {
        "endedReason": vapi.get("endedReason"),
        "status": vapi.get("status"),
        "duration": vapi.get("duration"),
        "isTransferred": vapi.get("isTransferred"),
        "criteriaSatisfied": vapi.get("criteriaSatisfied"),
        "summary": vapi.get("summary"),
        "analysis": vapi.get("analysis"),
        "transcript": vapi.get("transcript"),
        "customerNumber": vapi.get("customerNumber"),
        "customerName": vapi.get("customerName"),
    }
    user_msg = (
        "Classify this call into exactly one allowed status. "
        "If there is no content and the call didn't connect, use 'Failed to Call'.\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )

    body = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENAI_URL, headers=headers, json=body)
        if resp.status_code != 200:
            return "Failed to Call"
        data = resp.json()
        content = (data["choices"][0]["message"]["content"] or "").strip()
        parsed = json.loads(content)
        raw = parsed.get("status")
        norm = _normalize_status(raw)
        if norm in ALLOWED_STATUSES:
            return norm
    except Exception:
        pass
    return "Failed to Call"

async def decide_status(vapi: dict) -> str:
    h = _heuristic_status(vapi)
    if h:
        return h
    if vapi.get("summary") or vapi.get("transcript") or vapi.get("analysis"):
        return await _classify_status_with_openai(vapi)
    return "Failed to Call"


# ─────────────────────────────────────────────────────────────
# Local DB Call Logs (scoped to current user)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/me/call-logs",
    response_model=PaginatedLocalLogs,
    summary="Get my local call logs (DB) with filters & pagination",
)
async def get_my_call_logs(
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    # filters
    status: Optional[str] = Query(None, description="Filter by status (case-insensitive)"),
    statuses: Optional[list[str]] = Query(None, description="Repeatable ?statuses=... for multiple"),
    transferred: Optional[bool] = Query(None, description="Filter is_transferred"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    q: Optional[str] = Query(None, description="Search name/number/call_id"),
    has_recording: Optional[bool] = Query(None, description="Has recording url"),
    min_duration: Optional[float] = Query(None, description="Minimum duration (seconds)"),
    max_duration: Optional[float] = Query(None, description="Maximum duration (seconds)"),
    ended_reason: Optional[str] = Query(None, description="Filter by call_ended_reason"),
    criteria_satisfied: Optional[bool] = Query(None, description="Filter by criteria_satisfied"),
    # sorting (no 'cost' now)
    sort: Literal["latest", "oldest"] = Query("latest"),
    sort_by: Literal["started", "duration"] = Query("started"),
):
    qset = CallLog.filter(user=current_user)

    # status filter (single or multiple)
    status_vals: list[str] = []
    if statuses:
        status_vals.extend([s.strip() for s in statuses if s and s.strip()])
    if status:
        status_vals.append(status.strip())
    if status_vals:
        ors = None
        from tortoise.expressions import Q as TQ
        for s in status_vals:
            cond = TQ(status__iexact=s)
            ors = cond if ors is None else (ors | cond)
        qset = qset.filter(ors)

    if transferred is not None:
        qset = qset.filter(is_transferred=transferred)

    if criteria_satisfied is not None:
        qset = qset.filter(criteria_satisfied=criteria_satisfied)

    if ended_reason:
        qset = qset.filter(call_ended_reason__icontains=ended_reason)

    if has_recording is not None:
        if has_recording:
            qset = qset.filter(recording_url__isnull=False) | qset.filter(recordingUrl__isnull=False)
        else:
            qset = qset.filter(recording_url__isnull=True, recordingUrl__isnull=True)

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        qset = qset.filter(call_started_at__gte=df)
    if dt:
        qset = qset.filter(call_started_at__lte=datetime.combine(dt, datetime.max.time()))

    if min_duration is not None:
        qset = qset.filter(call_duration__gte=min_duration)
    if max_duration is not None:
        qset = qset.filter(call_duration__lte=max_duration)

    if q:
        from tortoise.expressions import Q as TQ
        s = q.strip()
        qset = qset.filter(
            TQ(customer_name__icontains=s) |
            TQ(customer_number__icontains=s) |
            TQ(call_id__icontains=s)
        )

    total = await qset.count()

    # sorting
    if sort_by == "duration":
        order = "-call_duration" if sort == "latest" else "call_duration"
    else:  # started
        order = "-call_started_at" if sort == "latest" else "call_started_at"
    qset = qset.order_by(order, "-id" if order.startswith("-") else "id")

    offset = (page - 1) * page_size
    rows = await qset.offset(offset).limit(page_size)

    def to_payload(cl: CallLog) -> LocalCallLogModel:
        duration = getattr(cl, "call_duration", None)
        if isinstance(duration, int):
            duration = float(duration)
        return LocalCallLogModel(
            id=cl.id,
            lead_id=getattr(cl, "lead_id", None),
            call_started_at=getattr(cl, "call_started_at", None),
            customer_number=getattr(cl, "customer_number", None),
            customer_name=getattr(cl, "customer_name", None),
            call_id=getattr(cl, "call_id", None),
            call_ended_at=getattr(cl, "call_ended_at", None),
            call_ended_reason=getattr(cl, "call_ended_reason", None),
            call_duration=duration,
            is_transferred=getattr(cl, "is_transferred", None),
            status=getattr(cl, "status", None),
            criteria_satisfied=getattr(cl, "criteria_satisfied", None),
            summary=getattr(cl, "summary", None),
            transcript=getattr(cl, "transcript", None),
            analysis=getattr(cl, "analysis", None),
            recordingUrl=getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
        )

    payload = [to_payload(x) for x in rows]

    # aggregates (page)
    page_duration_sum = sum([p.call_duration for p in payload if isinstance(p.call_duration, (int, float))], 0.0)

    # aggregates (overall)
    overall_duration_sum = None
    try:
        from tortoise.functions import Sum
        agg = await qset.clone().annotate(dur_sum=Sum("call_duration")).values("dur_sum")
        if agg and len(agg) > 0:
            overall_duration_sum = float(agg[0].get("dur_sum")) if agg[0].get("dur_sum") is not None else None
    except Exception:
        pass

    return PaginatedLocalLogs(
        success=True,
        pagination=Pagination(page=page, page_size=page_size, total=total),
        logs=payload,
        aggregates=LocalAggregates(
            page_logs=len(payload),
            page_duration_sum=page_duration_sum if len(payload) else None,
            overall_duration_sum=overall_duration_sum,
        ),
        message=f"Fetched {len(payload)} of {total} call logs",
    )


@router.get(
    "/me/call-logs/{call_log_id}",
    response_model=SingleLocalLogResponse,
    summary="Get a single local call log by id (scoped to me)",
)
async def get_my_call_log_by_id(call_log_id: int, current_user: User = Depends(get_current_user)):
    cl = await CallLog.get_or_none(id=call_log_id, user=current_user)
    if not cl:
        raise HTTPException(status_code=404, detail="Call log not found")

    duration = getattr(cl, "call_duration", None)
    if isinstance(duration, int):
        duration = float(duration)

    log = LocalCallLogModel(
        id=cl.id,
        lead_id=getattr(cl, "lead_id", None),
        call_started_at=getattr(cl, "call_started_at", None),
        customer_number=getattr(cl, "customer_number", None),
        customer_name=getattr(cl, "customer_name", None),
        call_id=getattr(cl, "call_id", None),
        call_ended_at=getattr(cl, "call_ended_at", None),
        call_ended_reason=getattr(cl, "call_ended_reason", None),
        call_duration=duration,
        is_transferred=getattr(cl, "is_transferred", None),
        status=getattr(cl, "status", None),
        criteria_satisfied=getattr(cl, "criteria_satisfied", None),
        summary=getattr(cl, "summary", None),
        transcript=getattr(cl, "transcript", None),
        analysis=getattr(cl, "analysis", None),
        recordingUrl=getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
    )

    return SingleLocalLogResponse(success=True, log=log, message="OK")


@router.get(
    "/me/call-logs/export.csv",
    summary="Export my local call logs to CSV (no cost)",
    response_description="text/csv",
)
async def export_my_call_logs_csv(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    statuses: Optional[list[str]] = Query(None),
    transferred: Optional[bool] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    has_recording: Optional[bool] = Query(None),
    min_duration: Optional[float] = Query(None),
    max_duration: Optional[float] = Query(None),
):
    qset = CallLog.filter(user=current_user)

    status_vals: list[str] = []
    if statuses:
        status_vals.extend([s.strip() for s in statuses if s and s.strip()])
    if status:
        status_vals.append(status.strip())
    if status_vals:
        from tortoise.expressions import Q as TQ
        ors = None
        for s in status_vals:
            cond = TQ(status__iexact=s)
            ors = cond if ors is None else (ors | cond)
        qset = qset.filter(ors)

    if transferred is not None:
        qset = qset.filter(is_transferred=transferred)

    if has_recording is not None:
        if has_recording:
            qset = qset.filter(recording_url__isnull=False) | qset.filter(recordingUrl__isnull=False)
        else:
            qset = qset.filter(recording_url__isnull=True, recordingUrl__isnull=True)

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        qset = qset.filter(call_started_at__gte=df)
    if dt:
        qset = qset.filter(call_started_at__lte=datetime.combine(dt, datetime.max.time()))

    if min_duration is not None:
        qset = qset.filter(call_duration__gte=min_duration)
    if max_duration is not None:
        qset = qset.filter(call_duration__lte=max_duration)

    if q:
        from tortoise.expressions import Q as TQ
        s = q.strip()
        qset = qset.filter(
            TQ(customer_name__icontains=s) |
            TQ(customer_number__icontains=s) |
            TQ(call_id__icontains=s)
        )

    logs = await qset.order_by("-call_started_at", "-id")

    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "lead_id", "call_started_at", "customer_number", "customer_name",
        "call_id", "call_ended_at", "call_ended_reason", "call_duration",
        "is_transferred", "status", "criteria_satisfied", "recording_url"
    ])
    for cl in logs:
        duration = getattr(cl, "call_duration", None)
        writer.writerow([
            cl.id,
            getattr(cl, "lead_id", None),
            getattr(cl, "call_started_at", None),
            getattr(cl, "customer_number", None),
            getattr(cl, "customer_name", None),
            getattr(cl, "call_id", None),
            getattr(cl, "call_ended_at", None),
            getattr(cl, "call_ended_reason", None),
            duration,
            getattr(cl, "is_transferred", None),
            getattr(cl, "status", None),
            getattr(cl, "criteria_satisfied", None),
            getattr(cl, "recording_url", None) or getattr(cl, "recordingUrl", None),
        ])

    buf.seek(0)
    return StreamingResponse(
        io.BytesIO(buf.read().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename=\"my_call_logs.csv\"'},
    )


# ─────────────────────────────────────────────────────────────
# VAPI Call Logs (with unified status) — ALWAYS PERSIST
# ─────────────────────────────────────────────────────────────

@router.get(
    "/me/vapi-call-logs",
    response_model=PaginatedVapiLogs,
    summary="Get my VAPI call logs (scoped to my assistants/phone numbers) with unified status",
)
async def get_my_vapi_call_logs(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Filter by unified status (after classification)"),
    transferred: Optional[bool] = Query(None, description="Filter by isTransferred (raw)"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt >=)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt <=)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_vapi_env()
    a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

    url = "https://api.vapi.ai/call/"
    headers = get_headers()

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
        raw = resp.json()
        all_calls: list[dict] = raw if isinstance(raw, list) else []

    scoped = [c for c in all_calls if _matches_user_vapi_scope(c, a_ids, p_ids)]

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] >= df.isoformat())]
    if dt:
        scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] <= dt.isoformat())]

    if transferred is not None:
        scoped = [c for c in scoped if bool(c.get("isTransferred")) is transferred]

    def sort_key(x: dict):
        return (x.get("startedAt") or "", x.get("id") or "")
    scoped.sort(key=sort_key, reverse=True)

    unified: list[dict] = []
    for v in scoped:
        dur = _compute_duration_seconds(v)
        cust_num, cust_name = _extract_customer(v)

        v_for_ai = {
            "status": v.get("status"),
            "endedReason": v.get("endedReason"),
            "duration": dur,
            "isTransferred": v.get("isTransferred"),
            "criteriaSatisfied": v.get("criteriaSatisfied"),
            "summary": v.get("summary"),
            "analysis": v.get("analysis"),
            "transcript": v.get("transcript"),
            "customerNumber": cust_num,
            "customerName": cust_name,
        }
        final_status = await decide_status(v_for_ai)

        v_out = dict(v)
        v_out["status"] = final_status
        v_out["duration"] = dur
        v_out["customerNumber"] = cust_num
        v_out["customerName"] = cust_name
        v_out.pop("cost", None)  # never expose cost
        unified.append(v_out)

        # ── ALWAYS PERSIST ─────────────────────────────────────
        cl = await CallLog.get_or_none(call_id=v.get("id"), user=current_user)
        if not cl:
            cl = CallLog(user=current_user, call_id=v.get("id"))

        started_local = _safe_iso(v.get("startedAt"))
        ended_local = _safe_iso(v.get("endedAt"))

        cl.call_started_at = started_local
        cl.call_ended_at = ended_local
        cl.call_duration = float(dur) if dur is not None else None

        cl.customer_number = cust_num
        cl.customer_name = cust_name
        cl.call_ended_reason = v.get("endedReason")
        cl.is_transferred = v.get("isTransferred")
        cl.criteria_satisfied = v.get("criteriaSatisfied")
        cl.status = final_status

        # text/json safety
        cl.summary = _to_text(v.get("summary"))
        cl.transcript = _to_text(v.get("transcript"))
        cl.analysis = _to_json_or_wrap(v.get("analysis"))
        cl.recording_url = v.get("recordingUrl") or v.get("recording_url")

        await cl.save()

        cd = await CallDetail.get_or_none(call_id=v.get("id"), user=current_user)
        if not cd:
            cd = CallDetail(user=current_user, call_id=v.get("id"), call_log=cl)

        cd.call_log = cl
        cd.assistant_id = v.get("assistantId")
        cd.phone_number_id = v.get("phoneNumberId")
        cd.customer_number = cust_num
        cd.customer_name = cust_name
        cd.status = final_status
        cd.started_at = started_local
        cd.ended_at = ended_local
        cd.duration = int(float(dur)) if isinstance(dur, (int, float)) else None
        cd.ended_reason = v.get("endedReason")
        cd.is_transferred = v.get("isTransferred")
        cd.criteria_satisfied = v.get("criteriaSatisfied")

        # text/json safety
        cd.summary = _to_text(v.get("summary"))          # TextField
        cd.transcript = _to_text(v.get("transcript"))    # TextField
        cd.analysis = _to_json_or_wrap(v.get("analysis"))# JSONField
        cd.recording_url = v.get("recordingUrl") or v.get("recording_url")

        cd.vapi_created_at = _safe_iso(v.get("createdAt"))
        cd.vapi_updated_at = _safe_iso(v.get("updatedAt"))
        cd.last_synced_at = datetime.now(timezone.utc)
        await cd.save()
        # ──────────────────────────────────────────────────────

    if status:
        want = _normalize_status(status)
        if want:
            unified = [c for c in unified if c.get("status") == want]
        else:
            unified = []

    total = len(unified)
    offset = (page - 1) * page_size
    paged = unified[offset: offset + page_size]

    models = [VapiCallLogModel(**c) for c in paged]
    return PaginatedVapiLogs(
        success=True,
        total=total,
        logs=models,
        message=f"Fetched {len(models)} of {total} VAPI call logs (unified status applied and persisted)",
    )


@router.get(
    "/me/vapi-call-logs/{call_id}",
    response_model=VapiCallLogModel,
    summary="Get a single VAPI call (scoped to me) with unified status",
)
async def get_my_vapi_call(call_id: str, current_user: User = Depends(get_current_user)):
    _require_vapi_env()
    a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

    url = f"https://api.vapi.ai/call/{call_id}"
    headers = get_headers()

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
        data = resp.json()

    if not _matches_user_vapi_scope(data, a_ids, p_ids):
        raise HTTPException(status_code=404, detail="Call not found")

    dur = _compute_duration_seconds(data)
    cust_num, cust_name = _extract_customer(data)

    v_for_ai = {
        "status": data.get("status"),
        "endedReason": data.get("endedReason"),
        "duration": dur,
        "isTransferred": data.get("isTransferred"),
        "criteriaSatisfied": data.get("criteriaSatisfied"),
        "summary": data.get("summary"),
        "analysis": data.get("analysis"),
        "transcript": data.get("transcript"),
        "customerNumber": cust_num,
        "customerName": cust_name,
    }
    final_status = await decide_status(v_for_ai)

    data["status"] = final_status
    data["duration"] = dur
    data["customerNumber"] = cust_num
    data["customerName"] = cust_name
    data.pop("cost", None)

    return VapiCallLogModel(**data)
