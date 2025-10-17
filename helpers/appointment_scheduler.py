from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from tortoise.expressions import Q

from models.auth import User
from models.call_log import CallLog
from models.call_detail import CallDetail
from models.appointment import Appointment
from helpers.appointment_extractor import process_call_to_appointment

SCHED_ENABLED = os.getenv("APPT_SCHED_ENABLED", "true").lower() in ("1", "true", "yes", "on")
SCHED_EVERY_SECONDS = int(os.getenv("APPT_SCHED_EVERY_SECONDS", "120"))
SCHED_SCAN_WINDOW_MIN = int(os.getenv("APPT_SCHED_SCAN_WINDOW_MIN", "1440"))  # 24h
SCHED_MAX_PER_TICK = int(os.getenv("APPT_SCHED_MAX_PER_TICK", "50"))

# Only create for these unified call statuses (if present on CallLog)
ELIGIBLE_STATUSES = {"Booked", "Follow-up Needed"}

DEFAULT_TZ_FALLBACK = os.getenv("APPT_DEFAULT_TZ", "UTC")

_running_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


async def _tick_once():
    """
    One pass:
      - find recent calls with transcript/summary and no appointment yet
      - only for eligible statuses (if set)
      - up to SCHED_MAX_PER_TICK across all users (FIFO by time)
    """
    now = datetime.utcnow()
    since = now - timedelta(minutes=SCHED_SCAN_WINDOW_MIN)

    base_q = (
        CallLog.filter(call_started_at__gte=since)
        .filter(Q(transcript__isnull=False) | Q(summary__isnull=False))
        .filter(Q(call_id__isnull=False))
        .order_by("-call_started_at", "-id")
    )

    if ELIGIBLE_STATUSES:
        base_q = base_q.filter(status__in=list(ELIGIBLE_STATUSES))

    rows = await base_q.limit(500)

    processed = 0
    for cl in rows:
        if processed >= SCHED_MAX_PER_TICK:
            break

        try:
            # skip if appointment already exists
            exists = await Appointment.get_or_none(user_id=cl.user_id, source_call_id=cl.call_id)
            if exists:
                continue

            # optional: touch details
            _ = await CallDetail.get_or_none(user_id=cl.user_id, call_id=cl.call_id)

            user = await User.get(id=cl.user_id)
            appt_id = await process_call_to_appointment(
                user=user,
                call_id=cl.call_id,
                default_timezone=DEFAULT_TZ_FALLBACK,
            )
            if appt_id:
                processed += 1
        except Exception as e:
            # log & continue
            import logging, traceback
            logging.getLogger("appointment_scheduler").error(
                "[appt-sched] failed call_id=%s user_id=%s error=%s\n%s",
                getattr(cl, "call_id", None), getattr(cl, "user_id", None), e, traceback.format_exc()
            )

    return processed


async def _loop():
    import logging
    lg = logging.getLogger("appointment_scheduler")
    while _stop_event and not _stop_event.is_set():
        try:
            n = await _tick_once()
            lg.info("[appt-sched] tick processed=%s", n)
        except Exception as e:
            lg.exception("[appt-sched] loop error: %s", e)

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=SCHED_EVERY_SECONDS)
        except asyncio.TimeoutError:
            continue


def start_scheduler():
    global _running_task, _stop_event
    if not SCHED_ENABLED:
        return
    if _running_task and not _running_task.done():
        return
    _stop_event = asyncio.Event()
    _running_task = asyncio.create_task(_loop())


async def stop_scheduler():
    global _running_task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _running_task:
        try:
            await _running_task
        except Exception:
            pass
    _running_task = None
    _stop_event = None
