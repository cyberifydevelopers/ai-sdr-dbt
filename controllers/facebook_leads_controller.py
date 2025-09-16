# controllers/facebook_leads_controller.py
from __future__ import annotations

import os
from fastapi import APIRouter, Request, HTTPException, Depends, Query, BackgroundTasks
from typing import Any, Dict
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

from helpers.token_helper import get_current_user
from models.auth import User
from models.facebook import FacebookIntegration, FacebookPage
from models.form_submission import FormSubmission, SubmissionStatus
from helpers.facebook_graph import FacebookGraph
from helpers.ai_structurer import process_submission_to_appointment
from controllers.form_controller import parse_any_datetime  # reuse your logic

# --------- ENV HELPERS ---------
def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise HTTPException(500, f"Missing required environment variable: {name}")
    return val or ""

META_GRAPH_VERSION = _env("META_GRAPH_VERSION", "v19.0")
PUBLIC_API_BASE = _env("PUBLIC_API_BASE", required=True).rstrip("/")
META_APP_VERIFY_TOKEN = _env("META_APP_VERIFY_TOKEN", required=True)

# Graph client from env (META_APP_ID / META_APP_SECRET / META_GRAPH_VERSION)
graph = FacebookGraph.from_env()

router = APIRouter(prefix="/facebook", tags=["facebook"])

# ---------- 4.1 Connect (OAuth) ----------
@router.get("/connect")
async def connect_facebook(user: User = Depends(get_current_user)):
    """
    Returns the URL for the user to click "Connect Facebook".
    After login/consent, Meta will redirect to /facebook/oauth/callback
    """
    redirect_uri = f"{PUBLIC_API_BASE}/facebook/oauth/callback"
    scope = ",".join([
        "pages_show_list",
        "pages_manage_metadata",
        "pages_read_engagement",
        "pages_manage_ads",
        "leads_retrieval",
    ])
    url = (
        f"https://www.facebook.com/{META_GRAPH_VERSION}/dialog/oauth"
        f"?client_id={os.getenv('META_APP_ID')}"
        f"&redirect_uri={redirect_uri}"
        f"&state={user.id}"
        f"&scope={scope}"
    )
    return {"success": True, "auth_url": url, "redirect_uri": redirect_uri}

@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str, request: Request):
    """
    1) Exchange code -> short-lived token
    2) Extend -> long-lived user token
    3) Save FacebookIntegration with fb_user_id
    """
    try:
        platform_user_id = int(state)
    except Exception:
        raise HTTPException(401, "Invalid OAuth state")

    platform_user = await User.get_or_none(id=platform_user_id)
    if not platform_user:
        raise HTTPException(401, "Invalid state user")

    redirect_uri = f"{PUBLIC_API_BASE}/facebook/oauth/callback"

    short = await graph.exchange_code_for_user_token(code=code, redirect_uri=redirect_uri)
    if not isinstance(short, dict) or "access_token" not in short:
        raise HTTPException(400, f"OAuth exchange failed: {short!r}")

    extended = await graph.extend_user_token(short["access_token"])
    user_token = extended.get("access_token") or short["access_token"]
    expires_in = extended.get("expires_in")  # seconds

    me = await graph.get_me(user_token)
    fb_user_id = (me or {}).get("id")
    if not fb_user_id:
        raise HTTPException(400, f"Unable to fetch /me: {me!r}")

    expires_at = None
    if expires_in:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except Exception:
            expires_at = None

    integ = await FacebookIntegration.get_or_none(user_id=platform_user.id, fb_user_id=fb_user_id)
    if not integ:
        integ = await FacebookIntegration.create(
            user_id=platform_user.id,
            fb_user_id=fb_user_id,
            user_access_token=user_token,
            token_expires_at=expires_at,
        )
    else:
        integ.user_access_token = user_token
        integ.token_expires_at = expires_at
        await integ.save()

    return {
        "success": True,
        "message": "Facebook connected",
        "fb_user_id": fb_user_id,
        "token_expires_at": expires_at.isoformat() if expires_at else None,
    }

# ---------- 4.2 Pages listing & linking ----------
@router.get("/pages")
async def list_pages(user: User = Depends(get_current_user)):
    integ = await FacebookIntegration.get_or_none(user_id=user.id)
    if not integ:
        raise HTTPException(400, "Connect Facebook first")

    pages = await graph.get_user_pages(integ.user_access_token)
    data = []
    for p in (pages or {}).get("data", []):
        exists = await FacebookPage.get_or_none(user_id=user.id, page_id=p.get("id"))
        data.append({
            "page_id": p.get("id"),
            "name": p.get("name"),
            "connected": bool(exists),
            "subscribed": bool(exists and exists.subscribed),
        })
    return {"success": True, "pages": data}

class LinkPageBody(BaseModel):
    page_id: str

@router.post("/pages/link")
async def link_page(body: LinkPageBody, user: User = Depends(get_current_user)):
    integ = await FacebookIntegration.get_or_none(user_id=user.id)
    if not integ:
        raise HTTPException(400, "Connect Facebook first")

    pages = await graph.get_user_pages(integ.user_access_token)
    if not isinstance(pages, dict):
        raise HTTPException(400, f"Failed to fetch pages: {pages!r}")

    page_obj = next((p for p in pages.get("data", []) if p.get("id") == body.page_id), None)
    if not page_obj:
        raise HTTPException(404, "Page not found in your accounts")

    page = await FacebookPage.get_or_none(user_id=user.id, page_id=body.page_id)
    if not page:
        page = await FacebookPage.create(
            user_id=user.id,
            page_id=page_obj.get("id"),
            name=page_obj.get("name"),
            page_access_token=page_obj.get("access_token") or "",
        )
    else:
        page.name = page_obj.get("name")
        page.page_access_token = page_obj.get("access_token") or page.page_access_token
        await page.save()

    return {"success": True, "page_id": page.page_id, "name": page.name}

# ---------- 4.3 Subscribe Page to Webhooks ----------
class SubscribeBody(BaseModel):
    page_id: str

@router.post("/pages/subscribe")
async def subscribe_page(body: SubscribeBody, user: User = Depends(get_current_user)):
    page = await FacebookPage.get_or_none(user_id=user.id, page_id=body.page_id)
    if not page:
        raise HTTPException(404, "Link the Page first")

    res = await graph.subscribe_app_to_page(page_id=page.page_id, page_token=page.page_access_token)
    if isinstance(res, dict) and res.get("success") is True:
        page.subscribed = True
        await page.save()
    else:
        # Bubble useful error back to UI
        raise HTTPException(400, f"Subscribe failed: {res!r}")
    return {"success": True, "facebook": res}

# ---------- 4.4 Webhook: Verify (GET) ----------
@router.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == META_APP_VERIFY_TOKEN:
        return hub_challenge  # Meta expects plain text
    raise HTTPException(403, "Verification failed")

# ---------- 4.5 Webhook: Receive (POST) ----------
@router.post("/webhook")
async def webhook_receive(request: Request, bg: BackgroundTasks):
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not graph.verify_signature(raw, sig):
        raise HTTPException(401, "Invalid signature")

    payload = await request.json()
    if payload.get("object") != "page":
        return {"success": True, "ignored": True}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value", {}) or {}
            leadgen_id = value.get("leadgen_id")
            page_id = value.get("page_id")
            if not (leadgen_id and page_id):
                continue
            bg.add_task(_process_leadgen, leadgen_id, page_id)

    return {"success": True}

# ---------- 4.6 Internal: process a single lead ----------
async def _process_leadgen(leadgen_id: str, page_id: str):
    page = await FacebookPage.get_or_none(page_id=page_id)
    if not page:
        return  # no token available

    lead = await graph.fetch_lead(leadgen_id, page.page_access_token)
    # Expected lead: created_time, field_data[{name,values}], ad_id, form_id, ...
    normalized = _normalize_lead_field_data(lead)

    extracted = {
        "first_name": normalized.get("first_name"),
        "last_name": normalized.get("last_name"),
        "email": normalized.get("email"),
        "phone": normalized.get("phone"),
        "booking_time": normalized.get("booking_time"),
        "additional_details": {
            "source": "facebook_lead_ads",
            "leadgen_id": leadgen_id,
            "page_id": page_id,
            "ad_id": lead.get("ad_id"),
            "form_id": lead.get("form_id"),
            "raw": lead,
        },
    }
    booking_dt = parse_any_datetime(extracted.get("booking_time"))
    user_id = page.user_id

    submission = None
    if extracted.get("email"):
        submission = await FormSubmission.get_or_none(email=extracted["email"], user_id=user_id)
    if (not submission) and extracted.get("phone"):
        submission = await FormSubmission.get_or_none(phone=extracted["phone"], user_id=user_id)

    minimal_ok = extracted.get("first_name") and (extracted.get("phone") or extracted.get("email"))

    if not submission:
        if minimal_ok:
            submission = await FormSubmission.create(
                user_id=user_id,
                first_name=extracted.get("first_name"),
                last_name=extracted.get("last_name"),
                email=extracted.get("email"),
                phone=extracted.get("phone"),
                booking_time=booking_dt,
                additional_details=extracted.get("additional_details"),
                raw_data=lead,
                status=SubmissionStatus.BOOKED if booking_dt else SubmissionStatus.UNBOOKED,
            )
        else:
            return
    else:
        if booking_dt:
            submission.booking_time = booking_dt
            submission.status = SubmissionStatus.BOOKED
        for key in ("first_name", "last_name", "email", "phone"):
            val = extracted.get(key)
            if val:
                setattr(submission, key, val)
        details = submission.additional_details or {}
        details.update(extracted.get("additional_details") or {})
        submission.additional_details = details
        submission.raw_data = lead
        await submission.save()

    await process_submission_to_appointment(submission.id)

def _normalize_lead_field_data(lead: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    fields = (lead or {}).get("field_data") or []
    kv: Dict[str, Any] = {}
    for f in fields:
        name = (f.get("name") or "").lower()
        vals = f.get("values") or []
        kv[name] = vals[0] if vals else None

    # Common mappings
    full_name = kv.get("full_name") or kv.get("name") or kv.get("your_name")
    first_name = kv.get("first_name") or kv.get("firstname") or kv.get("given_name")
    last_name = kv.get("last_name") or kv.get("lastname") or kv.get("family_name") or kv.get("surname")
    email = kv.get("email") or kv.get("email_address")
    phone = kv.get("phone_number") or kv.get("phone") or kv.get("mobile_number")

    if full_name and not (first_name or last_name):
        parts = full_name.strip().split()
        if parts:
            first_name = parts[0]
            if len(parts) > 1:
                last_name = " ".join(parts[1:])

    out["first_name"] = first_name
    out["last_name"] = last_name
    out["email"] = email
    out["phone"] = phone

    # Custom date/time (if your lead form has these fields)
    out["booking_time"] = kv.get("booking_time") or kv.get("preferred_time") or kv.get("date")

    return out
