# # services/ai_structurer.py
# from __future__ import annotations
# from dotenv import load_dotenv
# load_dotenv()
# import json
# import os
# from datetime import datetime, timedelta
# from typing import Optional, Dict, Any

# from pydantic import BaseModel, Field, ValidationError, constr
# from zoneinfo import ZoneInfo

# from models.appointment import Appointment, AppointmentStatus
# from models.form_submission import FormSubmission

# DEFAULT_TZ = "UTC"
# DEFAULT_DURATION_MIN = 30


# # ---------- Pydantic schema the AI must return ----------
# class AppointmentDraft(BaseModel):
#     title: constr(strip_whitespace=True, min_length=1)
#     notes: Optional[str] = None
#     location: Optional[str] = None
#     phone: constr(strip_whitespace=True, min_length=5)

#     timezone: str  # IANA tz like 'Asia/Karachi'

#     start_at: datetime
#     end_at: Optional[datetime] = None
#     duration_minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)

#     status: AppointmentStatus = AppointmentStatus.SCHEDULED

#     def _ensure_tz(self, dt: datetime, tz: str) -> datetime:
#         """Ensure tz-aware datetime; if naive, attach tz."""
#         if dt.tzinfo and dt.tzinfo.utcoffset(dt) is not None:
#             return dt
#         return dt.replace(tzinfo=ZoneInfo(tz))

#     def normalize(self):
#         """Make fields coherent: tz-aware, fill end/duration, clamp sanity."""
#         self.timezone = self.timezone or DEFAULT_TZ

#         # Ensure tz-aware
#         self.start_at = self._ensure_tz(self.start_at, self.timezone)
#         if self.end_at:
#             self.end_at = self._ensure_tz(self.end_at, self.timezone)

#         # Derive missing piece(s)
#         if self.duration_minutes and not self.end_at:
#             self.end_at = self.start_at + timedelta(minutes=self.duration_minutes)
#         elif self.end_at and not self.duration_minutes:
#             self.duration_minutes = max(1, int((self.end_at - self.start_at).total_seconds() // 60))
#         elif not self.end_at and not self.duration_minutes:
#             self.duration_minutes = DEFAULT_DURATION_MIN
#             self.end_at = self.start_at + timedelta(minutes=DEFAULT_DURATION_MIN)

#         # Sanity: end must be after start
#         if self.end_at <= self.start_at:
#             self.end_at = self.start_at + timedelta(minutes=max(self.duration_minutes or DEFAULT_DURATION_MIN, 1))


# # ---------- OpenAI call (Chat Completions JSON mode) ----------
# async def build_appointment_json_from_raw(raw_data: Dict[str, Any], extracted_hint: Dict[str, Any]) -> AppointmentDraft:
#     """
#     Turn messy form payload into AppointmentDraft using OpenAI.
#     Uses Chat Completions with JSON mode; supports both new (>=1.x) and legacy (<1.x) SDKs.
#     """
#     # Prefer new SDK; fall back to legacy automatically
#     client_mode = "new"
#     try:
#         from openai import OpenAI  # type: ignore
#         oa_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#     except Exception:
#         import openai  # type: ignore
#         openai.api_key = os.getenv("OPENAI_API_KEY")
#         oa_client = openai
#         client_mode = "old"

#     system_msg = (
#         "You convert messy form data into a single Appointment JSON.\n"
#         "Return ONLY JSON with exactly these keys: "
#         "title, notes, location, phone, timezone, start_at, end_at, duration_minutes, status.\n"
#         "Timezone must be according to the location he provided and if not provided location we will default to UTC time zone. Dates must be ISO8601.\n"
#         "If unsure about a field, infer sensibly; otherwise set a reasonable default."
#     )

#     schema_hint = {
#         "title": "string (e.g., 'Discovery Call with John Doe')",
#         "notes": "string or null",
#         "location": "string or null (e.g., 'Zoom', 'Office')",
#         "phone": "string (any readable phone)",
#         "timezone": "per location decided tz string  e.g UTC",
#         "start_at": "ISO8601 datetime",
#         "end_at": "ISO8601 datetime or null",
#         "duration_minutes": "integer or null",
#         "status": "one of ['scheduled','cancelled','completed'] .check in the raw data if it is unbooked  . post it as cancelled in appointment table and if you found booked in the form table  post it as scheduled in the appointments table ",
#     }

#     user_payload = {
#         "instruction": "Map the following raw form payload to the target JSON fields.",
#         "target_schema": schema_hint,
#         "extracted_hint": extracted_hint,
#         "raw_payload": raw_data,
#     }

#     model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

#     if client_mode == "new":
    
#         resp = oa_client.chat.completions.create(
#             model=model,
#             temperature=0,
#             response_format={"type": "json_object"},
#             messages=[
#                 {"role": "system", "content": system_msg},
#                 {"role": "user", "content": json.dumps(user_payload)},
#             ],
#         )
#         content = resp.choices[0].message.content or "{}"
#     else:
#         # Legacy SDK (<1.x): no guaranteed JSON mode; still often returns JSON with proper prompting
#         resp = oa_client.ChatCompletion.create(
#             model=model,
#             temperature=0,
#             messages=[
#                 {"role": "system", "content": system_msg},
#                 {"role": "user", "content": json.dumps(user_payload)},
#             ],
#         )
#         content = resp["choices"][0]["message"]["content"] or "{}"

#     data = json.loads(content)
#     data.setdefault("title", "Appointment")
#     data.setdefault("timezone", DEFAULT_TZ)

#     draft = AppointmentDraft(**data)
#     draft.normalize()
#     return draft


# # ---------- Orchestrator: one submission -> one appointment (upsert) ----------
# async def process_submission_to_appointment(submission_id: int) -> Dict[str, Any]:
#     """
#     - Loads FormSubmission
#     - AI → AppointmentDraft
#     - Upsert into appointments (match by user?, phone, start_at)
#     - Marks additional_details.ai with processed status or error
#     """
#     sub = await FormSubmission.get_or_none(id=submission_id).prefetch_related("user")
#     if not sub:
#         return {"ok": False, "reason": "submission_not_found"}

#     # Read/prepare AI processing state
#     ad = sub.additional_details or {}
#     ai_meta = ad.get("ai") or {}

#     # If already processed successfully, skip
#     if ai_meta.get("processed") is True and ai_meta.get("appointment_id"):
#         return {"ok": True, "reason": "already_processed", "appointment_id": ai_meta.get("appointment_id")}

#     extracted_hint = {
#         "first_name": sub.first_name,
#         "last_name": sub.last_name,
#         "email": sub.email,
#         "phone": sub.phone,
#         "booking_time": sub.booking_time.isoformat() if sub.booking_time else None,
#         "status": sub.status.value if sub.status else None,
#     }

#     # Build draft with AI
#     try:
#         draft = await build_appointment_json_from_raw(sub.raw_data or {}, extracted_hint)
#     except ValidationError as ve:
#         ad.setdefault("ai", {})
#         ad["ai"]["processed"] = False
#         ad["ai"]["error"] = {
#             "type": "validation",
#             "detail": ve.errors(),
#             "at": datetime.utcnow().isoformat(),
#         }
#         sub.additional_details = ad
#         await sub.save(update_fields=["additional_details", "updated_at"])
#         return {"ok": False, "reason": "ai_validation_error", "detail": ve.errors()}
#     except Exception as e:
#         ad.setdefault("ai", {})
#         ad["ai"]["processed"] = False
#         ad["ai"]["error"] = {
#             "type": "inference",
#             "detail": str(e),
#             "at": datetime.utcnow().isoformat(),
#         }
#         sub.additional_details = ad
#         await sub.save(update_fields=["additional_details", "updated_at"])
#         return {"ok": False, "reason": "ai_call_failed", "detail": str(e)}

#     # Upsert rule: same (user if present), same phone & start_at
#     q = Appointment.filter(phone=draft.phone, start_at=draft.start_at)
#     if sub.user_id:
#         q = q.filter(user_id=sub.user_id)
#     existing = await q.first()

#     if existing:
#         existing.title = draft.title
#         existing.notes = draft.notes
#         existing.location = draft.location
#         existing.timezone = draft.timezone
#         existing.end_at = draft.end_at
#         existing.duration_minutes = draft.duration_minutes
#         existing.status = draft.status
#         await existing.save()
#         appt_id = str(existing.id)
#         action = "updated"
#     else:
#         appt = await Appointment.create(
#             user_id=sub.user_id,  # your model allows null
#             title=draft.title,
#             notes=draft.notes,
#             location=draft.location,
#             phone=draft.phone,
#             timezone=draft.timezone,
#             start_at=draft.start_at,
#             end_at=draft.end_at,
#             duration_minutes=draft.duration_minutes,
#             status=draft.status,
#         )
#         appt_id = str(appt.id)
#         action = "created"

#     # Mark processed
#     ad.setdefault("ai", {})
#     ad["ai"]["processed"] = True
#     ad["ai"]["appointment_id"] = appt_id
#     ad["ai"]["action"] = action
#     ad["ai"]["at"] = datetime.utcnow().isoformat()
#     sub.additional_details = ad
#     await sub.save(update_fields=["additional_details", "updated_at"])

#     return {"ok": True, "appointment_id": appt_id, "action": action}
















# services/ai_structurer.py
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field, ValidationError, constr
from zoneinfo import ZoneInfo

from models.appointment import Appointment, AppointmentStatus
from models.form_submission import FormSubmission

# --- Logging setup ---
logger = logging.getLogger("ai_structurer")
logger.setLevel(logging.INFO)

DEFAULT_TZ = "UTC"
DEFAULT_DURATION_MIN = 30


# ---------- Pydantic schema ----------
class AppointmentDraft(BaseModel):
    title: constr(strip_whitespace=True, min_length=1)
    notes: Optional[str] = None
    location: Optional[str] = None
    phone: constr(strip_whitespace=True, min_length=5)

    timezone: str  # IANA tz like 'Asia/Karachi'

    start_at: datetime
    end_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)

    status: AppointmentStatus = AppointmentStatus.SCHEDULED

    def _ensure_tz(self, dt: datetime, tz: str) -> datetime:
        if dt.tzinfo and dt.tzinfo.utcoffset(dt) is not None:
            return dt
        return dt.replace(tzinfo=ZoneInfo(tz))

    def normalize(self):
        self.timezone = self.timezone or DEFAULT_TZ

        self.start_at = self._ensure_tz(self.start_at, self.timezone)
        if self.end_at:
            self.end_at = self._ensure_tz(self.end_at, self.timezone)

        if self.duration_minutes and not self.end_at:
            self.end_at = self.start_at + timedelta(minutes=self.duration_minutes)
        elif self.end_at and not self.duration_minutes:
            self.duration_minutes = max(1, int((self.end_at - self.start_at).total_seconds() // 60))
        elif not self.end_at and not self.duration_minutes:
            self.duration_minutes = DEFAULT_DURATION_MIN
            self.end_at = self.start_at + timedelta(minutes=DEFAULT_DURATION_MIN)

        if self.end_at <= self.start_at:
            self.end_at = self.start_at + timedelta(minutes=max(self.duration_minutes or DEFAULT_DURATION_MIN, 1))


# ---------- OpenAI call ----------
async def build_appointment_json_from_raw(raw_data: Dict[str, Any], extracted_hint: Dict[str, Any]) -> AppointmentDraft:
    logger.info("[AI] Converting raw data into appointment JSON…")
    client_mode = "new"
    try:
        from openai import OpenAI  # type: ignore
        oa_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        import openai  # type: ignore
        openai.api_key = os.getenv("OPENAI_API_KEY")
        oa_client = openai
        client_mode = "old"

    system_msg = (
        "You convert messy form data into a single Appointment JSON.\n"
        "Return ONLY JSON with exactly these keys: "
        "title, notes, location, phone, timezone, start_at, end_at, duration_minutes, status."
    )

    schema_hint = {
        "title": "string",
        "notes": "string or null",
        "location": "string or null",
        "phone": "string",
        "timezone": "tz string e.g. UTC",
        "start_at": "ISO8601 datetime",
        "end_at": "ISO8601 datetime or null",
        "duration_minutes": "integer or null",
        "status": "one of ['scheduled','cancelled','completed']",
    }

    user_payload = {
        "instruction": "Map the following raw form payload to the target JSON fields.",
        "target_schema": schema_hint,
        "extracted_hint": extracted_hint,
        "raw_payload": raw_data,
    }

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if client_mode == "new":
        resp = oa_client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
        content = resp.choices[0].message.content or "{}"
    else:
        resp = oa_client.ChatCompletion.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
        content = resp["choices"][0]["message"]["content"] or "{}"

    logger.info("[AI] Response content: %s", content[:200])  # log preview

    data = json.loads(content)
    data.setdefault("title", "Appointment")
    data.setdefault("timezone", DEFAULT_TZ)

    draft = AppointmentDraft(**data)
    draft.normalize()
    return draft


# ---------- Orchestrator ----------
async def process_submission_to_appointment(submission_id: int) -> Dict[str, Any]:
    logger.info("[Process] Starting for submission_id=%s", submission_id)

    sub = await FormSubmission.get_or_none(id=submission_id).prefetch_related("user")
    if not sub:
        logger.error("[Process] Submission not found: %s", submission_id)
        return {"ok": False, "reason": "submission_not_found"}

    ad = sub.additional_details or {}
    ai_meta = ad.get("ai") or {}

    if ai_meta.get("processed") is True and ai_meta.get("appointment_id"):
        logger.info("[Process] Already processed → appointment_id=%s", ai_meta.get("appointment_id"))
        return {"ok": True, "reason": "already_processed", "appointment_id": ai_meta.get("appointment_id")}

    extracted_hint = {
        "first_name": sub.first_name,
        "last_name": sub.last_name,
        "email": sub.email,
        "phone": sub.phone,
        "booking_time": sub.booking_time.isoformat() if sub.booking_time else None,
        "status": sub.status.value if sub.status else None,
    }

    try:
        draft = await build_appointment_json_from_raw(sub.raw_data or {}, extracted_hint)
    except ValidationError as ve:
        logger.error("[AI] ValidationError: %s", ve)
        ad.setdefault("ai", {})
        ad["ai"]["processed"] = False
        ad["ai"]["error"] = {"type": "validation", "detail": ve.errors(), "at": datetime.utcnow().isoformat()}
        sub.additional_details = ad
        await sub.save(update_fields=["additional_details", "updated_at"])
        return {"ok": False, "reason": "ai_validation_error", "detail": ve.errors()}
    except Exception as e:
        logger.exception("[AI] Call failed")
        ad.setdefault("ai", {})
        ad["ai"]["processed"] = False
        ad["ai"]["error"] = {"type": "inference", "detail": str(e), "at": datetime.utcnow().isoformat()}
        sub.additional_details = ad
        await sub.save(update_fields=["additional_details", "updated_at"])
        return {"ok": False, "reason": "ai_call_failed", "detail": str(e)}

    # Upsert into appointments
    q = Appointment.filter(phone=draft.phone, start_at=draft.start_at)
    if sub.user_id:
        q = q.filter(user_id=sub.user_id)
    existing = await q.first()

    if existing:
        logger.info("[DB] Updating existing appointment id=%s", existing.id)
        existing.title = draft.title
        existing.notes = draft.notes
        existing.location = draft.location
        existing.timezone = draft.timezone
        existing.end_at = draft.end_at
        existing.duration_minutes = draft.duration_minutes
        existing.status = draft.status
        await existing.save()
        appt_id, action = str(existing.id), "updated"
    else:
        logger.info("[DB] Creating new appointment for phone=%s, start_at=%s", draft.phone, draft.start_at)
        appt = await Appointment.create(
            user_id=sub.user_id,
            title=draft.title,
            notes=draft.notes,
            location=draft.location,
            phone=draft.phone,
            timezone=draft.timezone,
            start_at=draft.start_at,
            end_at=draft.end_at,
            duration_minutes=draft.duration_minutes,
            status=draft.status,
        )
        appt_id, action = str(appt.id), "created"

    ad.setdefault("ai", {})
    ad["ai"]["processed"] = True
    ad["ai"]["appointment_id"] = appt_id
    ad["ai"]["action"] = action
    ad["ai"]["at"] = datetime.utcnow().isoformat()
    sub.additional_details = ad
    await sub.save(update_fields=["additional_details", "updated_at"])

    logger.info("[Process] Done → appointment_id=%s (%s)", appt_id, action)
    return {"ok": True, "appointment_id": appt_id, "action": action}
