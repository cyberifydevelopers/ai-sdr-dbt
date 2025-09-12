# routes/intake.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Annotated, Optional, Dict, Any, List
from datetime import datetime

from models.form_submission import FormSubmission, SubmissionStatus
from helpers.token_helper import get_current_user, User
from helpers.intake_worker import scan_once
from helpers.ai_structurer import process_submission_to_appointment

router = APIRouter()


def _normalize_status(status: Optional[str]) -> Optional[SubmissionStatus]:
    """
    Convert query param to our enum (case-insensitive).
    Returns None if status is None.
    Raises HTTPException(400) if invalid.
    """
    if status is None:
        return None
    try:
        return SubmissionStatus(status.lower())
    except ValueError:
        allowed = [s.value for s in SubmissionStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Allowed values: {allowed}",
        )


def _normalize_item_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize enum/date fields for JSON responses.
    Works on dicts returned by .values().
    """
    out = dict(d)
    if "status" in out and isinstance(out["status"], SubmissionStatus):
        out["status"] = out["status"].value
    if "created_at" in out and isinstance(out["created_at"], datetime):
        out["created_at"] = out["created_at"].isoformat()
    if "updated_at" in out and isinstance(out.get("updated_at"), datetime):
        out["updated_at"] = out["updated_at"].isoformat()
    return out


# 🔹 Trigger one scan (batch run)
@router.post("/intake/scan")
async def intake_scan_now(user: Annotated[User, Depends(get_current_user)]):
    res = await scan_once()
    return {"ok": True, **res}


# 🔹 Manually process a single submission
@router.post("/intake/process/{submission_id}")
async def intake_process_one(
    submission_id: int,
    user: Annotated[User, Depends(get_current_user)],
):
    exists = await FormSubmission.filter(id=submission_id, user_id=user.id).exists()
    if not exists:
        raise HTTPException(404, "Submission not found for this user")

    res = await process_submission_to_appointment(submission_id)
    return {"ok": True, "result": res}


# 🔹 Get all submissions (User/Admin)
@router.get("/intake/submissions")
async def get_submissions(
    user: Annotated[User, Depends(get_current_user)],
    status: Optional[str] = Query(
        None, description="Filter by status (unbooked, booked, cancelled)"
    ),
    limit: int = 50,
    offset: int = 0,
):
    q = FormSubmission.filter(user_id=user.id).order_by("-created_at")

    status_enum = _normalize_status(status)
    if status_enum is not None:
        q = q.filter(status=status_enum)

    # Only concrete columns (no relations) -> avoids "Selecting relation 'user'..." errors
    raw_items: List[Dict[str, Any]] = await q.limit(limit).offset(offset).values()
    total = await FormSubmission.filter(user_id=user.id).count()

    items = [_normalize_item_dict(it) for it in raw_items]
    return {"ok": True, "total": total, "items": items}


# 🔹 View submission detail
@router.get("/intake/submissions/{submission_id}")
async def get_submission_detail(
    submission_id: int,
    user: Annotated[User, Depends(get_current_user)],
):
    # ValuesQuery has no .first(); use .limit(1).values() and index
    rows: List[Dict[str, Any]] = await (
        FormSubmission.filter(id=submission_id, user_id=user.id)
        .limit(1)
        .values()
    )
    if not rows:
        raise HTTPException(404, "Submission not found")

    sub = _normalize_item_dict(rows[0])
    return {"ok": True, "submission": sub}


# 🔹 Track processing progress
@router.get("/intake/progress")
async def intake_progress(user: Annotated[User, Depends(get_current_user)]):
    total = await FormSubmission.filter(user_id=user.id).count()
    booked = await FormSubmission.filter(
        user_id=user.id, status=SubmissionStatus.BOOKED
    ).count()
    cancelled = await FormSubmission.filter(
        user_id=user.id, status=SubmissionStatus.CANCELLED
    ).count()
    unbooked = await FormSubmission.filter(
        user_id=user.id, status=SubmissionStatus.UNBOOKED
    ).count()

    return {
        "ok": True,
        "progress": {
            "total": total,
            "booked": booked,
            "cancelled": cancelled,
            "unbooked": unbooked,
            "completion_rate": (booked / total * 100) if total > 0 else 0,
        },
    }


# 🔹 Analytics (Daily/Weekly breakdown)
@router.get("/intake/analytics")
async def intake_analytics(user: Annotated[User, Depends(get_current_user)]):
    submissions = await FormSubmission.filter(user_id=user.id)
    daily: Dict[str, Dict[str, int]] = {}
    for sub in submissions:
        day = sub.created_at.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"total": 0, "booked": 0, "cancelled": 0, "unbooked": 0}
        daily[day]["total"] += 1
        if sub.status == SubmissionStatus.BOOKED:
            daily[day]["booked"] += 1
        elif sub.status == SubmissionStatus.CANCELLED:
            daily[day]["cancelled"] += 1
        elif sub.status == SubmissionStatus.UNBOOKED:
            daily[day]["unbooked"] += 1

    return {"ok": True, "analytics": daily}
