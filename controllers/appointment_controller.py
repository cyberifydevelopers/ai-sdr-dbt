
# from pydantic import BaseModel
# from fastapi import APIRouter
# import logging

# router = APIRouter()
# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)

# class Appointment(BaseModel):
#     date: str
#     time: str
#     notes: str
#     title: str
#     phone: int
#     location: str
#     timezone: str
#     durationMinutes: int

# @router.post("/appointments/tool/schedule")
# async def hello(data: Appointment):
#     logger.info(data.model_dump())  
#     return {"success": True}







# # schemas/appointment.py
# from typing import Optional, Annotated
# from uuid import UUID
# from datetime import datetime
# from pydantic import BaseModel, Field, StringConstraints
# from models.appointment import AppointmentStatus

# # Reusable constrained types (Pydantic v2)
# DateStr = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]  # e.g. "2025-09-01"
# TimeStr = Annotated[str, StringConstraints(pattern=r"^\d{2}:\d{2}$")]        # e.g. "14:30"
# PhoneStr = Annotated[str, StringConstraints(min_length=11, max_length=16)]   # adapt as needed

# # Incoming payload (matches your original shape)
# class AppointmentCreate(BaseModel):
#     date: DateStr
#     time: TimeStr
#     notes: Optional[str] = None
#     title: str
#     # Phone as string (allows "+", leading zeros)
#     phone: PhoneStr
#     location: Optional[str] = None
#     timezone: str = Field(..., description="IANA tz (e.g., 'Asia/Karachi') or offset like '+05:00' or 'UTC+5'")
#     durationMinutes: int = Field(..., gt=0, le=24 * 60)

# # Outgoing payload
# class AppointmentOut(BaseModel):
#     id: UUID
#     title: str
#     notes: Optional[str]
#     location: Optional[str]
#     phone: str
#     timezone: str
#     start_at: datetime
#     end_at: datetime
#     duration_minutes: int
#     status: AppointmentStatus
#     created_at: datetime
#     updated_at: datetime

#     # Pydantic v2
#     model_config = {"from_attributes": True}



# import logging
# import re
# from datetime import datetime, timedelta, timezone as dtimezone
# from fastapi import APIRouter, HTTPException
# from zoneinfo import ZoneInfo

# from models.appointment import Appointment, AppointmentStatus

# router = APIRouter()
# logger = logging.getLogger(__name__)


# def _tzinfo_from_string(tz_str: str):
#     """
#     Accepts:
#       - IANA (e.g., "Asia/Karachi", "America/New_York")
#       - Offsets: "+05:00", "-0300", "UTC+5", "GMT+05:30", "+5"
#     Returns a tzinfo or raises ValueError.
#     """
#     # Try IANA first
#     try:
#         return ZoneInfo(tz_str)
#     except Exception:
#         pass

#     # Try offset forms
#     m = re.fullmatch(r'^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$', tz_str)
#     if m:
#         sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
#         if hh > 14 or mm > 59:
#             raise ValueError("Invalid offset")
#         delta = timedelta(hours=hh, minutes=mm)
#         if sign == "-":
#             delta = -delta
#         return dtimezone(delta)

#     raise ValueError("Invalid timezone string. Use IANA like 'Asia/Karachi' or an offset like '+05:00'.")


# @router.post("/appointments/tool/schedule", response_model=AppointmentOut)
# async def schedule_appointment(data: AppointmentCreate):
#     """
#     Creates and stores an appointment from {date, time, timezone, durationMinutes}.
#     """
#     try:
#         tzinfo = _tzinfo_from_string(data.timezone)

#         # Build tz-aware start datetime from provided local date & time
#         start_naive = datetime.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
#         start_at = start_naive.replace(tzinfo=tzinfo)  # assign local tz
#         end_at = start_at + timedelta(minutes=data.durationMinutes)

#         appt = await Appointment.create(
#             title=data.title,
#             notes=data.notes,
#             location=data.location,
#             phone=str(data.phone).strip(),
#             timezone=data.timezone,
#             start_at=start_at,
#             end_at=end_at,
#             duration_minutes=data.durationMinutes,
#             status=AppointmentStatus.SCHEDULED,
#         )
#         logger.info("Appointment created: %s", appt.id)

#         # Pydantic v2 serialization from ORM object
#         return AppointmentOut.model_validate(appt, from_attributes=True)

#     except ValueError as ve:
#         logger.exception("Validation error")
#         raise HTTPException(status_code=422, detail=str(ve))
#     except Exception:
#         logger.exception("Failed to create appointment")
#         raise HTTPException(status_code=500, detail="Failed to create appointment")


# @router.get("/appointments", response_model=list[AppointmentOut])
# async def list_appointments(status: AppointmentStatus | None = None):
#     """
#     List appointments (optionally filtered by status), newest first.
#     """
#     q = Appointment.all().order_by("-start_at")
#     if status:
#         q = q.filter(status=status)

#     rows = await q
#     # Pydantic v2 serialization
#     return [AppointmentOut.model_validate(r, from_attributes=True) for r in rows]


# @router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
# async def get_appointment(appointment_id: str):
#     """
#     Fetch one appointment by ID.
#     """
#     appt = await Appointment.get_or_none(id=appointment_id)
#     if not appt:
#         raise HTTPException(status_code=404, detail="Not found")
#     return AppointmentOut.model_validate(appt, from_attributes=True)













# schemas/appointment.py
from typing import Optional, Annotated
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, StringConstraints, field_validator
from models.appointment import AppointmentStatus

# Reusable constrained types (Pydantic v2)
DateStr = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]  # e.g. "2025-09-01"
TimeStr = Annotated[str, StringConstraints(pattern=r"^\d{2}:\d{2}$")]        # e.g. "14:30"
PhoneStr = Annotated[str, StringConstraints(min_length=11, max_length=16)]   # adapt as needed

# Incoming payload (matches your original shape)
class AppointmentCreate(BaseModel):
    date: DateStr
    time: TimeStr
    notes: Optional[str] = None
    title: str
    # Phone as string (allows "+", leading zeros)
    phone: PhoneStr
    location: Optional[str] = None
    timezone: str = Field(..., description="IANA tz (e.g., 'Asia/Karachi') or offset like '+05:00' or 'UTC+5'")
    durationMinutes: int = Field(..., gt=0, le=24 * 60)

# Minimal body for status updates (accepts 'canceled' alias; case-insensitive)
class AppointmentStatusPatch(BaseModel):
    status: AppointmentStatus

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        s = str(v).strip().lower()
        if s == "canceled":  # alias support
            s = "cancelled"
        try:
            return AppointmentStatus(s)
        except Exception:
            raise ValueError("status must be one of: scheduled, completed, cancelled")

# Outgoing payload
class AppointmentOut(BaseModel):
    id: UUID
    title: str
    notes: Optional[str]
    location: Optional[str]
    phone: str
    timezone: str
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime

    # Pydantic v2
    model_config = {"from_attributes": True}



# routes/appointments.py
import logging
import re
from datetime import datetime, timedelta, timezone as dtimezone
from fastapi import APIRouter, HTTPException
from zoneinfo import ZoneInfo

from models.appointment import Appointment, AppointmentStatus

router = APIRouter()
logger = logging.getLogger(__name__)


def _tzinfo_from_string(tz_str: str):
    """
    Accepts:
      - IANA (e.g., "Asia/Karachi", "America/New_York")
      - Offsets: "+05:00", "-0300", "UTC+5", "GMT+05:30", "+5"
    Returns a tzinfo or raises ValueError.
    """
    # Try IANA first
    try:
        return ZoneInfo(tz_str)
    except Exception:
        pass

    # Try offset forms
    m = re.fullmatch(r'^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$', tz_str)
    if m:
        sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if hh > 14 or mm > 59:
            raise ValueError("Invalid offset")
        delta = timedelta(hours=hh, minutes=mm)
        if sign == "-":
            delta = -delta
        return dtimezone(delta)

    raise ValueError("Invalid timezone string. Use IANA like 'Asia/Karachi' or an offset like '+05:00'.")


@router.post("/appointments/tool/schedule", response_model=AppointmentOut)
async def schedule_appointment(data: AppointmentCreate):
    """
    Creates and stores an appointment from {date, time, timezone, durationMinutes}.
    """
    try:
        tzinfo = _tzinfo_from_string(data.timezone)
    
        # Build tz-aware start datetime from provided local date & time
        start_naive = datetime.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
        start_at = start_naive.replace(tzinfo=tzinfo)  # assign local tz
        end_at = start_at + timedelta(minutes=data.durationMinutes)

        appt = await Appointment.create(
            title=data.title,
            notes=data.notes,
            location=data.location,
            phone=str(data.phone).strip(),
            timezone=data.timezone,
            start_at=start_at,
            end_at=end_at,
            duration_minutes=data.durationMinutes,
            status=AppointmentStatus.SCHEDULED,
        )
        logger.info("Appointment created: %s", appt.id)

        # Pydantic v2 serialization from ORM object
        return AppointmentOut.model_validate(appt, from_attributes=True)

    except ValueError as ve:
        logger.exception("Validation error")
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception:
        logger.exception("Failed to create appointment")
        raise HTTPException(status_code=500, detail="Failed to create appointment")


@router.get("/appointments", response_model=list[AppointmentOut])
async def list_appointments(status: AppointmentStatus | None = None):
    """
    List appointments (optionally filtered by status), newest first.
    """
    q = Appointment.all().order_by("-start_at")
    if status:
        q = q.filter(status=status)

    rows = await q
    # Pydantic v2 serialization
    return [AppointmentOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(appointment_id: str):
    """
    Fetch one appointment by ID.
    """
    appt = await Appointment.get_or_none(id=appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")
    return AppointmentOut.model_validate(appt, from_attributes=True)


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
async def update_appointment_status(appointment_id: str, data: AppointmentStatusPatch):
    """
    Update only the status of an appointment. Frontend sends: { "status": "scheduled|completed|cancelled" }.
    Accepts 'canceled' (US spelling) as alias for 'cancelled'.
    """
    appt = await Appointment.get_or_none(id=appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")

    new_status = data.status
    if str(appt.status) == new_status:
        # No change—return current resource for idempotency
        return AppointmentOut.model_validate(appt, from_attributes=True)

    appt.status = new_status
    await appt.save(update_fields=["status", "updated_at"])
    logger.info("Appointment %s status updated to %s", appt.id, new_status)
    return AppointmentOut.model_validate(appt, from_attributes=True)
