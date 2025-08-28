# # controllers/campaign_controller.py
# import asyncio
# from datetime import datetime, date, time, timedelta
# from typing import Annotated, List, Optional

# import pytz
# import requests
# from fastapi import APIRouter, HTTPException, Depends
# from fastapi.responses import StreamingResponse

# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from apscheduler.triggers.cron import CronTrigger
# from apscheduler.triggers.date import DateTrigger

# from tortoise.expressions import Q  # <-- IMPORTANT: for OR filters

# from models.auth import User
# from models.file import File as FileModel
# from models.lead import Lead
# from models.call_log import CallLog
# from models.assistant import Assistant
# from models.campaign import (
#     Campaign,
#     CampaignLeadProgress,
#     CampaignStatus,
#     CampaignSelectionMode,
# )

# from helpers.token_helper import get_current_user
# from helpers.vapi_helper import get_headers
# from controllers.call_controller import get_call_details  # re-use your existing

# from pydantic import BaseModel, Field

# router = APIRouter()

# # ------------- APScheduler (one global async scheduler) -------------
# scheduler: Optional[AsyncIOScheduler] = None


# def _get_scheduler() -> AsyncIOScheduler:
#     global scheduler
#     if scheduler is None:
#         scheduler = AsyncIOScheduler()
#         scheduler.start()
#     return scheduler


# # ------------- Schemas -------------
# class CampaignCreatePayload(BaseModel):
#     name: str = Field(..., min_length=2, max_length=255)
#     file_id: int
#     assistant_id: int

#     # lead selection
#     selection_mode: CampaignSelectionMode = CampaignSelectionMode.ALL
#     include_lead_ids: Optional[List[int]] = None  # used if mode=ONLY
#     exclude_lead_ids: Optional[List[int]] = None  # used if mode=SKIP

#     # schedule window
#     timezone: str = "America/Los_Angeles"
#     days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri
#     daily_start: str = "09:00"   # "HH:MM" 24h
#     daily_end: str = "18:00"     # "HH:MM"
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None

#     # pacing
#     calls_per_minute: int = 10
#     parallel_calls: int = 2

#     # retry policy
#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class CampaignUpdateSchedulePayload(BaseModel):
#     timezone: Optional[str] = None
#     days_of_week: Optional[List[int]] = None
#     daily_start: Optional[str] = None
#     daily_end: Optional[str] = None
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None


# class RetryPolicyPayload(BaseModel):
#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class RunNowPayload(BaseModel):
#     batch_size: int = 5   # how many leads to try right now


# # ------------- Helpers -------------
# BUSY_REASONS = {"busy", "user-busy", "target-busy", "no-answer", "call-rejected"}


# def _within_window(c: Campaign, now: datetime) -> bool:
#     """Check if 'now' is within days + daily window + start/end dates."""
#     tz = pytz.timezone(c.timezone or "America/Los_Angeles")
#     now_local = now.astimezone(tz)
#     if c.start_at and now_local < c.start_at.astimezone(tz):
#         return False
#     if c.end_at and now_local > c.end_at.astimezone(tz):
#         return False

#     if c.days_of_week:
#         # Python weekday: Mon=0 ... Sun=6
#         if now_local.weekday() not in set(c.days_of_week):
#             return False

#     def _parse_hhmm(s: Optional[str]) -> Optional[time]:
#         if not s:
#             return None
#         h, m = s.split(":")
#         return time(hour=int(h), minute=int(m))

#     start_t = _parse_hhmm(c.daily_start) or time(0, 0)
#     end_t = _parse_hhmm(c.daily_end) or time(23, 59)

#     cur_t = now_local.time()
#     return start_t <= cur_t <= end_t


# async def _compute_lead_ids_for_campaign(c: Campaign) -> List[int]:
#     """Build the lead set from file & selection mode; skip DNC leads."""
#     base = Lead.filter(file_id=c.file_id, dnc=False)

#     if c.selection_mode == CampaignSelectionMode.ONLY:
#         if not c.include_lead_ids:
#             return []
#         base = base.filter(id__in=c.include_lead_ids)

#     elif c.selection_mode == CampaignSelectionMode.SKIP:
#         if c.exclude_lead_ids:
#             base = base.exclude(id__in=c.exclude_lead_ids)

#     leads = await base.all()
#     return [l.id for l in leads]


# async def _ensure_progress_rows(campaign: Campaign) -> int:
#     """Create CampaignLeadProgress rows for selected leads if missing. Returns count added."""
#     lead_ids = await _compute_lead_ids_for_campaign(campaign)
#     if not lead_ids:
#         return 0

#     existing_ids = await CampaignLeadProgress.filter(
#         campaign_id=campaign.id
#     ).values_list("lead_id", flat=True)
#     existing_set = set(existing_ids)
#     to_create = [lid for lid in lead_ids if lid not in existing_set]

#     objs = [
#         CampaignLeadProgress(campaign=campaign, lead_id=lid, status="pending")
#         for lid in to_create
#     ]
#     if objs:
#         await CampaignLeadProgress.bulk_create(objs)
#     return len(objs)


# async def _place_vapi_call(user: User, assistant: Assistant, lead: Lead) -> str:
#     """Call VAPI like in your assistant controller; returns call_id."""
#     if not assistant.vapi_assistant_id:
#         raise HTTPException(status_code=400, detail="Assistant has no VAPI ID")
#     if not assistant.vapi_phone_uuid or not assistant.attached_Number:
#         raise HTTPException(status_code=400, detail="Assistant has no attached phone number")

#     # Normalize E.164 (default US +1; adapt if you store country)
#     mobile_raw = (lead.mobile or "").strip()
#     if not mobile_raw:
#         raise HTTPException(status_code=400, detail="Lead has no mobile number")
#     number_e164 = mobile_raw if mobile_raw.startswith("+") else f"+1{mobile_raw}"

#     payload = {
#         "name": f"Campaign {assistant.name}",
#         "assistantId": assistant.vapi_assistant_id,
#         "customer": {
#             "numberE164CheckEnabled": True,
#             "extension": None,
#             "number": number_e164,
#         },
#         "phoneNumberId": assistant.vapi_phone_uuid,
#         "assistantOverrides": {
#             "variableValues": {
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "mobile_no": number_e164,
#                 "add_date": (lead.add_date.isoformat() if isinstance(lead.add_date, (datetime, date)) else None),
#                 "custom_field_01": (lead.other_data or {}).get("Custom_0"),
#                 "custom_field_02": (lead.other_data or {}).get("Custom_1"),
#             },
#             "maxDurationSeconds": 10000,
#             "silenceTimeoutSeconds": 120,
#             "startSpeakingPlan": {
#                 "waitSeconds": 1.0,
#                 "smartEndpointingEnabled": True,
#                 "transcriptionEndpointingPlan": {
#                     "onPunctuationSeconds": 0.5,
#                     "onNoPunctuationSeconds": 3.0,
#                     "onNumberSeconds": 1.0,
#                 },
#             },
#             "stopSpeakingPlan": {
#                 "numWords": 0,
#                 "voiceSeconds": 0.5,
#                 "backoffSeconds": 2.0,
#             },
#         },
#     }

#     resp = requests.post("https://api.vapi.ai/call", json=payload, headers=get_headers())
#     if resp.status_code not in (200, 201):
#         try:
#             msg = resp.json().get("message", resp.text)
#         except Exception:
#             msg = resp.text
#         raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {msg}")

#     data = resp.json()
#     call_id = data.get("id")
#     if not call_id:
#         raise HTTPException(status_code=400, detail="VAPI response missing call ID")

#     # Persist immediate call log shell
#     started_at = data.get("createdAt")
#     await CallLog.create(
#         user=user,
#         call_id=call_id,
#         call_started_at=(
#             datetime.fromisoformat(started_at.replace("Z", "+00:00")) if isinstance(started_at, str) else None
#         ),
#         customer_name=f"{(lead.first_name or '').strip()} {(lead.last_name or '').strip()}".strip() or "Unknown",
#         customer_number=number_e164,
#         lead_id=lead.id,
#     )

#     # Schedule your detailed fetcher (re-using existing one)
#     sch = _get_scheduler()
#     processing_delay = min(120 + (10000 // 600), 1800)  # seconds
#     run_at = datetime.utcnow() + timedelta(seconds=processing_delay)
#     sch.add_job(
#         get_call_details,
#         DateTrigger(run_date=run_at),
#         args=[call_id, processing_delay, user.id, lead.id],
#     )

#     return call_id


# async def _process_call_outcome(campaign_id: int, lead_id: int, user_id: int, call_id: str):
#     """After get_call_details updates CallLog, set progress / retries."""
#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     prog = await CampaignLeadProgress.get_or_none(campaign_id=campaign_id, lead_id=lead_id)
#     if not prog:
#         return

#     cl = await CallLog.get_or_none(call_id=call_id)
#     if not cl:
#         # If not landed yet, try again in 2 minutes
#         _get_scheduler().add_job(
#             _process_call_outcome,
#             DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=2)),
#             args=[campaign_id, lead_id, user_id, call_id],
#         )
#         return

#     ended_reason = (cl.call_ended_reason or "").lower().strip()
#     prog.last_ended_reason = ended_reason
#     prog.status = "completed"  # optimistic default

#     # busy/no-answer retry
#     if ended_reason in BUSY_REASONS and c.retry_on_busy and prog.attempt_count < c.max_attempts:
#         prog.status = "retry_scheduled"
#         prog.next_attempt_at = datetime.utcnow() + timedelta(minutes=c.busy_retry_delay_minutes)
#     elif ended_reason in {"failed", "error"}:
#         prog.status = "failed"

#     await prog.save()


# async def _tick_campaign(campaign_id: int):
#     """Periodic job for a campaign: window + pacing + retries + calling."""
#     now = datetime.utcnow()
#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     if c.status not in {CampaignStatus.SCHEDULED, CampaignStatus.RUNNING}:
#         return

#     if not _within_window(c, now):
#         return

#     # pacing
#     batch = max(1, min(c.calls_per_minute, 50))
#     parallel = max(1, min(c.parallel_calls, 10))

#     # eligible leads
#     q = CampaignLeadProgress.filter(
#         campaign_id=c.id,
#         status__in=["pending", "retry_scheduled"],
#     ).order_by("id")

#     # next_attempt gate for retries  (FIXED: use Q() OR)
#     q = q.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))

#     todo: List[CampaignLeadProgress] = await q.limit(batch).all()
#     if not todo:
#         remaining = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["pending", "retry_scheduled", "calling"]
#         ).count()
#         if remaining == 0:
#             c.status = CampaignStatus.COMPLETED
#             await c.save()
#         return

#     sem = asyncio.Semaphore(parallel)

#     async def _one(prog: CampaignLeadProgress):
#         async with sem:
#             lead = await Lead.get_or_none(id=prog.lead_id)
#             if not lead:
#                 prog.status = "failed"
#                 await prog.save()
#                 return

#             try:
#                 prog.status = "calling"
#                 prog.attempt_count += 1
#                 prog.last_attempt_at = datetime.utcnow()
#                 await prog.save()

#                 call_id = await _place_vapi_call(c.user, c.assistant, lead)
#                 prog.last_call_id = call_id
#                 await prog.save()

#                 # when details land, evaluate outcome
#                 _get_scheduler().add_job(
#                     _process_call_outcome,
#                     DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=12)),
#                     args=[c.id, lead.id, c.user.id, call_id],
#                 )

#             except HTTPException as e:
#                 prog.status = "failed"
#                 prog.last_ended_reason = f"error:{e.detail}"
#                 await prog.save()
#             except Exception as e:
#                 prog.status = "failed"
#                 prog.last_ended_reason = f"error:{repr(e)}"
#                 await prog.save()

#     await asyncio.gather(*[_one(p) for p in todo])

#     c.last_tick_at = datetime.utcnow()
#     c.status = CampaignStatus.RUNNING
#     await c.save()


# def _schedule_campaign_job(campaign_id: int, timezone: str):
#     """Run every minute; window is checked inside _tick_campaign."""
#     sch = _get_scheduler()
#     job_id = f"campaign:{campaign_id}"
#     # Remove old
#     old = sch.get_job(job_id)
#     if old:
#         old.remove()

#     tz = pytz.timezone(timezone or "UTC")
#     sch.add_job(
#         _tick_campaign,
#         CronTrigger(minute="*/1", timezone=tz),
#         args=[campaign_id],
#         id=job_id,
#         replace_existing=True,
#         misfire_grace_time=60,
#         coalesce=True,
#         max_instances=1,
#     )


# # ------------- Routes -------------
# @router.post("/campaigns")
# async def create_campaign(payload: CampaignCreatePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     file = await FileModel.get_or_none(id=payload.file_id, user_id=user.id)
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found for this user")

#     assistant = await Assistant.get_or_none(id=payload.assistant_id, user_id=user.id)
#     if not assistant:
#         raise HTTPException(status_code=404, detail="Assistant not found")

#     if not assistant.vapi_assistant_id or not assistant.vapi_phone_uuid:
#         raise HTTPException(status_code=400, detail="Assistant must have VAPI ID and attached number")

#     c = await Campaign.create(
#         user=user,
#         name=payload.name,
#         file=file,
#         assistant=assistant,
#         selection_mode=payload.selection_mode,
#         include_lead_ids=payload.include_lead_ids,
#         exclude_lead_ids=payload.exclude_lead_ids,
#         timezone=payload.timezone,
#         days_of_week=payload.days_of_week,
#         daily_start=payload.daily_start,
#         daily_end=payload.daily_end,
#         start_at=payload.start_at,
#         end_at=payload.end_at,
#         calls_per_minute=payload.calls_per_minute,
#         parallel_calls=payload.parallel_calls,
#         retry_on_busy=payload.retry_on_busy,
#         busy_retry_delay_minutes=payload.busy_retry_delay_minutes,
#         max_attempts=payload.max_attempts,
#         status=CampaignStatus.SCHEDULED,
#     )

#     added = await _ensure_progress_rows(c)
#     _schedule_campaign_job(c.id, c.timezone)

#     return {
#         "success": True,
#         "campaign_id": c.id,
#         "detail": f"Campaign created. {added} lead(s) queued."
#     }


# @router.get("/campaigns")
# async def list_campaigns(user: Annotated[User, Depends(get_current_user)]):
#     cs = await Campaign.filter(user_id=user.id).order_by("-created_at").all()
#     out = []
#     for c in cs:
#         total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#         done = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#         ).count()
#         out.append({
#             "id": c.id,
#             "name": c.name,
#             "status": c.status,
#             "file_id": c.file_id,
#             "assistant_id": c.assistant_id,
#             "timezone": c.timezone,
#             "window": {"days": c.days_of_week, "start": c.daily_start, "end": c.daily_end},
#             "start_at": c.start_at,
#             "end_at": c.end_at,
#             "calls_per_minute": c.calls_per_minute,
#             "parallel_calls": c.parallel_calls,
#             "retry_on_busy": c.retry_on_busy,
#             "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#             "max_attempts": c.max_attempts,
#             "counts": {"total": total, "completed_or_failed": done},
#             "created_at": c.created_at,
#         })
#     return out


# @router.get("/campaigns/{campaign_id}")
# async def get_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#     pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
#     retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
#     calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
#     done = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#     ).count()

#     return {
#         "id": c.id,
#         "name": c.name,
#         "status": c.status,
#         "file_id": c.file_id,
#         "assistant_id": c.assistant_id,
#         "selection_mode": c.selection_mode,
#         "include_lead_ids": c.include_lead_ids,
#         "exclude_lead_ids": c.exclude_lead_ids,
#         "timezone": c.timezone,
#         "days_of_week": c.days_of_week,
#         "daily_start": c.daily_start,
#         "daily_end": c.daily_end,
#         "start_at": c.start_at,
#         "end_at": c.end_at,
#         "calls_per_minute": c.calls_per_minute,
#         "parallel_calls": c.parallel_calls,
#         "retry_on_busy": c.retry_on_busy,
#         "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#         "max_attempts": c.max_attempts,
#         "totals": {
#             "total": total,
#             "pending": pending,
#             "retry": retrying,
#             "calling": calling,
#             "done": done
#         }
#     }


# @router.delete("/campaigns/{campaign_id}")
# async def delete_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     # kill scheduler job
#     sch = _get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     await CampaignLeadProgress.filter(campaign_id=campaign_id).delete()
#     await c.delete()
#     return {"success": True, "detail": "Campaign deleted"}


# @router.post("/campaigns/{campaign_id}/schedule")
# async def update_schedule(campaign_id: int,
#                           payload: CampaignUpdateSchedulePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     if payload.timezone is not None:
#         c.timezone = payload.timezone
#     if payload.days_of_week is not None:
#         c.days_of_week = payload.days_of_week
#     if payload.daily_start is not None:
#         c.daily_start = payload.daily_start
#     if payload.daily_end is not None:
#         c.daily_end = payload.daily_end
#     if payload.start_at is not None:
#         c.start_at = payload.start_at
#     if payload.end_at is not None:
#         c.end_at = payload.end_at

#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     return {"success": True, "detail": "Schedule updated"}


# @router.post("/campaigns/{campaign_id}/retry-policy")
# async def update_retry(campaign_id: int,
#                        payload: RetryPolicyPayload,
#                        user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     c.retry_on_busy = payload.retry_on_busy
#     c.busy_retry_delay_minutes = payload.busy_retry_delay_minutes
#     c.max_attempts = payload.max_attempts
#     await c.save()
#     return {"success": True, "detail": "Retry policy updated"}


# @router.post("/campaigns/{campaign_id}/pause")
# async def pause_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.PAUSED
#     await c.save()
#     return {"success": True, "detail": "Campaign paused"}


# @router.post("/campaigns/{campaign_id}/resume")
# async def resume_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.SCHEDULED
#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     return {"success": True, "detail": "Campaign resumed"}


# @router.post("/campaigns/{campaign_id}/stop")
# async def stop_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.STOPPED
#     await c.save()

#     sch = _get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     return {"success": True, "detail": "Campaign stopped"}


# @router.post("/campaigns/{campaign_id}/run-now")
# async def run_now(campaign_id: int, payload: RunNowPayload,
#                   user: Annotated[User, Depends(get_current_user)]):
#     """Fire a small batch immediately (ignores window); useful for testing."""
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     await c.fetch_related("assistant", "user")

#     todo = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["pending", "retry_scheduled"]
#     ).order_by("id").limit(payload.batch_size).all()

#     if not todo:
#         return {"success": True, "detail": "No eligible leads to call right now."}

#     for prog in todo:
#         lead = await Lead.get_or_none(id=prog.lead_id)
#         if not lead:
#             prog.status = "failed"
#             await prog.save()
#             continue

#         try:
#             prog.status = "calling"
#             prog.attempt_count += 1
#             prog.last_attempt_at = datetime.utcnow()
#             await prog.save()

#             call_id = await _place_vapi_call(c.user, c.assistant, lead)
#             prog.last_call_id = call_id
#             await prog.save()

#             _get_scheduler().add_job(
#                 _process_call_outcome,
#                 DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=12)),
#                 args=[c.id, lead.id, c.user.id, call_id],
#             )
#         except Exception as e:
#             prog.status = "failed"
#             prog.last_ended_reason = f"error:{repr(e)}"
#             await prog.save()

#     return {"success": True, "detail": f"Triggered {len(todo)} lead(s) now."}


# # ---------- (Optional) Export an .ics for Google Calendar ----------
# def _ics_for_campaign(c: Campaign) -> str:
#     tz = c.timezone or "UTC"

#     # Map Python weekday (Mon=0..Sun=6) → RRULE BYDAY
#     map_rr = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}
#     byday = ",".join(map_rr.get(d, "MO") for d in (c.days_of_week or [0, 1, 2, 3, 4]))

#     import pytz as _pytz
#     zone = _pytz.timezone(tz)
#     now_local = datetime.now(zone)
#     hh, mm = (c.daily_start or "09:00").split(":")
#     start_local = (c.start_at.astimezone(zone) if c.start_at else now_local).replace(
#         hour=int(hh), minute=int(mm), second=0, microsecond=0
#     )
#     dtstart = start_local.strftime("%Y%m%dT%H%M%S")

#     uid = f"campaign-{c.id}@yourapp"
#     lines = [
#         "BEGIN:VCALENDAR",
#         "VERSION:2.0",
#         "PRODID:-//YourApp//Campaign//EN",
#         "CALSCALE:GREGORIAN",
#         "METHOD:PUBLISH",
#         "BEGIN:VEVENT",
#         f"UID:{uid}",
#         f"SUMMARY:Call Campaign — {c.name}",
#         f"DTSTART;TZID={tz}:{dtstart}",
#         f"RRULE:FREQ=WEEKLY;BYDAY={byday}",
#         f"DESCRIPTION:Calls placed within {c.daily_start}-{c.daily_end} local time. Server handles pacing & retries.",
#         "END:VEVENT",
#         "END:VCALENDAR",
#     ]
#     return "\r\n".join(lines)


# @router.get("/campaigns/{campaign_id}/calendar.ics")
# async def campaign_calendar_ics(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     ics = _ics_for_campaign(c)
#     return StreamingResponse(
#         content=iter([ics]),
#         media_type="text/calendar",
#         headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.ics"'},
#     )







# # controllers/campaign_controller.py
# import asyncio
# from datetime import datetime, date, time, timedelta
# from typing import Annotated, List, Optional
# from controllers.call_controller import get_call_details
# import pytz
# import requests
# from fastapi import APIRouter, HTTPException, Depends
# from fastapi.responses import StreamingResponse
# from scheduler.campaign_scheduler import get_scheduler as _get_scheduler
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from apscheduler.triggers.cron import CronTrigger
# from apscheduler.triggers.date import DateTrigger

# from tortoise.expressions import Q

# from models.auth import User
# from models.file import File as FileModel
# from models.lead import Lead
# from models.call_log import CallLog
# from models.assistant import Assistant
# from models.campaign import (
#     Campaign,
#     CampaignLeadProgress,
#     CampaignStatus,
#     CampaignSelectionMode,
# )

# from helpers.token_helper import get_current_user
# from helpers.vapi_helper import get_headers

# from pydantic import BaseModel, Field

# router = APIRouter()

# # ------------- APScheduler (one global async scheduler) -------------
# scheduler: Optional[AsyncIOScheduler] = None


# def _get_scheduler() -> AsyncIOScheduler:
#     global scheduler
#     if scheduler is None:
#         scheduler = AsyncIOScheduler()
#         scheduler.start()
#     return scheduler


# # ------------- Schemas -------------
# class CampaignCreatePayload(BaseModel):
#     name: str = Field(..., min_length=2, max_length=255)
#     file_id: int
#     assistant_id: int

#     selection_mode: CampaignSelectionMode = CampaignSelectionMode.ALL
#     include_lead_ids: Optional[List[int]] = None
#     exclude_lead_ids: Optional[List[int]] = None

#     timezone: str = "America/Los_Angeles"
#     days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
#     daily_start: str = "09:00"
#     daily_end: str = "18:00"
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None

#     calls_per_minute: int = 10
#     parallel_calls: int = 2

#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class CampaignUpdateSchedulePayload(BaseModel):
#     timezone: Optional[str] = None
#     days_of_week: Optional[List[int]] = None
#     daily_start: Optional[str] = None
#     daily_end: Optional[str] = None
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None


# class RetryPolicyPayload(BaseModel):
#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class RunNowPayload(BaseModel):
#     batch_size: int = 5


# # ------------- Helpers -------------
# BUSY_REASONS = {"busy", "user-busy", "target-busy", "no-answer", "call-rejected"}


# def _within_window(c: Campaign, now: datetime) -> bool:
#     tz = pytz.timezone(c.timezone or "America/Los_Angeles")
#     now_local = now.astimezone(tz)
#     if c.start_at and now_local < c.start_at.astimezone(tz):
#         return False
#     if c.end_at and now_local > c.end_at.astimezone(tz):
#         return False

#     if c.days_of_week and now_local.weekday() not in set(c.days_of_week):
#         return False

#     def _parse_hhmm(s: Optional[str]) -> Optional[time]:
#         if not s:
#             return None
#         h, m = s.split(":")
#         return time(hour=int(h), minute=int(m))

#     start_t = _parse_hhmm(c.daily_start) or time(0, 0)
#     end_t = _parse_hhmm(c.daily_end) or time(23, 59)
#     return start_t <= now_local.time() <= end_t


# async def _compute_lead_ids_for_campaign(c: Campaign) -> List[int]:
#     base = Lead.filter(file_id=c.file_id, dnc=False)

#     if c.selection_mode == CampaignSelectionMode.ONLY:
#         if not c.include_lead_ids:
#             return []
#         base = base.filter(id__in=c.include_lead_ids)
#     elif c.selection_mode == CampaignSelectionMode.SKIP:
#         if c.exclude_lead_ids:
#             base = base.exclude(id__in=c.exclude_lead_ids)

#     leads = await base.all()
#     return [l.id for l in leads]


# async def _ensure_progress_rows(campaign: Campaign) -> int:
#     lead_ids = await _compute_lead_ids_for_campaign(campaign)
#     if not lead_ids:
#         return 0

#     existing_ids = await CampaignLeadProgress.filter(
#         campaign_id=campaign.id
#     ).values_list("lead_id", flat=True)
#     existing_set = set(existing_ids)
#     to_create = [lid for lid in lead_ids if lid not in existing_set]

#     objs = [
#         CampaignLeadProgress(campaign=campaign, lead_id=lid, status="pending")
#         for lid in to_create
#     ]
#     if objs:
#         await CampaignLeadProgress.bulk_create(objs)
#     return len(objs)


# # ---------- NEW: external helper you can call from other controllers ----------
# async def trigger_campaign_refresh_for_file(file_id: int, and_tick: bool = True) -> dict:
#     """
#     Find SCHEDULED/RUNNING campaigns tied to this file and:
#       - ensure CampaignLeadProgress rows exist for all currently-eligible leads
#       - optionally schedule an immediate tick so calls start quickly
#     Returns a small summary.
#     """
#     campaigns = await Campaign.filter(
#         file_id=file_id,
#         status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING],
#     ).all()

#     total_added = 0
#     sch = _get_scheduler()
#     for c in campaigns:
#         added = await _ensure_progress_rows(c)
#         total_added += added
#         if and_tick:
#             # Nudge the minute scheduler so new leads don’t wait for the next cron
#             sch.add_job(
#                 _tick_campaign,
#                 DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=1)),
#                 args=[c.id],
#             )

#     return {"campaigns_checked": len(campaigns), "leads_added": total_added}


# async def _place_vapi_call(user: User, assistant: Assistant, lead: Lead) -> str:
#     if not assistant.vapi_assistant_id:
#         raise HTTPException(status_code=400, detail="Assistant has no VAPI ID")
#     if not assistant.vapi_phone_uuid or not assistant.attached_Number:
#         raise HTTPException(status_code=400, detail="Assistant has no attached phone number")

#     mobile_raw = (lead.mobile or "").strip()
#     if not mobile_raw:
#         raise HTTPException(status_code=400, detail="Lead has no mobile number")
#     number_e164 = mobile_raw if mobile_raw.startswith("+") else f"+1{mobile_raw}"

#     payload = {
#         "name": f"Campaign {assistant.name}",
#         "assistantId": assistant.vapi_assistant_id,
#         "customer": {
#             "numberE164CheckEnabled": True,
#             "extension": None,
#             "number": number_e164,
#         },
#         "phoneNumberId": assistant.vapi_phone_uuid,
#         "assistantOverrides": {
#             "variableValues": {
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "mobile_no": number_e164,
#                 "add_date": (lead.add_date.isoformat() if isinstance(lead.add_date, (datetime, date)) else None),
#                 "custom_field_01": (lead.other_data or {}).get("Custom_0"),
#                 "custom_field_02": (lead.other_data or {}).get("Custom_1"),
#             },
#             "maxDurationSeconds": 10000,
#             "silenceTimeoutSeconds": 120,
#             "startSpeakingPlan": {
#                 "waitSeconds": 1.0,
#                 "smartEndpointingEnabled": True,
#                 "transcriptionEndpointingPlan": {
#                     "onPunctuationSeconds": 0.5,
#                     "onNoPunctuationSeconds": 3.0,
#                     "onNumberSeconds": 1.0,
#                 },
#             },
#             "stopSpeakingPlan": {
#                 "numWords": 0,
#                 "voiceSeconds": 0.5,
#                 "backoffSeconds": 2.0,
#             },
#         },
#     }

#     resp = requests.post("https://api.vapi.ai/call", json=payload, headers=get_headers())
#     if resp.status_code not in (200, 201):
#         try:
#             msg = resp.json().get("message", resp.text)
#         except Exception:
#             msg = resp.text
#         raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {msg}")

#     data = resp.json()
#     call_id = data.get("id")
#     if not call_id:
#         raise HTTPException(status_code=400, detail="VAPI response missing call ID")

#     started_at = data.get("createdAt")
#     await CallLog.create(
#         user=user,
#         call_id=call_id,
#         call_started_at=(
#             datetime.fromisoformat(started_at.replace("Z", "+00:00")) if isinstance(started_at, str) else None
#         ),
#         customer_name=f"{(lead.first_name or '').strip()} {(lead.last_name or '').strip()}".strip() or "Unknown",
#         customer_number=number_e164,
#         lead_id=lead.id,
#     )

#     sch = _get_scheduler()
#     processing_delay = min(120 + (10000 // 600), 1800)
#     run_at = datetime.utcnow() + timedelta(seconds=processing_delay)
#     sch.add_job(
#         get_call_details,
#         DateTrigger(run_date=run_at),
#         args=[call_id, processing_delay, user.id, lead.id],
#     )

#     return call_id


# async def _process_call_outcome(campaign_id: int, lead_id: int, user_id: int, call_id: str):
#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     prog = await CampaignLeadProgress.get_or_none(campaign_id=campaign_id, lead_id=lead_id)
#     if not prog:
#         return

#     cl = await CallLog.get_or_none(call_id=call_id)
#     if not cl:
#         _get_scheduler().add_job(
#             _process_call_outcome,
#             DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=2)),
#             args=[campaign_id, lead_id, user_id, call_id],
#         )
#         return

#     ended_reason = (cl.call_ended_reason or "").lower().strip()
#     prog.last_ended_reason = ended_reason
#     prog.status = "completed"

#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return

#     if ended_reason in BUSY_REASONS and c.retry_on_busy and prog.attempt_count < c.max_attempts:
#         prog.status = "retry_scheduled"
#         prog.next_attempt_at = datetime.utcnow() + timedelta(minutes=c.busy_retry_delay_minutes)
#     elif ended_reason in {"failed", "error"}:
#         prog.status = "failed"

#     await prog.save()


# async def _tick_campaign(campaign_id: int):
#     now = datetime.utcnow()
#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     if c.status not in {CampaignStatus.SCHEDULED, CampaignStatus.RUNNING}:
#         return

#     # auto-absorb new leads
#     try:
#         added = await _ensure_progress_rows(c)
#         if added:
#             print(f"[campaign {c.id}] auto-synced {added} new lead(s).")
#     except Exception as e:
#         print(f"[campaign {c.id}] sync error: {e!r}")

#     if not _within_window(c, now):
#         return

#     batch = max(1, min(c.calls_per_minute, 50))
#     parallel = max(1, min(c.parallel_calls, 10))

#     q = CampaignLeadProgress.filter(
#         campaign_id=c.id,
#         status__in=["pending", "retry_scheduled"],
#     ).order_by("id")
#     q = q.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))

#     todo: List[CampaignLeadProgress] = await q.limit(batch).all()
#     if not todo:
#         remaining = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["pending", "retry_scheduled", "calling"]
#         ).count()
#         if remaining == 0:
#             c.status = CampaignStatus.COMPLETED
#             await c.save()
#         return

#     sem = asyncio.Semaphore(parallel)

#     async def _one(prog: CampaignLeadProgress):
#         async with sem:
#             lead = await Lead.get_or_none(id=prog.lead_id)
#             if not lead:
#                 prog.status = "failed"
#                 prog.last_ended_reason = "error:lead-missing"
#                 await prog.save()
#                 return

#             if lead.dnc:
#                 prog.status = "skipped"
#                 prog.last_ended_reason = "skipped:dnc"
#                 await prog.save()
#                 return

#             try:
#                 prog.status = "calling"
#                 prog.attempt_count += 1
#                 prog.last_attempt_at = datetime.utcnow()
#                 await prog.save()

#                 call_id = await _place_vapi_call(c.user, c.assistant, lead)
#                 prog.last_call_id = call_id
#                 await prog.save()

#                 _get_scheduler().add_job(
#                     _process_call_outcome,
#                     DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=12)),
#                     args=[c.id, lead.id, c.user.id, call_id],
#                 )

#             except HTTPException as e:
#                 detail = str(e.detail).lower()
#                 prog.status = "skipped" if ("no mobile" in detail or "mobile number" in detail) else "failed"
#                 prog.last_ended_reason = f"error:{e.detail}"
#                 await prog.save()
#             except Exception as e:
#                 prog.status = "failed"
#                 prog.last_ended_reason = f"error:{repr(e)}"
#                 await prog.save()

#     await asyncio.gather(*[_one(p) for p in todo])

#     c.last_tick_at = datetime.utcnow()
#     c.status = CampaignStatus.RUNNING
#     await c.save()


# def _schedule_campaign_job(campaign_id: int, timezone: str):
#     sch = _get_scheduler()
#     job_id = f"campaign:{campaign_id}"
#     old = sch.get_job(job_id)
#     if old:
#         old.remove()

#     tz = pytz.timezone(timezone or "UTC")
#     sch.add_job(
#         _tick_campaign,
#         CronTrigger(minute="*/1", timezone=tz),
#         args=[campaign_id],
#         id=job_id,
#         replace_existing=True,
#         misfire_grace_time=60,
#         coalesce=True,
#         max_instances=1,
#     )


# # ------------- Routes -------------
# @router.post("/campaigns")
# async def create_campaign(payload: CampaignCreatePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     file = await FileModel.get_or_none(id=payload.file_id, user_id=user.id)
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found for this user")

#     assistant = await Assistant.get_or_none(id=payload.assistant_id, user_id=user.id)
#     if not assistant:
#         raise HTTPException(status_code=404, detail="Assistant not found")

#     if not assistant.vapi_assistant_id or not assistant.vapi_phone_uuid:
#         raise HTTPException(status_code=400, detail="Assistant must have VAPI ID and attached number")

#     c = await Campaign.create(
#         user=user,
#         name=payload.name,
#         file=file,
#         assistant=assistant,
#         selection_mode=payload.selection_mode,
#         include_lead_ids=payload.include_lead_ids,
#         exclude_lead_ids=payload.exclude_lead_ids,
#         timezone=payload.timezone,
#         days_of_week=payload.days_of_week,
#         daily_start=payload.daily_start,
#         daily_end=payload.daily_end,
#         start_at=payload.start_at,
#         end_at=payload.end_at,
#         calls_per_minute=payload.calls_per_minute,
#         parallel_calls=payload.parallel_calls,
#         retry_on_busy=payload.retry_on_busy,
#         busy_retry_delay_minutes=payload.busy_retry_delay_minutes,
#         max_attempts=payload.max_attempts,
#         status=CampaignStatus.SCHEDULED,
#     )

#     added = await _ensure_progress_rows(c)
#     _schedule_campaign_job(c.id, c.timezone)

#     return {
#         "success": True,
#         "campaign_id": c.id,
#         "detail": f"Campaign created. {added} lead(s) queued."
#     }


# @router.get("/campaigns")
# async def list_campaigns(user: Annotated[User, Depends(get_current_user)]):
#     cs = await Campaign.filter(user_id=user.id).order_by("-created_at").all()
#     out = []
#     for c in cs:
#         total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#         done = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#         ).count()
#         out.append({
#             "id": c.id,
#             "name": c.name,
#             "status": c.status,
#             "file_id": c.file_id,
#             "assistant_id": c.assistant_id,
#             "timezone": c.timezone,
#             "window": {"days": c.days_of_week, "start": c.daily_start, "end": c.daily_end},
#             "start_at": c.start_at,
#             "end_at": c.end_at,
#             "calls_per_minute": c.calls_per_minute,
#             "parallel_calls": c.parallel_calls,
#             "retry_on_busy": c.retry_on_busy,
#             "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#             "max_attempts": c.max_attempts,
#             "counts": {"total": total, "completed_or_failed": done},
#             "created_at": c.created_at,
#         })
#     return out


# @router.get("/campaigns/{campaign_id}")
# async def get_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#     pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
#     retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
#     calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
#     done = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#     ).count()

#     return {
#         "id": c.id,
#         "name": c.name,
#         "status": c.status,
#         "file_id": c.file_id,
#         "assistant_id": c.assistant_id,
#         "selection_mode": c.selection_mode,
#         "include_lead_ids": c.include_lead_ids,
#         "exclude_lead_ids": c.exclude_lead_ids,
#         "timezone": c.timezone,
#         "days_of_week": c.days_of_week,
#         "daily_start": c.daily_start,
#         "daily_end": c.daily_end,
#         "start_at": c.start_at,
#         "end_at": c.end_at,
#         "calls_per_minute": c.calls_per_minute,
#         "parallel_calls": c.parallel_calls,
#         "retry_on_busy": c.retry_on_busy,
#         "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#         "max_attempts": c.max_attempts,
#         "totals": {
#             "total": total,
#             "pending": pending,
#             "retry": retrying,
#             "calling": calling,
#             "done": done
#         }
#     }


# # ---------- NEW: real-time stats endpoint ----------
# @router.get("/campaigns/{campaign_id}/stats")
# async def campaign_stats(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     """
#     Real-time snapshot for a campaign:
#       - totals breakdown (pending/retry/calling/done/total)
#       - percent complete
#       - is the campaign active in its window right now?
#       - next tick time (if scheduled)
#       - pacing & window info
#       - local and server time (for the header on UI)
#     """
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
#     tz = pytz.timezone(c.timezone or "UTC")

#     # segment counts
#     total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#     pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
#     retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
#     calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
#     done = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#     ).count()

#     # progress percent
#     pct = 0
#     if total > 0:
#         pct = int(round((done / total) * 100))

#     # next tick (from APScheduler job, if any)
#     sch = _get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     next_tick_at = job.next_run_time if job else None

#     # how many are eligible to dial right now (backlog)
#     eligible_now = await CampaignLeadProgress.filter(
#         campaign_id=c.id,
#         status__in=["pending", "retry_scheduled"]
#     ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=datetime.utcnow())).count()

#     active_now = _within_window(c, datetime.utcnow()) and c.status in {
#         CampaignStatus.SCHEDULED, CampaignStatus.RUNNING
#     }

#     return {
#         "id": c.id,
#         "name": c.name,
#         "status": c.status,
#         "timezone": c.timezone,
#         "window": {
#             "days_of_week": c.days_of_week,
#             "daily_start": c.daily_start,
#             "daily_end": c.daily_end,
#             "start_at": c.start_at,
#             "end_at": c.end_at,
#         },
#         "now": {
#             "server_utc": now_utc.isoformat(),
#             "local": now_utc.astimezone(tz).isoformat(),
#         },
#         "active_now": active_now,
#         "last_tick_at": c.last_tick_at,
#         "next_tick_at": next_tick_at.isoformat() if next_tick_at else None,
#         "pacing": {
#             "calls_per_minute": c.calls_per_minute,
#             "parallel_calls": c.parallel_calls,
#         },
#         "totals": {
#             "total": total,
#             "pending": pending,
#             "retry": retrying,
#             "calling": calling,
#             "done": done,
#         },
#         "percent_complete": pct,
#         "counts": {  # convenience mirror for your cards
#             "total": total,
#             "done": done,
#         },
#         "eligible_now": eligible_now,
#     }


# @router.delete("/campaigns/{campaign_id}")
# async def delete_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     sch = _get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     await CampaignLeadProgress.filter(campaign_id=campaign_id).delete()
#     await c.delete()
#     return {"success": True, "detail": "Campaign deleted"}


# @router.post("/campaigns/{campaign_id}/schedule")
# async def update_schedule(campaign_id: int,
#                           payload: CampaignUpdateSchedulePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     if payload.timezone is not None:
#         c.timezone = payload.timezone
#     if payload.days_of_week is not None:
#         c.days_of_week = payload.days_of_week
#     if payload.daily_start is not None:
#         c.daily_start = payload.daily_start
#     if payload.daily_end is not None:
#         c.daily_end = payload.daily_end
#     if payload.start_at is not None:
#         c.start_at = payload.start_at
#     if payload.end_at is not None:
#         c.end_at = payload.end_at

#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     await _ensure_progress_rows(c)
#     return {"success": True, "detail": "Schedule updated"}


# @router.post("/campaigns/{campaign_id}/retry-policy")
# async def update_retry(campaign_id: int,
#                        payload: RetryPolicyPayload,
#                        user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     c.retry_on_busy = payload.retry_on_busy
#     c.busy_retry_delay_minutes = payload.busy_retry_delay_minutes
#     c.max_attempts = payload.max_attempts
#     await c.save()
#     return {"success": True, "detail": "Retry policy updated"}


# @router.post("/campaigns/{campaign_id}/pause")
# async def pause_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.PAUSED
#     await c.save()
#     return {"success": True, "detail": "Campaign paused"}


# @router.post("/campaigns/{campaign_id}/resume")
# async def resume_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.SCHEDULED
#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     await _ensure_progress_rows(c)
#     return {"success": True, "detail": "Campaign resumed"}


# @router.post("/campaigns/{campaign_id}/stop")
# async def stop_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.STOPPED
#     await c.save()

#     sch = _get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     return {"success": True, "detail": "Campaign stopped"}


# @router.post("/campaigns/{campaign_id}/run-now")
# async def run_now(campaign_id: int, payload: RunNowPayload,
#                   user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     await c.fetch_related("assistant", "user")

#     await _ensure_progress_rows(c)

#     todo = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["pending", "retry_scheduled"]
#     ).order_by("id").limit(payload.batch_size).all()

#     if not todo:
#         return {"success": True, "detail": "No eligible leads to call right now."}

#     for prog in todo:
#         lead = await Lead.get_or_none(id=prog.lead_id)
#         if not lead:
#             prog.status = "failed"
#             prog.last_ended_reason = "error:lead-missing"
#             await prog.save()
#             continue

#         if lead.dnc:
#             prog.status = "skipped"
#             prog.last_ended_reason = "skipped:dnc"
#             await prog.save()
#             continue

#         try:
#             prog.status = "calling"
#             prog.attempt_count += 1
#             prog.last_attempt_at = datetime.utcnow()
#             await prog.save()

#             call_id = await _place_vapi_call(c.user, c.assistant, lead)
#             prog.last_call_id = call_id
#             await prog.save()

#             _get_scheduler().add_job(
#                 _process_call_outcome,
#                 DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=12)),
#                 args=[c.id, lead.id, c.user.id, call_id],
#             )
#         except Exception as e:
#             prog.status = "failed"
#             prog.last_ended_reason = f"error:{repr(e)}"
#             await prog.save()

#     return {"success": True, "detail": f"Triggered {len(todo)} lead(s) now."}


# # ---------- On-demand re-sync endpoint ----------
# @router.post("/campaigns/{campaign_id}/refresh-leads")
# async def refresh_campaign_leads(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     added = await _ensure_progress_rows(c)

#     # Kick a near-immediate tick so newly added leads don't wait for the cron
#     _get_scheduler().add_job(
#         _tick_campaign,
#         DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=1)),
#         args=[c.id],
#     )

#     return {"success": True, "detail": f"Synced {added} new lead(s)."}


# # ---------- (Optional) Export an .ics for Google Calendar ----------
# def _ics_for_campaign(c: Campaign) -> str:
#     tz = c.timezone or "UTC"
#     map_rr = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}
#     byday = ",".join(map_rr.get(d, "MO") for d in (c.days_of_week or [0, 1, 2, 3, 4]))

#     import pytz as _pytz
#     zone = _pytz.timezone(tz)
#     now_local = datetime.now(zone)
#     hh, mm = (c.daily_start or "09:00").split(":")
#     start_local = (c.start_at.astimezone(zone) if c.start_at else now_local).replace(
#         hour=int(hh), minute=int(mm), second=0, microsecond=0
#     )
#     dtstart = start_local.strftime("%Y%m%dT%H%M%S")

#     uid = f"campaign-{c.id}@yourapp"
#     lines = [
#         "BEGIN:VCALENDAR",
#         "VERSION:2.0",
#         "PRODID:-//YourApp//Campaign//EN",
#         "CALSCALE:GREGORIAN",
#         "METHOD:PUBLISH",
#         "BEGIN:VEVENT",
#         f"UID:{uid}",
#         f"SUMMARY:Call Campaign — {c.name}",
#         f"DTSTART;TZID={tz}:{dtstart}",
#         f"RRULE:FREQ=WEEKLY;BYDAY={byday}",
#         f"DESCRIPTION:Calls placed within {c.daily_start}-{c.daily_end} local time. Server handles pacing & retries.",
#         "END:VEVENT",
#         "END:VCALENDAR",
#     ]
#     return "\r\n".join(lines)


# @router.get("/campaigns/{campaign_id}/calendar.ics")
# async def campaign_calendar_ics(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     ics = _ics_for_campaign(c)
#     return StreamingResponse(
#         content=iter([ics]),
#         media_type="text/calendar",
#         headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.ics"'},
#     )






# # controllers/campaign_controller.py
# import logging
# import asyncio
# from datetime import datetime, date, time, timedelta
# from typing import Annotated, List, Optional

# import pytz
# import httpx
# from fastapi import APIRouter, HTTPException, Depends, Query
# from fastapi.responses import StreamingResponse
# from apscheduler.triggers.date import DateTrigger
# from tortoise.expressions import Q

# from controllers.call_controller import get_call_details
# from scheduler.campaign_scheduler import (
#     get_scheduler,          # single global AsyncIOScheduler
#     schedule_minutely_job,  # helper to add a */1 cron with timezone
#     nudge_once,             # helper to fire once after N seconds
# )

# from models.auth import User
# from models.file import File as FileModel
# from models.lead import Lead
# from models.call_log import CallLog
# from models.assistant import Assistant
# from models.campaign import (
#     Campaign,
#     CampaignLeadProgress,
#     CampaignStatus,
#     CampaignSelectionMode,
# )

# from helpers.token_helper import get_current_user
# from helpers.vapi_helper import get_headers
# from pydantic import BaseModel, Field

# router = APIRouter()

# # ─────────────────────────────────────────────────────────────────────────────
# # Logging
# # ─────────────────────────────────────────────────────────────────────────────
# logger = logging.getLogger("campaigns")
# # (configure logging level/handlers globally in your app startup if needed)

# # ─────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ─────────────────────────────────────────────────────────────────────────────
# class CampaignCreatePayload(BaseModel):
#     name: str = Field(..., min_length=2, max_length=255)
#     file_id: int
#     assistant_id: int

#     selection_mode: CampaignSelectionMode = CampaignSelectionMode.ALL
#     include_lead_ids: Optional[List[int]] = None
#     exclude_lead_ids: Optional[List[int]] = None

#     timezone: str = "America/Los_Angeles"
#     days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
#     daily_start: str = "09:00"
#     daily_end: str = "18:00"
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None

#     calls_per_minute: int = 10
#     parallel_calls: int = 2

#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class CampaignUpdateSchedulePayload(BaseModel):
#     timezone: Optional[str] = None
#     days_of_week: Optional[List[int]] = None
#     daily_start: Optional[str] = None
#     daily_end: Optional[str] = None
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None


# class RetryPolicyPayload(BaseModel):
#     retry_on_busy: bool = True
#     busy_retry_delay_minutes: int = 15
#     max_attempts: int = 3


# class RunNowPayload(BaseModel):
#     batch_size: int = 5


# # ─────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────────────────────────────────────
# BUSY_REASONS = {"busy", "user-busy", "target-busy", "no-answer", "call-rejected"}


# def now_utc() -> datetime:
#     """Return tz-aware current UTC time."""
#     return datetime.now(pytz.utc)


# def _parse_hhmm(s: Optional[str]) -> Optional[time]:
#     if not s:
#         return None
#     h, m = s.split(":")
#     return time(hour=int(h), minute=int(m))


# def _as_tzaware(dt: Optional[datetime], tz) -> Optional[datetime]:
#     """Ensure dt is timezone-aware in tz."""
#     if dt is None:
#         return None
#     if dt.tzinfo is None:
#         # treat naive as local to the campaign timezone
#         return tz.localize(dt)
#     return dt.astimezone(tz)


# def _within_window(c: Campaign, now: datetime) -> bool:
#     """
#     Check if the campaign is currently within its allowed window.
#     `now` should be tz-aware (UTC).
#     """
#     if now.tzinfo is None:
#         now = now.replace(tzinfo=pytz.utc)

#     tz = pytz.timezone(c.timezone or "America/Los_Angeles")
#     now_local = now.astimezone(tz)

#     start_at = _as_tzaware(c.start_at, tz)
#     end_at = _as_tzaware(c.end_at, tz)
#     if start_at and now_local < start_at:
#         return False
#     if end_at and now_local > end_at:
#         return False

#     if c.days_of_week and now_local.weekday() not in set(c.days_of_week):
#         return False

#     start_t = _parse_hhmm(c.daily_start) or time(0, 0)
#     end_t = _parse_hhmm(c.daily_end) or time(23, 59)
#     return start_t <= now_local.time() <= end_t


# async def _compute_lead_ids_for_campaign(c: Campaign) -> List[int]:
#     base = Lead.filter(file_id=c.file_id, dnc=False)

#     if c.selection_mode == CampaignSelectionMode.ONLY:
#         if not c.include_lead_ids:
#             return []
#         base = base.filter(id__in=c.include_lead_ids)
#     elif c.selection_mode == CampaignSelectionMode.SKIP:
#         if c.exclude_lead_ids:
#             base = base.exclude(id__in=c.exclude_lead_ids)

#     leads = await base.all()
#     return [l.id for l in leads]


# async def _ensure_progress_rows(campaign: Campaign) -> int:
#     lead_ids = await _compute_lead_ids_for_campaign(campaign)
#     if not lead_ids:
#         return 0

#     existing_ids = await CampaignLeadProgress.filter(
#         campaign_id=campaign.id
#     ).values_list("lead_id", flat=True)
#     existing_set = set(existing_ids)
#     to_create = [lid for lid in lead_ids if lid not in existing_set]

#     objs = [
#         CampaignLeadProgress(campaign=campaign, lead_id=lid, status="pending")
#         for lid in to_create
#     ]
#     if objs:
#         await CampaignLeadProgress.bulk_create(objs)
#         logger.info("campaign %s: queued %d new leads", campaign.id, len(objs))
#     return len(objs)


# # ─────────────────────────────────────────────────────────────────────────────
# # Shared helpers usable from other controllers
# # ─────────────────────────────────────────────────────────────────────────────
# async def trigger_campaign_refresh_for_file(file_id: int, and_tick: bool = True) -> dict:
#     """
#     Find SCHEDULED/RUNNING campaigns tied to this file and:
#       - ensure CampaignLeadProgress rows exist for all currently-eligible leads
#       - optionally schedule an immediate tick so calls start quickly
#     """
#     campaigns = await Campaign.filter(
#         file_id=file_id,
#         status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING],
#     ).all()

#     total_added = 0
#     for c in campaigns:
#         added = await _ensure_progress_rows(c)
#         total_added += added
#         if and_tick:
#             nudge_once(_tick_campaign, c.id, delay_seconds=1)
#             logger.debug("campaign %s: nudged immediate tick", c.id)

#     return {"campaigns_checked": len(campaigns), "leads_added": total_added}


# # ─────────────────────────────────────────────────────────────────────────────
# # VAPI call placement (async, non-blocking)
# # ─────────────────────────────────────────────────────────────────────────────
# async def _place_vapi_call(user: User, assistant: Assistant, lead: Lead) -> str:
#     if not assistant.vapi_assistant_id:
#         raise HTTPException(status_code=400, detail="Assistant has no VAPI ID")
#     if not assistant.vapi_phone_uuid or not assistant.attached_Number:
#         raise HTTPException(status_code=400, detail="Assistant has no attached phone number")

#     mobile_raw = (lead.mobile or "").strip()
#     if not mobile_raw:
#         raise HTTPException(status_code=400, detail="Lead has no mobile number")
#     number_e164 = mobile_raw if mobile_raw.startswith("+") else f"+1{mobile_raw}"

#     payload = {
#         "name": f"Campaign {assistant.name}",
#         "assistantId": assistant.vapi_assistant_id,
#         "customer": {
#             "numberE164CheckEnabled": True,
#             "extension": None,
#             "number": number_e164,
#         },
#         "phoneNumberId": assistant.vapi_phone_uuid,
#         "assistantOverrides": {
#             "variableValues": {
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "mobile_no": number_e164,
#                 "add_date": (lead.add_date.isoformat() if isinstance(lead.add_date, (datetime, date)) else None),
#                 "custom_field_01": (lead.other_data or {}).get("Custom_0"),
#                 "custom_field_02": (lead.other_data or {}).get("Custom_1"),
#             },
#             "maxDurationSeconds": 10000,
#             "silenceTimeoutSeconds": 120,
#             "startSpeakingPlan": {
#                 "waitSeconds": 1.0,
#                 "smartEndpointingEnabled": True,
#                 "transcriptionEndpointingPlan": {
#                     "onPunctuationSeconds": 0.5,
#                     "onNoPunctuationSeconds": 3.0,
#                     "onNumberSeconds": 1.0,
#                 },
#             },
#             "stopSpeakingPlan": {
#                 "numWords": 0,
#                 "voiceSeconds": 0.5,
#                 "backoffSeconds": 2.0,
#             },
#         },
#     }

#     headers = get_headers()
#     async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
#         resp = await client.post("https://api.vapi.ai/call", json=payload, headers=headers)

#     if resp.status_code not in (200, 201):
#         try:
#             msg = resp.json().get("message", resp.text)
#         except Exception:
#             msg = resp.text
#         logger.error("VAPI error (%s): %s", resp.status_code, msg)
#         raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {msg}")

#     data = resp.json()
#     call_id = data.get("id")
#     if not call_id:
#         logger.error("VAPI response missing call ID: %s", data)
#         raise HTTPException(status_code=400, detail="VAPI response missing call ID")

#     started_at = data.get("createdAt")
#     await CallLog.create(
#         user=user,
#         call_id=call_id,
#         call_started_at=(
#             datetime.fromisoformat(started_at.replace("Z", "+00:00")) if isinstance(started_at, str) else None
#         ),
#         customer_name=f"{(lead.first_name or '').strip()} {(lead.last_name or '').strip()}".strip() or "Unknown",
#         customer_number=number_e164,
#         lead_id=lead.id,
#     )

#     logger.info("call placed: campaign_user=%s lead_id=%s number=%s call_id=%s",
#                 user.id, lead.id, number_e164, call_id)

#     # schedule details fetch (tz-aware)
#     processing_delay = min(120 + (10000 // 600), 1800)
#     run_at = now_utc() + timedelta(seconds=processing_delay)
#     get_scheduler().add_job(
#         get_call_details,
#         DateTrigger(run_date=run_at),
#         args=[call_id, processing_delay, user.id, lead.id],
#     )

#     return call_id


# # ─────────────────────────────────────────────────────────────────────────────
# # Outcome processing
# # ─────────────────────────────────────────────────────────────────────────────
# async def _process_call_outcome(campaign_id: int, lead_id: int, user_id: int, call_id: str):
#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     prog = await CampaignLeadProgress.get_or_none(campaign_id=campaign_id, lead_id=lead_id)
#     if not prog:
#         return

#     cl = await CallLog.get_or_none(call_id=call_id)
#     if not cl:
#         # try again in 2 minutes
#         get_scheduler().add_job(
#             _process_call_outcome,
#             DateTrigger(run_date=now_utc() + timedelta(minutes=2)),
#             args=[campaign_id, lead_id, user_id, call_id],
#         )
#         return

#     ended_reason = (cl.call_ended_reason or "").lower().strip()
#     prog.last_ended_reason = ended_reason
#     prog.status = "completed"

#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return

#     if ended_reason in BUSY_REASONS and c.retry_on_busy and prog.attempt_count < c.max_attempts:
#         prog.status = "retry_scheduled"
#         prog.next_attempt_at = datetime.utcnow() + timedelta(minutes=c.busy_retry_delay_minutes)  # DB likely naive
#         logger.info("campaign %s lead %s: scheduled retry in %s min",
#                     c.id, lead_id, c.busy_retry_delay_minutes)
#     elif ended_reason in {"failed", "error"}:
#         prog.status = "failed"

#     await prog.save()


# # ─────────────────────────────────────────────────────────────────────────────
# # Campaign ticking (cron)
# # ─────────────────────────────────────────────────────────────────────────────
# async def _tick_campaign(campaign_id: int):
#     now_aw = now_utc()      # tz-aware
#     now_db = datetime.utcnow()  # naive for DB comparisons

#     c = await Campaign.get_or_none(id=campaign_id)
#     if not c:
#         return
#     await c.fetch_related("assistant", "user")

#     if c.status not in {CampaignStatus.SCHEDULED, CampaignStatus.RUNNING}:
#         return

#     # auto-absorb new leads
#     try:
#         added = await _ensure_progress_rows(c)
#         if added:
#             logger.info("campaign %s: auto-synced %d new lead(s)", c.id, added)
#     except Exception as e:
#         logger.exception("campaign %s: sync error: %r", c.id, e)

#     if not _within_window(c, now_aw):
#         logger.debug("campaign %s: outside window at %s", c.id, now_aw.isoformat())
#         return

#     batch = max(1, min(c.calls_per_minute, 50))
#     parallel = max(1, min(c.parallel_calls, 10))

#     q = CampaignLeadProgress.filter(
#         campaign_id=c.id,
#         status__in=["pending", "retry_scheduled"],
#     ).order_by("id")
#     q = q.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now_db))

#     todo: List[CampaignLeadProgress] = await q.limit(batch).all()
#     if not todo:
#         remaining = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["pending", "retry_scheduled", "calling"]
#         ).count()
#         if remaining == 0:
#             c.status = CampaignStatus.COMPLETED
#             await c.save()
#             logger.info("campaign %s: completed (no remaining leads)", c.id)
#         return

#     sem = asyncio.Semaphore(parallel)

#     async def _one(prog: CampaignLeadProgress):
#         async with sem:
#             lead = await Lead.get_or_none(id=prog.lead_id)
#             if not lead:
#                 prog.status = "failed"
#                 prog.last_ended_reason = "error:lead-missing"
#                 await prog.save()
#                 logger.warning("campaign %s: lead %s missing; marked failed", c.id, prog.lead_id)
#                 return

#             if lead.dnc:
#                 prog.status = "skipped"
#                 prog.last_ended_reason = "skipped:dnc"
#                 await prog.save()
#                 logger.info("campaign %s: lead %s skipped (DNC)", c.id, prog.lead_id)
#                 return

#             try:
#                 prog.status = "calling"
#                 prog.attempt_count += 1
#                 prog.last_attempt_at = datetime.utcnow()  # DB naive
#                 await prog.save()

#                 call_id = await _place_vapi_call(c.user, c.assistant, lead)
#                 prog.last_call_id = call_id
#                 await prog.save()

#                 get_scheduler().add_job(
#                     _process_call_outcome,
#                     DateTrigger(run_date=now_utc() + timedelta(minutes=12)),
#                     args=[c.id, lead.id, c.user.id, call_id],
#                 )
#                 logger.debug("campaign %s: scheduled outcome processing for lead %s (call %s)",
#                              c.id, lead.id, call_id)

#             except HTTPException as e:
#                 detail = str(e.detail).lower()
#                 prog.status = "skipped" if ("no mobile" in detail or "mobile number" in detail) else "failed"
#                 prog.last_ended_reason = f"error:{e.detail}"
#                 await prog.save()
#                 logger.warning("campaign %s: lead %s error => %s", c.id, lead.id, detail)
#             except Exception as e:
#                 prog.status = "failed"
#                 prog.last_ended_reason = f"error:{repr(e)}"
#                 await prog.save()
#                 logger.exception("campaign %s: lead %s unexpected error", c.id, lead.id)

#     await asyncio.gather(*[_one(p) for p in todo])

#     c.last_tick_at = datetime.utcnow()  # DB naive
#     c.status = CampaignStatus.RUNNING
#     await c.save()
#     logger.info("campaign %s: tick complete - placed %d call(s)", c.id, len(todo))


# def _schedule_campaign_job(campaign_id: int, timezone: str):
#     job_id = f"campaign:{campaign_id}"
#     # Replaces existing minute job with a fresh one in the correct timezone
#     schedule_minutely_job(job_id, timezone, _tick_campaign, campaign_id)
#     logger.info("campaign %s: scheduled */1 min ticker (tz=%s)", campaign_id, timezone or "UTC")


# # ─────────────────────────────────────────────────────────────────────────────
# # Routes
# # ─────────────────────────────────────────────────────────────────────────────
# @router.post("/campaigns")
# async def create_campaign(payload: CampaignCreatePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     file = await FileModel.get_or_none(id=payload.file_id, user_id=user.id)
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found for this user")

#     assistant = await Assistant.get_or_none(id=payload.assistant_id, user_id=user.id)
#     if not assistant:
#         raise HTTPException(status_code=404, detail="Assistant not found")

#     if not assistant.vapi_assistant_id or not assistant.vapi_phone_uuid:
#         raise HTTPException(status_code=400, detail="Assistant must have VAPI ID and attached number")

#     c = await Campaign.create(
#         user=user,
#         name=payload.name,
#         file=file,
#         assistant=assistant,
#         selection_mode=payload.selection_mode,
#         include_lead_ids=payload.include_lead_ids,
#         exclude_lead_ids=payload.exclude_lead_ids,
#         timezone=payload.timezone,
#         days_of_week=payload.days_of_week,
#         daily_start=payload.daily_start,
#         daily_end=payload.daily_end,
#         start_at=payload.start_at,
#         end_at=payload.end_at,
#         calls_per_minute=payload.calls_per_minute,
#         parallel_calls=payload.parallel_calls,
#         retry_on_busy=payload.retry_on_busy,
#         busy_retry_delay_minutes=payload.busy_retry_delay_minutes,
#         max_attempts=payload.max_attempts,
#         status=CampaignStatus.SCHEDULED,
#     )

#     added = await _ensure_progress_rows(c)
#     _schedule_campaign_job(c.id, c.timezone)

#     logger.info("campaign %s created by user %s; queued=%d", c.id, user.id, added)

#     return {
#         "success": True,
#         "campaign_id": c.id,
#         "detail": f"Campaign created. {added} lead(s) queued."
#     }


# @router.get("/campaigns")
# async def list_campaigns(user: Annotated[User, Depends(get_current_user)]):
#     cs = await Campaign.filter(user_id=user.id).order_by("-created_at").all()
#     out = []
#     for c in cs:
#         total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#         done = await CampaignLeadProgress.filter(
#             campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#         ).count()
#         out.append({
#             "id": c.id,
#             "name": c.name,
#             "status": c.status,
#             "file_id": c.file_id,
#             "assistant_id": c.assistant_id,
#             "timezone": c.timezone,
#             "window": {"days": c.days_of_week, "start": c.daily_start, "end": c.daily_end},
#             "start_at": c.start_at,
#             "end_at": c.end_at,
#             "calls_per_minute": c.calls_per_minute,
#             "parallel_calls": c.parallel_calls,
#             "retry_on_busy": c.retry_on_busy,
#             "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#             "max_attempts": c.max_attempts,
#             "counts": {"total": total, "completed_or_failed": done},
#             "created_at": c.created_at,
#         })
#     return out


# @router.get("/campaigns/{campaign_id}")
# async def get_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#     pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
#     retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
#     calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
#     done = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#     ).count()

#     return {
#         "id": c.id,
#         "name": c.name,
#         "status": c.status,
#         "file_id": c.file_id,
#         "assistant_id": c.assistant_id,
#         "selection_mode": c.selection_mode,
#         "include_lead_ids": c.include_lead_ids,
#         "exclude_lead_ids": c.exclude_lead_ids,
#         "timezone": c.timezone,
#         "days_of_week": c.days_of_week,
#         "daily_start": c.daily_start,
#         "daily_end": c.daily_end,
#         "start_at": c.start_at,
#         "end_at": c.end_at,
#         "calls_per_minute": c.calls_per_minute,
#         "parallel_calls": c.parallel_calls,
#         "retry_on_busy": c.retry_on_busy,
#         "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
#         "max_attempts": c.max_attempts,
#         "totals": {
#             "total": total,
#             "pending": pending,
#             "retry": retrying,
#             "calling": calling,
#             "done": done
#         }
#     }


# @router.get("/campaigns/{campaign_id}/stats")
# async def campaign_stats(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     now_aw = now_utc()
#     tz = pytz.timezone(c.timezone or "UTC")

#     # segment counts
#     total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
#     pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
#     retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
#     calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
#     done = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["completed", "failed", "skipped"]
#     ).count()

#     # progress percent
#     pct = int(round((done / total) * 100)) if total > 0 else 0

#     # next tick (from APScheduler job, if any)
#     sch = get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     next_tick_at = job.next_run_time if job else None

#     # eligible backlog now (DB naive time for comparisons)
#     eligible_now = await CampaignLeadProgress.filter(
#         campaign_id=c.id,
#         status__in=["pending", "retry_scheduled"]
#     ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=datetime.utcnow())).count()

#     active_now = _within_window(c, now_aw) and c.status in {
#         CampaignStatus.SCHEDULED, CampaignStatus.RUNNING
#     }

#     return {
#         "id": c.id,
#         "name": c.name,
#         "status": c.status,
#         "timezone": c.timezone,
#         "window": {
#             "days_of_week": c.days_of_week,
#             "daily_start": c.daily_start,
#             "daily_end": c.daily_end,
#             "start_at": c.start_at,
#             "end_at": c.end_at,
#         },
#         "now": {
#             "server_utc": now_aw.isoformat(),
#             "local": now_aw.astimezone(tz).isoformat(),
#         },
#         "active_now": active_now,
#         "last_tick_at": c.last_tick_at,
#         "next_tick_at": next_tick_at.isoformat() if next_tick_at else None,
#         "pacing": {
#             "calls_per_minute": c.calls_per_minute,
#             "parallel_calls": c.parallel_calls,
#         },
#         "totals": {
#             "total": total,
#             "pending": pending,
#             "retry": retrying,
#             "calling": calling,
#             "done": done,
#         },
#         "percent_complete": pct,
#         "counts": {  # convenience mirror for your cards
#             "total": total,
#             "done": done,
#         },
#         "eligible_now": eligible_now,
#     }


# @router.delete("/campaigns/{campaign_id}")
# async def delete_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     sch = get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     await CampaignLeadProgress.filter(campaign_id=campaign_id).delete()
#     await c.delete()
#     logger.info("campaign %s: deleted", campaign_id)
#     return {"success": True, "detail": "Campaign deleted"}


# @router.post("/campaigns/{campaign_id}/schedule")
# async def update_schedule(campaign_id: int,
#                           payload: CampaignUpdateSchedulePayload,
#                           user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     if payload.timezone is not None:
#         c.timezone = payload.timezone
#     if payload.days_of_week is not None:
#         c.days_of_week = payload.days_of_week
#     if payload.daily_start is not None:
#         c.daily_start = payload.daily_start
#     if payload.daily_end is not None:
#         c.daily_end = payload.daily_end
#     if payload.start_at is not None:
#         c.start_at = payload.start_at
#     if payload.end_at is not None:
#         c.end_at = payload.end_at

#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     added = await _ensure_progress_rows(c)
#     logger.info("campaign %s: schedule updated; queued_new=%d", c.id, added)
#     return {"success": True, "detail": "Schedule updated"}


# @router.post("/campaigns/{campaign_id}/retry-policy")
# async def update_retry(campaign_id: int,
#                        payload: RetryPolicyPayload,
#                        user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     c.retry_on_busy = payload.retry_on_busy
#     c.busy_retry_delay_minutes = payload.busy_retry_delay_minutes
#     c.max_attempts = payload.max_attempts
#     await c.save()
#     logger.info("campaign %s: retry policy updated", c.id)
#     return {"success": True, "detail": "Retry policy updated"}


# @router.post("/campaigns/{campaign_id}/pause")
# async def pause_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.PAUSED
#     await c.save()
#     logger.info("campaign %s: paused", c.id)
#     return {"success": True, "detail": "Campaign paused"}


# @router.post("/campaigns/{campaign_id}/resume")
# async def resume_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.SCHEDULED
#     await c.save()
#     _schedule_campaign_job(c.id, c.timezone)
#     added = await _ensure_progress_rows(c)
#     logger.info("campaign %s: resumed; queued_new=%d", c.id, added)
#     return {"success": True, "detail": "Campaign resumed"}


# @router.post("/campaigns/{campaign_id}/stop")
# async def stop_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     c.status = CampaignStatus.STOPPED
#     await c.save()

#     sch = get_scheduler()
#     job = sch.get_job(f"campaign:{campaign_id}")
#     if job:
#         job.remove()

#     logger.info("campaign %s: stopped", c.id)
#     return {"success": True, "detail": "Campaign stopped"}


# @router.post("/campaigns/{campaign_id}/run-now")
# async def run_now(campaign_id: int, payload: RunNowPayload,
#                   user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     await c.fetch_related("assistant", "user")

#     await _ensure_progress_rows(c)

#     todo = await CampaignLeadProgress.filter(
#         campaign_id=c.id, status__in=["pending", "retry_scheduled"]
#     ).order_by("id").limit(payload.batch_size).all()

#     if not todo:
#         return {"success": True, "detail": "No eligible leads to call right now."}

#     placed = 0
#     for prog in todo:
#         lead = await Lead.get_or_none(id=prog.lead_id)
#         if not lead:
#             prog.status = "failed"
#             prog.last_ended_reason = "error:lead-missing"
#             await prog.save()
#             continue

#         if lead.dnc:
#             prog.status = "skipped"
#             prog.last_ended_reason = "skipped:dnc"
#             await prog.save()
#             continue

#         try:
#             prog.status = "calling"
#             prog.attempt_count += 1
#             prog.last_attempt_at = datetime.utcnow()
#             await prog.save()

#             call_id = await _place_vapi_call(c.user, c.assistant, lead)
#             prog.last_call_id = call_id
#             await prog.save()
#             placed += 1

#             get_scheduler().add_job(
#                 _process_call_outcome,
#                 DateTrigger(run_date=now_utc() + timedelta(minutes=12)),
#                 args=[c.id, lead.id, c.user.id, call_id],
#             )
#         except Exception as e:
#             prog.status = "failed"
#             prog.last_ended_reason = f"error:{repr(e)}"
#             await prog.save()

#     logger.info("campaign %s: run-now placed %d call(s)", c.id, placed)
#     return {"success": True, "detail": f"Triggered {placed} lead(s) now."}


# @router.post("/campaigns/{campaign_id}/refresh-leads")
# async def refresh_campaign_leads(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")

#     added = await _ensure_progress_rows(c)

#     # kick near-immediate tick
#     nudge_once(_tick_campaign, c.id, delay_seconds=1)
#     logger.info("campaign %s: refresh-leads queued_new=%d and nudged", c.id, added)

#     return {"success": True, "detail": f"Synced {added} new lead(s)."}


# # ─────────────────────────────────────────────────────────────────────────────
# # iCalendar export
# # ─────────────────────────────────────────────────────────────────────────────
# def _ics_for_campaign(c: Campaign) -> str:
#     tz = c.timezone or "UTC"
#     map_rr = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}
#     byday = ",".join(map_rr.get(d, "MO") for d in (c.days_of_week or [0, 1, 2, 3, 4]))

#     import pytz as _pytz
#     zone = _pytz.timezone(tz)
#     now_local = datetime.now(zone)
#     hh, mm = (c.daily_start or "09:00").split(":")
#     start_local = (c.start_at.astimezone(zone) if c.start_at else now_local).replace(
#         hour=int(hh), minute=int(mm), second=0, microsecond=0
#     )
#     dtstart = start_local.strftime("%Y%m%dT%H%M%S")

#     uid = f"campaign-{c.id}@yourapp"
#     lines = [
#         "BEGIN:VCALENDAR",
#         "VERSION:2.0",
#         "PRODID:-//YourApp//Campaign//EN",
#         "CALSCALE:GREGORIAN",
#         "METHOD:PUBLISH",
#         "BEGIN:VEVENT",
#         f"UID:{uid}",
#         f"SUMMARY:Call Campaign — {c.name}",
#         f"DTSTART;TZID={tz}:{dtstart}",
#         f"RRULE:FREQ=WEEKLY;BYDAY={byday}",
#         f"DESCRIPTION:Calls placed within {c.daily_start}-{c.daily_end} local time. Server handles pacing & retries.",
#         "END:VEVENT",
#         "END:VCALENDAR",
#     ]
#     return "\r\n".join(lines)


# @router.get("/campaigns/{campaign_id}/calendar.ics")
# async def campaign_calendar_ics(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
#     c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
#     if not c:
#         raise HTTPException(status_code=404, detail="Campaign not found")
#     ics = _ics_for_campaign(c)
#     return StreamingResponse(
#         content=iter([ics]),
#         media_type="text/calendar",
#         headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.ics"'},
#     )


# # ─────────────────────────────────────────────────────────────────────────────
# # Debug endpoints
# # ─────────────────────────────────────────────────────────────────────────────
# @router.get("/debug/scheduler")
# async def scheduler_jobs():
#     """
#     Inspect jobs currently registered in APScheduler.
#     """
#     jobs = get_scheduler().get_jobs()
#     return [
#         {
#             "id": j.id,
#             "name": getattr(j, "name", None),
#             "next_run_time": (j.next_run_time.isoformat() if j.next_run_time else None),
#         }
#         for j in jobs
#     ]


# @router.post("/debug/tick/{campaign_id}")
# async def debug_tick(campaign_id: int):
#     """
#     Force a one-off tick for a campaign (fires in ~1s).
#     """
#     nudge_once(_tick_campaign, campaign_id, delay_seconds=1)
#     return {"success": True, "detail": f"Tick scheduled for campaign {campaign_id} in ~1s"}





















# controllers/campaign_controller.py
import logging
import asyncio
from datetime import datetime, date, time, timedelta
from typing import Annotated, List, Optional

import pytz
import httpx
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from apscheduler.triggers.date import DateTrigger
from tortoise.expressions import Q

from controllers.call_controller import get_call_details
from scheduler.campaign_scheduler import (
    get_scheduler,          # single global AsyncIOScheduler
    schedule_minutely_job,  # helper to add a */1 cron with timezone
    nudge_once,             # helper to fire once after N seconds
)

from models.auth import User
from models.file import File as FileModel
from models.lead import Lead
from models.call_log import CallLog
from models.assistant import Assistant
from models.campaign import (
    Campaign,
    CampaignLeadProgress,
    CampaignStatus,
    CampaignSelectionMode,
)

from helpers.token_helper import get_current_user
from helpers.vapi_helper import get_headers
from pydantic import BaseModel, Field

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("campaigns")
# (configure logging level/handlers globally in your app startup if needed)

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class CampaignCreatePayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    file_id: int
    assistant_id: int

    selection_mode: CampaignSelectionMode = CampaignSelectionMode.ALL
    include_lead_ids: Optional[List[int]] = None
    exclude_lead_ids: Optional[List[int]] = None

    timezone: str = "America/Los_Angeles"
    days_of_week: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    daily_start: str = "09:00"
    daily_end: str = "18:00"
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None

    calls_per_minute: int = 10
    parallel_calls: int = 2

    retry_on_busy: bool = True
    busy_retry_delay_minutes: int = 15
    max_attempts: int = 3


class CampaignUpdateSchedulePayload(BaseModel):
    timezone: Optional[str] = None
    days_of_week: Optional[List[int]] = None
    daily_start: Optional[str] = None
    daily_end: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None


class RetryPolicyPayload(BaseModel):
    retry_on_busy: bool = True
    busy_retry_delay_minutes: int = 15
    max_attempts: int = 3


class RunNowPayload(BaseModel):
    batch_size: int = 5


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
BUSY_REASONS = {"busy", "user-busy", "target-busy", "no-answer", "call-rejected"}


def now_utc() -> datetime:
    """Return tz-aware current UTC time."""
    return datetime.now(pytz.utc)


def _parse_hhmm(s: Optional[str]) -> Optional[time]:
    if not s:
        return None
    h, m = s.split(":")
    return time(hour=int(h), minute=int(m))


def _as_tzaware(dt: Optional[datetime], tz) -> Optional[datetime]:
    """Ensure dt is timezone-aware in tz."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # treat naive as local to the campaign timezone
        return tz.localize(dt)
    return dt.astimezone(tz)


def _within_window(c: Campaign, now: datetime) -> bool:
    """
    Check if the campaign is currently within its allowed window.
    `now` should be tz-aware (UTC).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    tz = pytz.timezone(c.timezone or "America/Los_Angeles")
    now_local = now.astimezone(tz)

    start_at = _as_tzaware(c.start_at, tz)
    end_at = _as_tzaware(c.end_at, tz)
    if start_at and now_local < start_at:
        return False
    if end_at and now_local > end_at:
        return False

    if c.days_of_week and now_local.weekday() not in set(c.days_of_week):
        return False

    start_t = _parse_hhmm(c.daily_start) or time(0, 0)
    end_t = _parse_hhmm(c.daily_end) or time(23, 59)
    return start_t <= now_local.time() <= end_t


async def _compute_lead_ids_for_campaign(c: Campaign) -> List[int]:
    base = Lead.filter(file_id=c.file_id, dnc=False)

    if c.selection_mode == CampaignSelectionMode.ONLY:
        if not c.include_lead_ids:
            return []
        base = base.filter(id__in=c.include_lead_ids)
    elif c.selection_mode == CampaignSelectionMode.SKIP:
        if c.exclude_lead_ids:
            base = base.exclude(id__in=c.exclude_lead_ids)

    leads = await base.all()
    return [l.id for l in leads]


async def _ensure_progress_rows(campaign: Campaign) -> int:
    lead_ids = await _compute_lead_ids_for_campaign(campaign)
    if not lead_ids:
        return 0

    existing_ids = await CampaignLeadProgress.filter(
        campaign_id=campaign.id
    ).values_list("lead_id", flat=True)
    existing_set = set(existing_ids)
    to_create = [lid for lid in lead_ids if lid not in existing_set]

    objs = [
        CampaignLeadProgress(campaign=campaign, lead_id=lid, status="pending")
        for lid in to_create
    ]
    if objs:
        await CampaignLeadProgress.bulk_create(objs)
        logger.info("campaign %s: queued %d new leads", campaign.id, len(objs))
    return len(objs)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers usable from other controllers
# ─────────────────────────────────────────────────────────────────────────────
async def trigger_campaign_refresh_for_file(file_id: int, and_tick: bool = True) -> dict:
    """
    Find SCHEDULED/RUNNING campaigns tied to this file and:
      - ensure CampaignLeadProgress rows exist for all currently-eligible leads
      - optionally schedule an immediate tick so calls start quickly
    """
    campaigns = await Campaign.filter(
        file_id=file_id,
        status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING],
    ).all()

    total_added = 0
    for c in campaigns:
        added = await _ensure_progress_rows(c)
        total_added += added
        if and_tick:
            nudge_once(_tick_campaign, c.id, delay_seconds=1)
            logger.debug("campaign %s: nudged immediate tick", c.id)

    return {"campaigns_checked": len(campaigns), "leads_added": total_added}


# ─────────────────────────────────────────────────────────────────────────────
# VAPI call placement (async, non-blocking)
# ─────────────────────────────────────────────────────────────────────────────
async def _place_vapi_call(user: User, assistant: Assistant, lead: Lead) -> str:
    if not assistant.vapi_assistant_id:
        raise HTTPException(status_code=400, detail="Assistant has no VAPI ID")
    if not assistant.vapi_phone_uuid or not assistant.attached_Number:
        raise HTTPException(status_code=400, detail="Assistant has no attached phone number")

    mobile_raw = (lead.mobile or "").strip()
    if not mobile_raw:
        raise HTTPException(status_code=400, detail="Lead has no mobile number")
    number_e164 = mobile_raw if mobile_raw.startswith("+") else f"+1{mobile_raw}"

    payload = {
        "name": f"Campaign {assistant.name}",
        "assistantId": assistant.vapi_assistant_id,
        "customer": {
            "numberE164CheckEnabled": True,
            "extension": None,
            "number": number_e164,
        },
        "phoneNumberId": assistant.vapi_phone_uuid,
        "assistantOverrides": {
            "variableValues": {
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "mobile_no": number_e164,
                "add_date": (lead.add_date.isoformat() if isinstance(lead.add_date, (datetime, date)) else None),
                "custom_field_01": (lead.other_data or {}).get("Custom_0"),
                "custom_field_02": (lead.other_data or {}).get("Custom_1"),
            },
            "maxDurationSeconds": 10000,
            "silenceTimeoutSeconds": 120,
            "startSpeakingPlan": {
                "waitSeconds": 1.0,
                "smartEndpointingEnabled": True,
                "transcriptionEndpointingPlan": {
                    "onPunctuationSeconds": 0.5,
                    "onNoPunctuationSeconds": 3.0,
                    "onNumberSeconds": 1.0,
                },
            },
            "stopSpeakingPlan": {
                "numWords": 0,
                "voiceSeconds": 0.5,
                "backoffSeconds": 2.0,
            },
        },
    }

    headers = get_headers()
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        resp = await client.post("https://api.vapi.ai/call", json=payload, headers=headers)

    if resp.status_code not in (200, 201):
        try:
            msg = resp.json().get("message", resp.text)
        except Exception:
            msg = resp.text
        logger.error("VAPI error (%s): %s", resp.status_code, msg)
        raise HTTPException(status_code=resp.status_code, detail=f"VAPI error: {msg}")

    data = resp.json()
    call_id = data.get("id")
    if not call_id:
        logger.error("VAPI response missing call ID: %s", data)
        raise HTTPException(status_code=400, detail="VAPI response missing call ID")

    started_at = data.get("createdAt")
    await CallLog.create(
        user=user,
        call_id=call_id,
        call_started_at=(
            datetime.fromisoformat(started_at.replace("Z", "+00:00")) if isinstance(started_at, str) else None
        ),
        customer_name=f"{(lead.first_name or '').strip()} {(lead.last_name or '').strip()}".strip() or "Unknown",
        customer_number=number_e164,
        lead_id=lead.id,
    )

    logger.info("call placed: campaign_user=%s lead_id=%s number=%s call_id=%s",
                user.id, lead.id, number_e164, call_id)

    # schedule details fetch (tz-aware)
    processing_delay = min(120 + (10000 // 600), 1800)
    run_at = now_utc() + timedelta(seconds=processing_delay)
    get_scheduler().add_job(
        get_call_details,
        DateTrigger(run_date=run_at),
        args=[call_id, processing_delay, user.id, lead.id],
    )

    return call_id


# ─────────────────────────────────────────────────────────────────────────────
# Outcome processing
# ─────────────────────────────────────────────────────────────────────────────
async def _process_call_outcome(campaign_id: int, lead_id: int, user_id: int, call_id: str):
    c = await Campaign.get_or_none(id=campaign_id)
    if not c:
        return
    await c.fetch_related("assistant", "user")

    prog = await CampaignLeadProgress.get_or_none(campaign_id=campaign_id, lead_id=lead_id)
    if not prog:
        return

    cl = await CallLog.get_or_none(call_id=call_id)
    if not cl:
        # try again in 2 minutes
        get_scheduler().add_job(
            _process_call_outcome,
            DateTrigger(run_date=now_utc() + timedelta(minutes=2)),
            args=[campaign_id, lead_id, user_id, call_id],
        )
        return

    ended_reason = (cl.call_ended_reason or "").lower().strip()
    prog.last_ended_reason = ended_reason
    prog.status = "completed"

    c = await Campaign.get_or_none(id=campaign_id)
    if not c:
        return

    if ended_reason in BUSY_REASONS and c.retry_on_busy and prog.attempt_count < c.max_attempts:
        prog.status = "retry_scheduled"
        prog.next_attempt_at = datetime.utcnow() + timedelta(minutes=c.busy_retry_delay_minutes)  # DB likely naive
        logger.info("campaign %s lead %s: scheduled retry in %s min",
                    c.id, lead_id, c.busy_retry_delay_minutes)
    elif ended_reason in {"failed", "error"}:
        prog.status = "failed"

    await prog.save()


# ─────────────────────────────────────────────────────────────────────────────
# Campaign ticking (cron)
# ─────────────────────────────────────────────────────────────────────────────
async def _tick_campaign(campaign_id: int):
    now_aw = now_utc()      # tz-aware
    now_db = datetime.utcnow()  # naive for DB comparisons

    c = await Campaign.get_or_none(id=campaign_id)
    if not c:
        return
    await c.fetch_related("assistant", "user")

    if c.status not in {CampaignStatus.SCHEDULED, CampaignStatus.RUNNING}:
        return

    # auto-absorb new leads
    try:
        added = await _ensure_progress_rows(c)
        if added:
            logger.info("campaign %s: auto-synced %d new lead(s)", c.id, added)
    except Exception as e:
        logger.exception("campaign %s: sync error: %r", c.id, e)

    if not _within_window(c, now_aw):
        logger.debug("campaign %s: outside window at %s", c.id, now_aw.isoformat())
        return

    batch = max(1, min(c.calls_per_minute, 50))
    parallel = max(1, min(c.parallel_calls, 10))

    q = CampaignLeadProgress.filter(
        campaign_id=c.id,
        status__in=["pending", "retry_scheduled"],
    ).order_by("id")
    q = q.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now_db))

    todo: List[CampaignLeadProgress] = await q.limit(batch).all()
    if not todo:
        remaining = await CampaignLeadProgress.filter(
            campaign_id=c.id, status__in=["pending", "retry_scheduled", "calling"]
        ).count()
        if remaining == 0:
            c.status = CampaignStatus.COMPLETED
            await c.save()
            logger.info("campaign %s: completed (no remaining leads)", c.id)
        return

    sem = asyncio.Semaphore(parallel)

    async def _one(prog: CampaignLeadProgress):
        async with sem:
            lead = await Lead.get_or_none(id=prog.lead_id)
            if not lead:
                prog.status = "failed"
                prog.last_ended_reason = "error:lead-missing"
                await prog.save()
                logger.warning("campaign %s: lead %s missing; marked failed", c.id, prog.lead_id)
                return

            if lead.dnc:
                prog.status = "skipped"
                prog.last_ended_reason = "skipped:dnc"
                await prog.save()
                logger.info("campaign %s: lead %s skipped (DNC)", c.id, prog.lead_id)
                return

            try:
                prog.status = "calling"
                prog.attempt_count += 1
                prog.last_attempt_at = datetime.utcnow()  # DB naive
                await prog.save()

                call_id = await _place_vapi_call(c.user, c.assistant, lead)
                prog.last_call_id = call_id
                await prog.save()

                get_scheduler().add_job(
                    _process_call_outcome,
                    DateTrigger(run_date=now_utc() + timedelta(minutes=12)),
                    args=[c.id, lead.id, c.user.id, call_id],
                )
                logger.debug("campaign %s: scheduled outcome processing for lead %s (call %s)",
                             c.id, lead.id, call_id)

            except HTTPException as e:
                detail = str(e.detail).lower()
                prog.status = "skipped" if ("no mobile" in detail or "mobile number" in detail) else "failed"
                prog.last_ended_reason = f"error:{e.detail}"
                await prog.save()
                logger.warning("campaign %s: lead %s error => %s", c.id, lead.id, detail)
            except Exception as e:
                prog.status = "failed"
                prog.last_ended_reason = f"error:{repr(e)}"
                await prog.save()
                logger.exception("campaign %s: lead %s unexpected error", c.id, lead.id)

    await asyncio.gather(*[_one(p) for p in todo])

    c.last_tick_at = datetime.utcnow()  # DB naive
    c.status = CampaignStatus.RUNNING
    await c.save()
    logger.info("campaign %s: tick complete - placed %d call(s)", c.id, len(todo))


def _schedule_campaign_job(campaign_id: int, timezone: str):
    job_id = f"campaign:{campaign_id}"
    # Replaces existing minute job with a fresh one in the correct timezone
    schedule_minutely_job(job_id, timezone, _tick_campaign, campaign_id)
    logger.info("campaign %s: scheduled */1 min ticker (tz=%s)", campaign_id, timezone or "UTC")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/campaigns")
async def create_campaign(payload: CampaignCreatePayload,
                          user: Annotated[User, Depends(get_current_user)]):
    file = await FileModel.get_or_none(id=payload.file_id, user_id=user.id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found for this user")

    assistant = await Assistant.get_or_none(id=payload.assistant_id, user_id=user.id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    if not assistant.vapi_assistant_id or not assistant.vapi_phone_uuid:
        raise HTTPException(status_code=400, detail="Assistant must have VAPI ID and attached number")

    c = await Campaign.create(
        user=user,
        name=payload.name,
        file=file,
        assistant=assistant,
        selection_mode=payload.selection_mode,
        include_lead_ids=payload.include_lead_ids,
        exclude_lead_ids=payload.exclude_lead_ids,
        timezone=payload.timezone,
        days_of_week=payload.days_of_week,
        daily_start=payload.daily_start,
        daily_end=payload.daily_end,
        start_at=payload.start_at,
        end_at=payload.end_at,
        calls_per_minute=payload.calls_per_minute,
        parallel_calls=payload.parallel_calls,
        retry_on_busy=payload.retry_on_busy,
        busy_retry_delay_minutes=payload.busy_retry_delay_minutes,
        max_attempts=payload.max_attempts,
        status=CampaignStatus.SCHEDULED,
    )

    added = await _ensure_progress_rows(c)
    _schedule_campaign_job(c.id, c.timezone)

    logger.info("campaign %s created by user %s; queued=%d", c.id, user.id, added)

    return {
        "success": True,
        "campaign_id": c.id,
        "detail": f"Campaign created. {added} lead(s) queued."
    }


@router.get("/campaigns")
async def list_campaigns(user: Annotated[User, Depends(get_current_user)]):
    cs = await Campaign.filter(user_id=user.id).order_by("-created_at").all()
    out = []
    for c in cs:
        total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
        done = await CampaignLeadProgress.filter(
            campaign_id=c.id, status__in=["completed", "failed", "skipped"]
        ).count()
        out.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "file_id": c.file_id,
            "assistant_id": c.assistant_id,
            "timezone": c.timezone,
            "window": {"days": c.days_of_week, "start": c.daily_start, "end": c.daily_end},
            "start_at": c.start_at,
            "end_at": c.end_at,
            "calls_per_minute": c.calls_per_minute,
            "parallel_calls": c.parallel_calls,
            "retry_on_busy": c.retry_on_busy,
            "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
            "max_attempts": c.max_attempts,
            "counts": {"total": total, "completed_or_failed": done},
            "created_at": c.created_at,
        })
    return out


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
    pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
    retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
    calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
    done = await CampaignLeadProgress.filter(
        campaign_id=c.id, status__in=["completed", "failed", "skipped"]
    ).count()

    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "file_id": c.file_id,
        "assistant_id": c.assistant_id,
        "selection_mode": c.selection_mode,
        "include_lead_ids": c.include_lead_ids,
        "exclude_lead_ids": c.exclude_lead_ids,
        "timezone": c.timezone,
        "days_of_week": c.days_of_week,
        "daily_start": c.daily_start,
        "daily_end": c.daily_end,
        "start_at": c.start_at,
        "end_at": c.end_at,
        "calls_per_minute": c.calls_per_minute,
        "parallel_calls": c.parallel_calls,
        "retry_on_busy": c.retry_on_busy,
        "busy_retry_delay_minutes": c.busy_retry_delay_minutes,
        "max_attempts": c.max_attempts,
        "totals": {
            "total": total,
            "pending": pending,
            "retry": retrying,
            "calling": calling,
            "done": done
        }
    }


@router.get("/campaigns/{campaign_id}/stats")
async def campaign_stats(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    now_aw = now_utc()
    tz = pytz.timezone(c.timezone or "UTC")

    # segment counts
    total = await CampaignLeadProgress.filter(campaign_id=c.id).count()
    pending = await CampaignLeadProgress.filter(campaign_id=c.id, status="pending").count()
    retrying = await CampaignLeadProgress.filter(campaign_id=c.id, status="retry_scheduled").count()
    calling = await CampaignLeadProgress.filter(campaign_id=c.id, status="calling").count()
    done = await CampaignLeadProgress.filter(
        campaign_id=c.id, status__in=["completed", "failed", "skipped"]
    ).count()

    # progress percent
    pct = int(round((done / total) * 100)) if total > 0 else 0

    # next tick (from APScheduler job, if any)
    sch = get_scheduler()
    job = sch.get_job(f"campaign:{campaign_id}")
    next_tick_at = job.next_run_time if job else None

    # eligible backlog now (DB naive time for comparisons)
    eligible_now = await CampaignLeadProgress.filter(
        campaign_id=c.id,
        status__in=["pending", "retry_scheduled"]
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=datetime.utcnow())).count()

    active_now = _within_window(c, now_aw) and c.status in {
        CampaignStatus.SCHEDULED, CampaignStatus.RUNNING
    }

    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "timezone": c.timezone,
        "window": {
            "days_of_week": c.days_of_week,
            "daily_start": c.daily_start,
            "daily_end": c.daily_end,
            "start_at": c.start_at,
            "end_at": c.end_at,
        },
        "now": {
            "server_utc": now_aw.isoformat(),
            "local": now_aw.astimezone(tz).isoformat(),
        },
        "active_now": active_now,
        "last_tick_at": c.last_tick_at,
        "next_tick_at": next_tick_at.isoformat() if next_tick_at else None,
        "pacing": {
            "calls_per_minute": c.calls_per_minute,
            "parallel_calls": c.parallel_calls,
        },
        "totals": {
            "total": total,
            "pending": pending,
            "retry": retrying,
            "calling": calling,
            "done": done,
        },
        "percent_complete": pct,
        "counts": {  # convenience mirror for your cards
            "total": total,
            "done": done,
        },
        "eligible_now": eligible_now,
    }


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    sch = get_scheduler()
    job = sch.get_job(f"campaign:{campaign_id}")
    if job:
        job.remove()

    await CampaignLeadProgress.filter(campaign_id=campaign_id).delete()
    await c.delete()
    logger.info("campaign %s: deleted", campaign_id)
    return {"success": True, "detail": "Campaign deleted"}


@router.post("/campaigns/{campaign_id}/schedule")
async def update_schedule(campaign_id: int,
                          payload: CampaignUpdateSchedulePayload,
                          user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if payload.timezone is not None:
        c.timezone = payload.timezone
    if payload.days_of_week is not None:
        c.days_of_week = payload.days_of_week
    if payload.daily_start is not None:
        c.daily_start = payload.daily_start
    if payload.daily_end is not None:
        c.daily_end = payload.daily_end
    if payload.start_at is not None:
        c.start_at = payload.start_at
    if payload.end_at is not None:
        c.end_at = payload.end_at

    await c.save()
    _schedule_campaign_job(c.id, c.timezone)
    added = await _ensure_progress_rows(c)
    logger.info("campaign %s: schedule updated; queued_new=%d", c.id, added)
    return {"success": True, "detail": "Schedule updated"}


@router.post("/campaigns/{campaign_id}/retry-policy")
async def update_retry(campaign_id: int,
                       payload: RetryPolicyPayload,
                       user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    c.retry_on_busy = payload.retry_on_busy
    c.busy_retry_delay_minutes = payload.busy_retry_delay_minutes
    c.max_attempts = payload.max_attempts
    await c.save()
    logger.info("campaign %s: retry policy updated", c.id)
    return {"success": True, "detail": "Retry policy updated"}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c.status = CampaignStatus.PAUSED
    await c.save()
    logger.info("campaign %s: paused", c.id)
    return {"success": True, "detail": "Campaign paused"}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c.status = CampaignStatus.SCHEDULED
    await c.save()
    _schedule_campaign_job(c.id, c.timezone)
    added = await _ensure_progress_rows(c)
    logger.info("campaign %s: resumed; queued_new=%d", c.id, added)
    return {"success": True, "detail": "Campaign resumed"}


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c.status = CampaignStatus.STOPPED
    await c.save()

    sch = get_scheduler()
    job = sch.get_job(f"campaign:{campaign_id}")
    if job:
        job.remove()

    logger.info("campaign %s: stopped", c.id)
    return {"success": True, "detail": "Campaign stopped"}


@router.post("/campaigns/{campaign_id}/run-now")
async def run_now(campaign_id: int, payload: RunNowPayload,
                  user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await c.fetch_related("assistant", "user")

    await _ensure_progress_rows(c)

    todo = await CampaignLeadProgress.filter(
        campaign_id=c.id, status__in=["pending", "retry_scheduled"]
    ).order_by("id").limit(payload.batch_size).all()

    if not todo:
        return {"success": True, "detail": "No eligible leads to call right now."}

    placed = 0
    for prog in todo:
        lead = await Lead.get_or_none(id=prog.lead_id)
        if not lead:
            prog.status = "failed"
            prog.last_ended_reason = "error:lead-missing"
            await prog.save()
            continue

        if lead.dnc:
            prog.status = "skipped"
            prog.last_ended_reason = "skipped:dnc"
            await prog.save()
            continue

        try:
            prog.status = "calling"
            prog.attempt_count += 1
            prog.last_attempt_at = datetime.utcnow()
            await prog.save()

            call_id = await _place_vapi_call(c.user, c.assistant, lead)
            prog.last_call_id = call_id
            await prog.save()
            placed += 1

            get_scheduler().add_job(
                _process_call_outcome,
                DateTrigger(run_date=now_utc() + timedelta(minutes=12)),
                args=[c.id, lead.id, c.user.id, call_id],
            )
        except Exception as e:
            prog.status = "failed"
            prog.last_ended_reason = f"error:{repr(e)}"
            await prog.save()

    logger.info("campaign %s: run-now placed %d call(s)", c.id, placed)
    return {"success": True, "detail": f"Triggered {placed} lead(s) now."}


@router.post("/campaigns/{campaign_id}/refresh-leads")
async def refresh_campaign_leads(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")

    added = await _ensure_progress_rows(c)

    # kick near-immediate tick
    nudge_once(_tick_campaign, c.id, delay_seconds=1)
    logger.info("campaign %s: refresh-leads queued_new=%d and nudged", c.id, added)

    return {"success": True, "detail": f"Synced {added} new lead(s)."}


# ─────────────────────────────────────────────────────────────────────────────
# iCalendar export
# ─────────────────────────────────────────────────────────────────────────────
def _ics_for_campaign(c: Campaign) -> str:
    tz = c.timezone or "UTC"
    map_rr = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}
    byday = ",".join(map_rr.get(d, "MO") for d in (c.days_of_week or [0, 1, 2, 3, 4]))

    import pytz as _pytz
    zone = _pytz.timezone(tz)
    now_local = datetime.now(zone)
    hh, mm = (c.daily_start or "09:00").split(":")
    start_local = (c.start_at.astimezone(zone) if c.start_at else now_local).replace(
        hour=int(hh), minute=int(mm), second=0, microsecond=0
    )
    dtstart = start_local.strftime("%Y%m%dT%H%M%S")

    uid = f"campaign-{c.id}@yourapp"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//YourApp//Campaign//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:Call Campaign — {c.name}",
        f"DTSTART;TZID={tz}:{dtstart}",
        f"RRULE:FREQ=WEEKLY;BYDAY={byday}",
        f"DESCRIPTION:Calls placed within {c.daily_start}-{c.daily_end} local time. Server handles pacing & retries.",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


@router.get("/campaigns/{campaign_id}/calendar.ics")
async def campaign_calendar_ics(campaign_id: int, user: Annotated[User, Depends(get_current_user)]):
    c = await Campaign.get_or_none(id=campaign_id, user_id=user.id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    ics = _ics_for_campaign(c)
    return StreamingResponse(
        content=iter([ics]),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.ics"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Debug endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/debug/scheduler")
async def scheduler_jobs():
    """
    Inspect jobs currently registered in APScheduler.
    """
    jobs = get_scheduler().get_jobs()
    return [
        {
            "id": j.id,
            "name": getattr(j, "name", None),
            "next_run_time": (j.next_run_time.isoformat() if j.next_run_time else None),
        }
        for j in jobs
    ]


@router.post("/debug/tick/{campaign_id}")
async def debug_tick(campaign_id: int):
    """
    Force a one-off tick for a campaign (fires in ~1s).
    """
    nudge_once(_tick_campaign, campaign_id, delay_seconds=1)
    return {"success": True, "detail": f"Tick scheduled for campaign {campaign_id} in ~1s"}
