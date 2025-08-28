# scheduler/campaign_scheduler.py
import os
from typing import Optional
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# Optional Redis jobstore (safe to ignore if not installed/configured)
try:
    from apscheduler.jobstores.redis import RedisJobStore
except Exception:  # pragma: no cover
    RedisJobStore = None  # type: ignore

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """
    Global singleton AsyncIOScheduler.
    Uses Redis jobstore if APS_REDIS_URL is set (optional).
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    jobstores = {}
    redis_url = os.getenv("APS_REDIS_URL", "").strip()
    if redis_url and RedisJobStore:
        jobstores["default"] = RedisJobStore.from_url(redis_url)

    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone=os.getenv("APS_TIMEZONE", "UTC"),
        job_defaults={
            "coalesce": True,
            "max_instances": 1, 
            "misfire_grace_time": int(os.getenv("APS_MISFIRE_GRACE_SECONDS", "60")),
        },
    )
    _scheduler.start()
    return _scheduler


def schedule_minutely_job(job_id: str, timezone: str, func, *args):
    """
    Generic helper: schedule `func(*args)` every minute in `timezone`.
    """
    sch = get_scheduler()
    old = sch.get_job(job_id)
    if old:
        old.remove()

    sch.add_job(
        func,
        CronTrigger(minute="*/1", timezone=timezone or "UTC"),
        args=list(args),
        id=job_id,
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
        max_instances=1,
    )


def nudge_once(func, *args, delay_seconds: int = 1):
    """
    Fire a one-off execution of `func(*args)` after `delay_seconds`.
    Useful to “tick” immediately after data changes.
    """
    sch = get_scheduler()
    sch.add_job(
        func,
        DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=delay_seconds)),
        args=list(args),
    )


async def reschedule_campaigns_on_startup():
    """
    FastAPI startup hook:
    - ensures scheduler is running
    - re-creates per-campaign cron jobs for SCHEDULED/RUNNING campaigns
    """
    get_scheduler()

    # Lazy imports to avoid circulars at module import time
    from models.campaign import Campaign, CampaignStatus  # noqa
    from controllers.campaign_controller import _schedule_campaign_job  # noqa

    cs = await Campaign.filter(
        status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING]
    ).all()

    for c in cs:
        _schedule_campaign_job(c.id, c.timezone)


def shutdown_scheduler(wait: bool = False):
    """
    FastAPI shutdown hook.
    """
    sch = get_scheduler()
    if sch.running:
        sch.shutdown(wait=wait)

