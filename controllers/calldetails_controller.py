
# from __future__ import annotations

# import os
# import math
# from decimal import Decimal
# from datetime import datetime, date, timezone
# from typing import Optional, Any, Dict, List

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query
# from pydantic import BaseModel
# from dateutil import parser as dtparser  # pip install python-dateutil

# from models.auth import User
# from models.call_log import CallLog
# from models.call_detail import CallDetail
# from helpers.token_helper import get_current_user


# # ───────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ───────────────────────────────────────────────────────────────────────────────

# class UserRef(BaseModel):
#     id: int
#     name: Optional[str]
#     email: Optional[str]


# class CallLogOut(BaseModel):
#     # Local CallLog (DB)
#     id: int
#     lead_id: Optional[int]
#     call_started_at: Optional[str]
#     customer_number: Optional[str]
#     customer_name: Optional[str]
#     call_id: Optional[str]
#     cost: Optional[float]
#     call_ended_at: Optional[str]
#     call_ended_reason: Optional[str]
#     call_duration: Optional[int]
#     is_transferred: Optional[bool]
#     status: Optional[str]
#     criteria_satisfied: Optional[bool]
#     user: Optional[UserRef]

#     # VAPI (rich)
#     assistant_id: Optional[str] = None
#     phone_number_id: Optional[str] = None
#     started_at: Optional[str] = None
#     ended_at: Optional[str] = None
#     duration: Optional[int] = None
#     ended_reason: Optional[str] = None
#     success_evaluation_status: Optional[str] = None
#     summary: Any | None = None
#     transcript: Any | None = None
#     analysis: Any | None = None
#     recording_url: Optional[str] = None

#     vapi_created_at: Optional[str] = None
#     vapi_updated_at: Optional[str] = None


# class CallDetailOut(BaseModel):
#     id: int
#     user: UserRef | None
#     call_log_id: Optional[int]

#     # IDs
#     call_id: Optional[str]
#     assistant_id: Optional[str]
#     phone_number_id: Optional[str]

#     # Parties
#     customer_number: Optional[str]
#     customer_name: Optional[str]

#     # Status/Timing/Cost
#     status: Optional[str]
#     started_at: Optional[str]
#     ended_at: Optional[str]
#     duration: Optional[int]
#     cost: Optional[float]
#     ended_reason: Optional[str]
#     is_transferred: Optional[bool]
#     criteria_satisfied: Optional[bool]

#     # **Extra** success evaluation
#     success_evaluation_status: Optional[str]

#     # Rich data
#     summary: Any | None
#     transcript: Any | None
#     analysis: Any | None
#     recording_url: Optional[str]

#     vapi_created_at: Optional[str]
#     vapi_updated_at: Optional[str]
#     last_synced_at: Optional[str]


# router = APIRouter()


# # ───────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ───────────────────────────────────────────────────────────────────────────────

# def _require_vapi_creds() -> tuple[str, str | None]:
#     vapi_api_key = os.environ.get("VAPI_API_KEY")
#     vapi_org_id = os.environ.get("VAPI_ORG_ID")  # optional in some setups, but send if present
#     if not vapi_api_key:
#         raise HTTPException(status_code=500, detail="VAPI credentials not configured")
#     return vapi_api_key, vapi_org_id


# def _vapi_headers() -> dict:
#     api_key, org = _require_vapi_creds()
#     h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
#     # Some orgs require this header to return recording/transcript fields reliably:
#     if org:
#         h["x-vapi-organization"] = org
#     return h


# def _iso(v):
#     if isinstance(v, (datetime, date)):
#         return v.isoformat()
#     return v


# def _to_float(v):
#     if v is None:
#         return None
#     if isinstance(v, (float, int)):
#         return float(v)
#     if isinstance(v, Decimal):
#         return float(v)
#     try:
#         return float(v)
#     except Exception:
#         return None


# def _to_int_seconds(v, *, rounding: str = "round"):
#     if v is None:
#         return None
#     if isinstance(v, bool):
#         return int(v)
#     if isinstance(v, int):
#         return v
#     if isinstance(v, (float, Decimal)):
#         f = float(v)
#         if rounding == "round":
#             return int(round(f))
#         elif rounding == "floor":
#             return math.floor(f)
#         else:
#             return math.ceil(f)
#     try:
#         return int(v)
#     except Exception:
#         return None


# def _extract_success_eval(analysis: Any) -> Optional[str]:
#     try:
#         if not isinstance(analysis, dict):
#             return None
#         se = analysis.get("successEvaluation")
#         if isinstance(se, dict):
#             status = se.get("status")
#             if isinstance(status, str):
#                 return status
#         call_score = analysis.get("callScore")
#         if isinstance(call_score, dict):
#             status = call_score.get("overallStatus")
#             if isinstance(status, str):
#                 return status
#     except Exception:
#         pass
#     return None


# def _map_user_ref(u: Optional[User]) -> Optional[UserRef]:
#     if not u:
#         return None
#     return UserRef(id=u.id, name=getattr(u, "name", None), email=getattr(u, "email", None))


# def _dt(v) -> Optional[datetime]:
#     if v is None:
#         return None
#     if isinstance(v, datetime):
#         return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
#     if isinstance(v, str):
#         try:
#             d = dtparser.isoparse(v)
#             if d.tzinfo is None:
#                 d = d.replace(tzinfo=timezone.utc)
#             return d.astimezone(timezone.utc)
#         except Exception:
#             return None
#     return None


# async def _my_call_ids_for_user(uid: int) -> Dict[str, int]:
#     """Map {callId: local CallLog.id} for this user."""
#     logs = await CallLog.filter(user_id=uid).all()
#     out: Dict[str, int] = {}
#     for cl in logs:
#         cid = getattr(cl, "call_id", None)
#         if cid:
#             out[cid] = cl.id
#     return out


# async def _fetch_vapi_calls() -> List[dict]:
#     # Pull full call objects; VAPI returns an array
#     url = "https://api.vapi.ai/call/"
#     headers = _vapi_headers()
#     async with httpx.AsyncClient(timeout=30) as client:
#         resp = await client.get(url, headers=headers)
#         if resp.status_code != 200:
#             raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
#         data = resp.json()
#         return data if isinstance(data, list) else []


# # ───────────────────────────────────────────────────────────────────────────────
# # Endpoints
# # ───────────────────────────────────────────────────────────────────────────────

# # ONE endpoint that merges local CallLogs with rich VAPI data (like admin)
# @router.get("/call-logs", response_model=dict)
# async def list_user_call_logs_full(current_user: User = Depends(get_current_user)):
#     """
#     Returns the user's call logs from the local DB,
#     merged with the corresponding VAPI rich fields (summary, transcript, analysis, recording_url, etc.)
#     so it matches admin's view but scoped to the user.
#     """
#     try:
#         # 1) Local logs
#         logs = await CallLog.filter(user_id=current_user.id).prefetch_related("user").all()
#         # Build a map callId->local
#         local_by_call_id: Dict[str, CallLog] = {}
#         for cl in logs:
#             cid = getattr(cl, "call_id", None)
#             if cid:
#                 local_by_call_id[cid] = cl

#         # 2) VAPI calls (live)
#         vapi_list = await _fetch_vapi_calls()
#         # filter to this user's callIds only
#         vapi_by_call_id: Dict[str, dict] = {c.get("callId"): c for c in vapi_list if c.get("callId") in local_by_call_id}

#         # 3) Merge row-by-row so frontend always gets one source of truth
#         out: List[dict] = []
#         for cl in logs:
#             v: dict = vapi_by_call_id.get(getattr(cl, "call_id", None), {}) or {}
#             analysis = v.get("analysis")

#             merged = CallLogOut(
#                 # Local
#                 id=cl.id,
#                 lead_id=getattr(cl, "lead_id", None),
#                 call_started_at=_iso(getattr(cl, "call_started_at", None)),
#                 customer_number=getattr(cl, "customer_number", None),
#                 customer_name=getattr(cl, "customer_name", None),
#                 call_id=getattr(cl, "call_id", None),
#                 cost=_to_float(getattr(cl, "cost", None)),
#                 call_ended_at=_iso(getattr(cl, "call_ended_at", None)),
#                 call_ended_reason=getattr(cl, "call_ended_reason", None),
#                 call_duration=_to_int_seconds(getattr(cl, "call_duration", None), rounding="round"),
#                 is_transferred=getattr(cl, "is_transferred", None),
#                 status=getattr(cl, "status", None),
#                 criteria_satisfied=getattr(cl, "criteria_satisfied", None),
#                 user=_map_user_ref(getattr(cl, "user", None)),

#                 # VAPI (rich) – matches admin
#                 assistant_id=v.get("assistantId"),
#                 phone_number_id=v.get("phoneNumberId"),
#                 started_at=v.get("startedAt"),
#                 ended_at=v.get("endedAt"),
#                 duration=_to_int_seconds(v.get("duration")),
#                 ended_reason=v.get("endedReason"),
#                 success_evaluation_status=_extract_success_eval(analysis),
#                 summary=v.get("summary"),
#                 transcript=v.get("transcript"),
#                 analysis=analysis,
#                 recording_url=v.get("recordingUrl"),
#                 vapi_created_at=v.get("createdAt"),
#                 vapi_updated_at=v.get("UpdatedAt") or v.get("updatedAt"),
#             ).dict()

#             out.append(merged)

#         return {
#             "success": True,
#             "total_call_logs": len(out),
#             "call_logs": out,
#             "message": f"Fetched {len(out)} merged call logs (local + VAPI) for current user",
#         }
#     except HTTPException:
#         raise
#     except httpx.RequestError as e:
#         raise HTTPException(status_code=500, detail=f"Network error while contacting VAPI: {str(e)}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching merged call logs: {str(e)}")


# # ───────────────────────────────────────────────────────────────────────────────
# # (Optional) keep detail/sync endpoints if you use them elsewhere
# # ───────────────────────────────────────────────────────────────────────────────

# @router.post("/call-details/sync", response_model=dict)
# async def sync_vapi_into_call_details(current_user: User = Depends(get_current_user)):
#     try:
#         by_call_id = await _my_call_ids_for_user(current_user.id)  # {callId: call_log_id}
#         if not by_call_id:
#             return {"success": True, "synced": 0, "message": "No user callIds to sync from VAPI."}

#         vapi_calls = await _fetch_vapi_calls()
#         now = datetime.now(timezone.utc)
#         upserts = 0

#         existing = await CallDetail.filter(user_id=current_user.id).all()
#         existing_by_call_id = {cd.call_id: cd for cd in existing if cd.call_id}

#         for c in vapi_calls:
#             call_id = c.get("callId")
#             if not call_id or call_id not in by_call_id:
#                 continue

#             analysis = c.get("analysis")
#             payload = dict(
#                 user_id=current_user.id,
#                 call_log_id=by_call_id[call_id],
#                 call_id=call_id,
#                 assistant_id=c.get("assistantId"),
#                 phone_number_id=c.get("phoneNumberId"),
#                 customer_number=c.get("customerNumber"),
#                 customer_name=c.get("customerName"),
#                 status=c.get("status"),
#                 started_at=_dt(c.get("startedAt")),
#                 ended_at=_dt(c.get("endedAt")),
#                 duration=_to_int_seconds(c.get("duration"), rounding="round"),
#                 cost=_to_float(c.get("cost")),
#                 ended_reason=c.get("endedReason"),
#                 is_transferred=bool(c.get("isTransferred")) if c.get("isTransferred") is not None else None,
#                 criteria_satisfied=bool(c.get("criteriaSatisfied")) if c.get("criteriaSatisfied") is not None else None,
#                 success_evaluation_status=_extract_success_eval(analysis),
#                 summary=c.get("summary"),
#                 transcript=c.get("transcript"),
#                 analysis=analysis,
#                 recording_url=c.get("recordingUrl"),
#                 vapi_created_at=_dt(c.get("createdAt")),
#                 vapi_updated_at=_dt(c.get("UpdatedAt") or c.get("updatedAt")),
#                 last_synced_at=now,
#             )

#             if call_id in existing_by_call_id:
#                 cd = existing_by_call_id[call_id]
#                 for k, v in payload.items():
#                     setattr(cd, k, v)
#                 await cd.save()
#             else:
#                 await CallDetail.create(**payload)

#             upserts += 1

#         return {"success": True, "synced": upserts, "message": f"Synced {upserts} calls into CallDetail"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error syncing call details: {str(e)}")


# @router.get("/call-details", response_model=dict)
# async def list_call_details(
#     status: Optional[str] = Query(None, description="Filter by status"),
#     success_eval: Optional[str] = Query(None, description="Filter by success_evaluation_status"),
#     current_user: User = Depends(get_current_user),
# ):
#     try:
#         qs = CallDetail.filter(user_id=current_user.id).prefetch_related("user", "call_log")
#         if status:
#             qs = qs.filter(status=status)
#         if success_eval:
#             qs = qs.filter(success_evaluation_status=success_eval)

#         rows = await qs.all()
#         out: List[CallDetailOut] = []
#         for cd in rows:
#             out.append(
#                 CallDetailOut(
#                     id=cd.id,
#                     user=_map_user_ref(getattr(cd, "user", None)),
#                     call_log_id=getattr(cd, "call_log_id", None),
#                     call_id=cd.call_id,
#                     assistant_id=cd.assistant_id,
#                     phone_number_id=cd.phone_number_id,
#                     customer_number=cd.customer_number,
#                     customer_name=cd.customer_name,
#                     status=cd.status,
#                     started_at=(cd.started_at.isoformat() if cd.started_at else None),
#                     ended_at=(cd.ended_at.isoformat() if cd.ended_at else None),
#                     duration=cd.duration,
#                     cost=cd.cost,
#                     ended_reason=cd.ended_reason,
#                     is_transferred=cd.is_transferred,
#                     criteria_satisfied=cd.criteria_satisfied,
#                     success_evaluation_status=cd.success_evaluation_status,
#                     summary=cd.summary,
#                     transcript=cd.transcript,
#                     analysis=cd.analysis,
#                     recording_url=cd.recording_url,
#                     vapi_created_at=(cd.vapi_created_at.isoformat() if cd.vapi_created_at else None),
#                     vapi_updated_at=(cd.vapi_updated_at.isoformat() if cd.vapi_updated_at else None),
#                     last_synced_at=(cd.last_synced_at.isoformat() if cd.last_synced_at else None),
#                 ).dict()
#             )

#         return {
#             "success": True,
#             "total": len(out),
#             "call_details": out,
#             "message": f"Fetched {len(out)} call details for current user",
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching call details: {str(e)}")


# @router.get("/call-details/{detail_id}", response_model=dict)
# async def get_call_detail(detail_id: int, current_user: User = Depends(get_current_user)):
#     try:
#         cd = await CallDetail.get_or_none(id=detail_id, user_id=current_user.id)
#         if not cd:
#             raise HTTPException(status_code=404, detail="Call detail not found")

#         try:
#             await cd.fetch_related("user", "call_log")
#         except Exception:
#             pass

#         payload = CallDetailOut(
#             id=cd.id,
#             user=_map_user_ref(getattr(cd, "user", None)),
#             call_log_id=getattr(cd, "call_log_id", None),
#             call_id=cd.call_id,
#             assistant_id=cd.assistant_id,
#             phone_number_id=cd.phone_number_id,
#             customer_number=cd.customer_number,
#             customer_name=cd.customer_name,
#             status=cd.status,
#             started_at=(cd.started_at.isoformat() if cd.started_at else None),
#             ended_at=(cd.ended_at.isoformat() if cd.ended_at else None),
#             duration=cd.duration,
#             cost=cd.cost,
#             ended_reason=cd.ended_reason,
#             is_transferred=cd.is_transferred,
#             criteria_satisfied=cd.criteria_satisfied,
#             success_evaluation_status=cd.success_evaluation_status,
#             summary=cd.summary,
#             transcript=cd.transcript,
#             analysis=cd.analysis,
#             recording_url=cd.recording_url,
#             vapi_created_at=(cd.vapi_created_at.isoformat() if cd.vapi_created_at else None),
#             vapi_updated_at=(cd.vapi_updated_at.isoformat() if cd.vapi_updated_at else None),
#             last_synced_at=(cd.last_synced_at.isoformat() if cd.last_synced_at else None),
#         ).dict()

#         return {"success": True, "call_detail": payload}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error reading call detail: {str(e)}")


# @router.get("/call-details/by-call-log/{call_log_id}", response_model=dict)
# async def get_call_detail_by_call_log(call_log_id: int, current_user: User = Depends(get_current_user)):
#     try:
#         cd = await CallDetail.get_or_none(call_log_id=call_log_id, user_id=current_user.id)
#         if not cd:
#             return {"success": True, "call_detail": None}

#         try:
#             await cd.fetch_related("user", "call_log")
#         except Exception:
#             pass

#         payload = CallDetailOut(
#             id=cd.id,
#             user=_map_user_ref(getattr(cd, "user", None)),
#             call_log_id=getattr(cd, "call_log_id", None),
#             call_id=cd.call_id,
#             assistant_id=cd.assistant_id,
#             phone_number_id=cd.phone_number_id,
#             customer_number=cd.customer_number,
#             customer_name=cd.customer_name,
#             status=cd.status,
#             started_at=(cd.started_at.isoformat() if cd.started_at else None),
#             ended_at=(cd.ended_at.isoformat() if cd.ended_at else None),
#             duration=cd.duration,
#             cost=cd.cost,
#             ended_reason=cd.ended_reason,
#             is_transferred=cd.is_transferred,
#             criteria_satisfied=cd.criteria_satisfied,
#             success_evaluation_status=cd.success_evaluation_status,
#             summary=cd.summary,
#             transcript=cd.transcript,
#             analysis=cd.analysis,
#             recording_url=cd.recording_url,
#             vapi_created_at=(cd.vapi_created_at.isoformat() if cd.vapi_created_at else None),
#             vapi_updated_at=(cd.vapi_updated_at.isoformat() if cd.vapi_updated_at else None),
#             last_synced_at=(cd.last_synced_at.isoformat() if cd.last_synced_at else None),
#         ).dict()

#         return {"success": True, "call_detail": payload}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching detail by call_log_id: {str(e)}")

# app/api/user_calllogs_controller.py
# controllers/calldetails_controller.py (user-facing routes)

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from datetime import datetime, date
import io
import os
import httpx

from models.auth import User
from models.assistant import Assistant
from models.purchased_numbers import PurchasedNumber
from models.call_log import CallLog
from helpers.token_helper import get_current_user
from helpers.vapi_helper import get_headers

router = APIRouter()

# ───────────────────────────────────────────────────────────────────────────────
# Pydantic Models (Response Schemas)
# ───────────────────────────────────────────────────────────────────────────────

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
    cost: Optional[float] = None
    call_ended_at: Optional[datetime] = None
    call_ended_reason: Optional[str] = None
    # accept float to avoid ValidationError when DB stores fractional seconds
    call_duration: Optional[float] = None
    is_transferred: Optional[bool] = None
    status: Optional[str] = None
    criteria_satisfied: Optional[bool] = None

    # Optional extended fields if present in your CallLog table
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
    status: Optional[str] = None
    started_at: Optional[str] = Field(default=None, alias="startedAt")
    ended_at: Optional[str] = Field(default=None, alias="endedAt")
    # accept float for consistency
    duration: Optional[float] = None
    cost: Optional[float] = None
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
    page_cost_sum: float | None = None
    overall_duration_sum: float | None = None
    overall_cost_sum: float | None = None


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


# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────

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


# ───────────────────────────────────────────────────────────────────────────────
# Local DB Call Logs (scoped to current user)
# ───────────────────────────────────────────────────────────────────────────────

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
    # sorting
    sort: Literal["latest", "oldest"] = Query("latest"),
    sort_by: Literal["started", "duration", "cost"] = Query("started"),
):
    qset = CallLog.filter(user=current_user)

    # status filter (single or multiple)
    status_vals: list[str] = []
    if statuses:
        status_vals.extend([s.strip() for s in statuses if s and s.strip()])
    if status:
        status_vals.append(status.strip())
    if status_vals:
        # case-insensitive OR across provided statuses
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
    elif sort_by == "cost":
        order = "-cost" if sort == "latest" else "cost"
    else:  # started
        order = "-call_started_at" if sort == "latest" else "call_started_at"
    # tie-breaker by id for determinism
    if order.startswith("-"):
        qset = qset.order_by(order, "-id")
    else:
        qset = qset.order_by(order, "id")

    offset = (page - 1) * page_size
    rows = await qset.offset(offset).limit(page_size)

    def to_payload(cl: CallLog) -> LocalCallLogModel:
        # keep fractional seconds; do not coerce to int
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
            cost=float(getattr(cl, "cost", 0)) if getattr(cl, "cost", None) is not None else None,
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
    page_cost_sum = sum([p.cost for p in payload if isinstance(p.cost, (int, float))], 0.0)

    # aggregates (overall) — try DB aggregation, fall back to None if unsupported
    overall_duration_sum = None
    overall_cost_sum = None
    try:
        from tortoise.functions import Sum
        agg = await qset.clone().annotate(
            dur_sum=Sum("call_duration"),
            cost_sum=Sum("cost"),
        ).values("dur_sum", "cost_sum")
        if agg and len(agg) > 0:
            overall_duration_sum = float(agg[0].get("dur_sum")) if agg[0].get("dur_sum") is not None else None
            overall_cost_sum = float(agg[0].get("cost_sum")) if agg[0].get("cost_sum") is not None else None
    except Exception:
        # keep None if aggregate functions unavailable
        pass

    return PaginatedLocalLogs(
        success=True,
        pagination=Pagination(page=page, page_size=page_size, total=total),
        logs=payload,
        aggregates=LocalAggregates(
            page_logs=len(payload),
            page_duration_sum=page_duration_sum if len(payload) else None,
            page_cost_sum=page_cost_sum if len(payload) else None,
            overall_duration_sum=overall_duration_sum,
            overall_cost_sum=overall_cost_sum,
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
        cost=float(getattr(cl, "cost", 0)) if getattr(cl, "cost", None) is not None else None,
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
    summary="Export my local call logs to CSV",
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
        "call_id", "cost", "call_ended_at", "call_ended_reason", "call_duration",
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
            getattr(cl, "cost", None),
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


# ───────────────────────────────────────────────────────────────────────────────
# VAPI Call Logs (scoped to user's assistants/phones)
# ───────────────────────────────────────────────────────────────────────────────

@router.get(
    "/me/vapi-call-logs",
    response_model=PaginatedVapiLogs,
    summary="Get my VAPI call logs (scoped to my assistants/phone numbers)",
)
async def get_my_vapi_call_logs(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="Filter by VAPI status"),
    transferred: Optional[bool] = Query(None, description="Filter by isTransferred"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt >=)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (VAPI startedAt <=)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_vapi_env()
    a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

    url = "https://api.vapi.ai/call/"
    headers = get_headers()

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
        raw = resp.json()
        all_calls: list[dict] = raw if isinstance(raw, list) else []

    scoped = [c for c in all_calls if _matches_user_vapi_scope(c, a_ids, p_ids)]

    if status:
        s = status.lower()
        scoped = [c for c in scoped if (c.get("status") or "").lower() == s]
    if transferred is not None:
        scoped = [c for c in scoped if bool(c.get("isTransferred")) is transferred]

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] >= df.isoformat())]
    if dt:
        scoped = [c for c in scoped if (c.get("startedAt") and c["startedAt"][:10] <= dt.isoformat())]

    def sort_key(x: dict):
        return (x.get("startedAt") or "", x.get("id") or "")
    scoped.sort(key=sort_key, reverse=True)

    total = len(scoped)
    offset = (page - 1) * page_size
    paged = scoped[offset: offset + page_size]

    models = [VapiCallLogModel(**c) for c in paged]

    return PaginatedVapiLogs(
        success=True,
        total=total,
        logs=models,
        message=f"Fetched {len(models)} of {total} VAPI call logs",
    )


@router.get(
    "/me/vapi-call-logs/{call_id}",
    response_model=VapiCallLogModel,
    summary="Get a single VAPI call (scoped to me)",
)
async def get_my_vapi_call(call_id: str, current_user: User = Depends(get_current_user)):
    _require_vapi_env()
    a_ids, p_ids = await _user_assistant_and_phone_sets(current_user)

    url = f"https://api.vapi.ai/call/{call_id}"
    headers = get_headers()

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {resp.text}")
        data = resp.json()

    if not _matches_user_vapi_scope(data, a_ids, p_ids):
        raise HTTPException(status_code=404, detail="Call not found")

    return VapiCallLogModel(**data)
