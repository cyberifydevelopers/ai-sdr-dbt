# services/intake_worker.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from models.form_submission import FormSubmission, SubmissionStatus
from helpers.ai_structurer import process_submission_to_appointment

SCAN_INTERVAL_SECONDS = 300  # 5 minutes
BATCH_LIMIT = 50             # how many to process per pass

def _is_unprocessed(sub: FormSubmission) -> bool:
    """
    Decide whether to attempt AI processing.
    We avoid schema changes by using additional_details.ai.processed flag.
    """
    ad = sub.additional_details or {}
    ai = ad.get("ai") or {}
    if ai.get("processed") is True and ai.get("appointment_id"):
        return False
    # Only consider recent/active items (tweak as you like)
    if sub.status in (SubmissionStatus.UNBOOKED, SubmissionStatus.BOOKED):
        return True
    return False

async def scan_once(limit: int = BATCH_LIMIT) -> Dict[str, Any]:
    """
    Process up to `limit` unprocessed submissions.
    """
    candidates = await FormSubmission.all().order_by("-updated_at").limit(500)
    todo = [s for s in candidates if _is_unprocessed(s)][:limit]

    results: List[Dict[str, Any]] = []
    for sub in todo:
        try:
            res = await process_submission_to_appointment(sub.id)
        except Exception as e:
            res = {"ok": False, "reason": "unexpected_error", "detail": str(e), "submission_id": sub.id}
        results.append({"submission_id": sub.id, **res})
    return {
        "processed_count": len(todo),
        "results": results
    }

async def scheduler_loop(app) -> None:
    """
    Background loop: runs every 5 minutes.
    Call this once on startup with: app.add_event_handler("startup", start_scheduler(app))
    """
    app.state._intake_scheduler_running = True
    try:
        while app.state._intake_scheduler_running:
            try:
                await scan_once(BATCH_LIMIT)
            except Exception:
                # don't crash the loop
                pass
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
    finally:
        app.state._intake_scheduler_running = False

def start_scheduler(app):
    async def _start():
        app.state._intake_scheduler_task = asyncio.create_task(scheduler_loop(app))
    return _start

def stop_scheduler(app):
    async def _stop():
        app.state._intake_scheduler_running = False
        task = getattr(app.state, "_intake_scheduler_task", None)
        if task:
            task.cancel()
    return _stop
