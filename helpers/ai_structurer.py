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

# from models.appointment import Appointment, AppointmentOutcome
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

#     status: AppointmentOutcome = AppointmentOutcome.SCHEDULED

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

from pydantic import BaseModel, Field, ValidationError, constr, field_validator
from zoneinfo import ZoneInfo

from models.appointment import Appointment, AppointmentOutcome
from models.form_submission import FormSubmission

logger = logging.getLogger("ai_structurer")
logger.setLevel(logging.INFO)

DEFAULT_TZ = "UTC"
DEFAULT_DURATION_MIN = 30

# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────
class AppointmentDraft(BaseModel):
    title: constr(strip_whitespace=True, min_length=1)
    notes: Optional[str] = None
    location: Optional[str] = None
    phone: constr(strip_whitespace=True, min_length=5)

    timezone: str  # IANA tz like 'Asia/Karachi'
    start_at: datetime
    end_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)

    # NEW enum aligned with controller/model
    status: AppointmentOutcome = AppointmentOutcome.FOLLOW_UP_NEEDED

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

# ─────────────────────────────────────────────────────────────
# OpenAI helpers
# ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_MSG = (
    "You convert messy form data into a single Appointment JSON.\n"
    "Return ONLY JSON with exactly these keys: "
    "title, notes, location, phone, timezone, start_at, end_at, duration_minutes, status.\n"
    "status must be one of: 'Booked' or 'Follow-up Needed'."
)

SCHEMA_HINT = {
    "title": "string",
    "notes": "string or null",
    "location": "string or null",
    "phone": "string",
    "timezone": "tz string e.g. 'UTC' or 'America/Los_Angeles'",
    "start_at": "ISO8601 datetime with or without timezone",
    "end_at": "ISO8601 datetime or null",
    "duration_minutes": "integer or null",
    "status": "one of ['Booked','Follow-up Needed']",
}

def _status_to_enum(s: str) -> AppointmentOutcome:
    s = (s or "").strip().lower()
    if s == "booked":
        return AppointmentOutcome.BOOKED
    # default/fallback
    return AppointmentOutcome.FOLLOW_UP_NEEDED

def _tz(dt: Optional[datetime], tz: str) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo and dt.tzinfo.utcoffset(dt) is not None:
        return dt
    try:
        return dt.replace(tzinfo=ZoneInfo(tz))
    except Exception:
        return dt.replace(tzinfo=ZoneInfo(DEFAULT_TZ))

async def build_appointment_json_from_raw(raw_data: Dict[str, Any], extracted_hint: Dict[str, Any]) -> AppointmentDraft:
    """
    Calls OpenAI to map arbitrary form payload to our unified appointment JSON.
    """
    if not OPENAI_API_KEY:
        # If no key, try a dumb fallback mapping to avoid hard failure
        dt = extracted_hint.get("booking_time")
        start = None
        try:
            if dt:
                start = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            pass

        draft = AppointmentDraft(
            title=(raw_data.get("title") or extracted_hint.get("first_name") or "Appointment"),
            notes=(raw_data.get("notes") or None),
            location=(raw_data.get("location") or None),
            phone=(raw_data.get("phone") or extracted_hint.get("phone") or "unknown"),
            timezone=(raw_data.get("timezone") or extracted_hint.get("timezone") or DEFAULT_TZ),
            start_at=(start or datetime.utcnow()),
            end_at=None,
            duration_minutes=raw_data.get("duration_minutes") or DEFAULT_DURATION_MIN,
            status=_status_to_enum(raw_data.get("status") or "Follow-up Needed"),
        )
        draft.normalize()
        return draft

    try:
        from openai import OpenAI  # new SDK
        client = OpenAI(api_key=OPENAI_API_KEY)
        use_new = True
    except Exception:
        import openai
        openai.api_key = OPENAI_API_KEY
        client = openai
        use_new = False

    user_payload = {
        "instruction": "Map the following raw payload to the target JSON fields.",
        "target_schema": SCHEMA_HINT,
        "extracted_hint": extracted_hint,
        "raw_payload": raw_data,
    }

    if use_new:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        content = resp.choices[0].message.content or "{}"
    else:
        resp = client.ChatCompletion.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        content = resp["choices"][0]["message"]["content"] or "{}"

    logger.info("[AI] Response content (preview): %s", content[:200])
    data = json.loads(content)

    # Defaults + normalization
    data.setdefault("title", "Appointment")
    data.setdefault("timezone", DEFAULT_TZ)
    # map status to enum string for Pydantic
    data["status"] = _status_to_enum(data.get("status") or "Follow-up Needed")

    # Pydantic accepts enum value directly
    draft = AppointmentDraft(**data)
    draft.normalize()
    return draft

# ─────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────
async def process_submission_to_appointment(submission_id: int) -> Dict[str, Any]:
    """
    Read a FormSubmission row, call OpenAI to structure → upsert Appointment.
    Writes extraction metadata to Appointment and marks submission.additional_details.ai.
    """
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
        "status": (sub.status.value if getattr(sub, "status", None) else None),
        # if you store assistant/call ids in form payload, surface here:
        "assistant_id": (ad.get("assistant_id") if isinstance(ad, dict) else None),
        "source_call_id": (ad.get("source_call_id") if isinstance(ad, dict) else None),
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

    # Upsert key = (user?, phone, start_at)
    q = Appointment.filter(phone=draft.phone, start_at=draft.start_at)
    if sub.user_id:
        q = q.filter(user_id=sub.user_id)
    existing = await q.first()

    # extraction metadata
    extraction_raw = {
        "source": "form_submission",
        "submission_id": sub.id,
        "raw_data": sub.raw_data,
        "extracted_hint": extracted_hint,
    }

    # Optionally pick these from the submission metadata if you have them
    assistant_id = extracted_hint.get("assistant_id")
    source_call_id = extracted_hint.get("source_call_id")

    if existing:
        logger.info("[DB] Updating appointment id=%s", existing.id)
        existing.title = draft.title
        existing.notes = draft.notes
        existing.location = draft.location
        existing.phone = draft.phone
        existing.timezone = draft.timezone
        existing.start_at = draft.start_at
        existing.end_at = draft.end_at
        existing.duration_minutes = draft.duration_minutes
        existing.status = draft.status
        # NEW columns
        if assistant_id:
            existing.assistant_id = assistant_id
        if source_call_id:
            existing.source_call_id = source_call_id
        existing.extraction_version = "v1"
        existing.extraction_confidence = None
        existing.extraction_raw = extraction_raw
        await existing.save()
        appt_id, action = str(existing.id), "updated"
    else:
        logger.info("[DB] Creating new appointment for phone=%s, start_at=%s", draft.phone, draft.start_at)
        appt = await Appointment.create(
            user_id=sub.user_id,
            assistant_id=assistant_id,
            source_call_id=source_call_id,
            source_transcript_id=None,
            title=draft.title,
            notes=draft.notes,
            location=draft.location,
            phone=draft.phone,
            timezone=draft.timezone,
            start_at=draft.start_at,
            end_at=draft.end_at,
            duration_minutes=draft.duration_minutes,
            status=draft.status,
            extraction_version="v1",
            extraction_confidence=None,
            extraction_raw=extraction_raw,
        )
        appt_id, action = str(appt.id), "created"

    # mark submission
    ad.setdefault("ai", {})
    ad["ai"]["processed"] = True
    ad["ai"]["appointment_id"] = appt_id
    ad["ai"]["action"] = action
    ad["ai"]["at"] = datetime.utcnow().isoformat()
    sub.additional_details = ad
    await sub.save(update_fields=["additional_details", "updated_at"])

    logger.info("[Process] Done → appointment_id=%s (%s)", appt_id, action)
    return {"ok": True, "appointment_id": appt_id, "action": action}
