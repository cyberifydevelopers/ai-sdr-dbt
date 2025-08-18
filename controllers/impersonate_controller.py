from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from models.auth import User
from helpers.token_helper import admin_required, generate_user_token
from typing import Optional
import os
from datetime import datetime

impersonate_router = APIRouter(tags=["Admin Impersonation"])

# Optional safety: block impersonating admins unless explicitly allowed
ALLOW_IMPERSONATE_ADMINS = os.getenv("ALLOW_IMPERSONATE_ADMINS", "false").lower() in ("1", "true", "yes")

class ImpersonatePayload(BaseModel):
    # Provide either user_id or email (email wins if both given)
    email: Optional[EmailStr] = None
    user_id: Optional[int] = None
    reason: Optional[str] = None  # for audit / UI

def _impersonation_denied(target: User) -> bool:
    role = (getattr(target, "role", None) or "user").lower()
    return (role == "admin") and (not ALLOW_IMPERSONATE_ADMINS)

@impersonate_router.post("/admin/impersonate/login-as")
async def admin_login_as(
    payload: ImpersonatePayload,
    admin_user: User = Depends(admin_required),
):
    """
    Admin-only: issue a user token without password/OTP.
    Adds claims: impersonation=True, impersonated_by=<admin_id>.
    """
    # find target
    target: Optional[User] = None
    if payload.email:
        target = await User.filter(email=payload.email).first()
    elif payload.user_id:
        target = await User.get_or_none(id=payload.user_id)

    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    if _impersonation_denied(target):
        raise HTTPException(
            status_code=403,
            detail="Impersonating admins is disabled. Set ALLOW_IMPERSONATE_ADMINS=true to allow."
        )

    # build token with extra claims so backend/UI can detect impersonation
    claims = {
        "id": target.id,
        "impersonation": True,
        "impersonated_by": admin_user.id,
        # optionally: short-lived token; only include if your token helper respects 'ttl_minutes'
        # "ttl_minutes": 60
    }
    token = generate_user_token(claims)

    # best-effort audit log (optional: wire to your DB if you have an Audit/Log model)
    try:
        reason = (payload.reason or "").strip()
        print(
            f"[IMPERSONATE] {datetime.utcnow().isoformat()} "
            f"admin_id={admin_user.id} -> user_id={target.id} "
            f"email={target.email} reason={reason!r}"
        )
        # If you have a model, do it like:
        # from models.audit import ImpersonationLog
        # await ImpersonationLog.create(
        #     admin_id=admin_user.id, user_id=target.id, reason=reason
        # )
    except Exception as e:
        # don't break the flow if logging fails
        print(f"[IMPERSONATE][WARN] audit logging failed: {e}")

    return {
        "success": True,
        "detail": "Impersonation token issued.",
        "token": token,
        "acting_as": {
            "id": target.id,
            "name": target.name,
            "email": target.email,
            "role": getattr(target, "role", "user"),
        },
        "impersonated_by": {
            "id": admin_user.id,
            "name": admin_user.name,
            "email": admin_user.email,
        },
        "impersonation": True,
    }

@impersonate_router.get("/admin/impersonate/check")
async def whoami_impersonation(
    admin_user: User = Depends(admin_required),
):
    """
    Simple sanity endpoint for admins (not the impersonated session).
    Confirms admin is authenticated and impersonation API is reachable.
    """
    return {
        "success": True,
        "detail": "Admin authenticated. Impersonation API is live.",
        "admin": {
            "id": admin_user.id,
            "email": admin_user.email,
            "role": getattr(admin_user, "role", "admin"),
        },
        "allow_impersonate_admins": ALLOW_IMPERSONATE_ADMINS,
    }
