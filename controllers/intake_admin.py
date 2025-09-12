# routes/intake_admin.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated

from models.form_submission import FormSubmission
from helpers.token_helper import get_current_user, User
from helpers.intake_worker import scan_once
from helpers.ai_structurer import process_submission_to_appointment

router = APIRouter()

@router.post("/intake/scan")
async def intake_scan_now(user: Annotated[User, Depends(get_current_user)]):
    """
    Manually trigger one scan pass (up to batch limit).
    """
    res = await scan_once()
    return {"ok": True, **res}

@router.post("/intake/process/{submission_id}")
async def intake_process_one(submission_id: int, user: Annotated[User, Depends(get_current_user)]):
    """
    Manually process a single submission by ID (useful for debugging).
    """
    sub = await FormSubmission.get_or_none(id=submission_id, user_id=user.id)
    if not sub:
        raise HTTPException(404, "Submission not found for this user")
    res = await process_submission_to_appointment(submission_id)
    return {"ok": True, "result": res}
