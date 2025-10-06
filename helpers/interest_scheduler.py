# services/interest_scheduler.py
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List

from tortoise.transactions import in_transaction
from models.call_detail import CallDetail
from helpers.interest_classifier import classify_interest

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
BATCH_SIZE = 50                 # process in small batches to avoid spikes
RECHECK_AFTER_MINUTES = 120     # if we failed earlier, try again after 2h

async def _fetch_batch() -> List[CallDetail]:
    """
    Pick items that either:
      - have transcript but no interest_status; OR
      - have transcript and very old last_synced_at (retry).
    """
    cutoff = datetime.utcnow() - timedelta(minutes=RECHECK_AFTER_MINUTES)
    qs = CallDetail.filter(
        transcript__isnull=False
    ).filter(
        ( (CallDetail.interest_status.isnull(True)) | (CallDetail.last_synced_at.isnull(True)) | (CallDetail.last_synced_at < cutoff) )
    ).order_by("-id").limit(BATCH_SIZE)
    return await qs

async def _process_row(row: CallDetail) -> None:
    label, conf = classify_interest(row.transcript)
    row.last_synced_at = datetime.utcnow()
    if label:
        row.interest_status = label
        row.interest_confidence = conf
    await row.save()

async def run_interest_scheduler(stop_event: asyncio.Event, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """
    A long-running task that wakes every `interval_seconds` and classifies interest.
    Use app.on_event('startup') to launch this as a background task.
    """
    while not stop_event.is_set():
        try:
            batch = await _fetch_batch()
            if batch:
                async with in_transaction():
                    for row in batch:
                        await _process_row(row)
            # sleep (shorter if we had nothing to do)
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds if batch else 60)
        except asyncio.TimeoutError:
            # normal wake-up
            continue
        except Exception as e:
            # swallow errors and try again next tick
            print("[interest-scheduler] error:", e)
            await asyncio.sleep(10)

# Optional: one-shot manual trigger
async def classify_now_for_ids(ids: List[int]) -> int:
    done = 0
    rows = await CallDetail.filter(id__in=ids).all()
    async with in_transaction():
        for r in rows:
            await _process_row(r)
            done += 1
    return done
