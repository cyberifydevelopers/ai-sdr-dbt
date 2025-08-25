# controllers/crm_controller.py
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import RedirectResponse, JSONResponse

from helpers.token_helper import get_current_user
from models.auth import User
from models.crm import IntegrationAccount, IntegrationOAuthState

router = APIRouter()

# -------------------------
# Provider config (OAuth app creds in env)
# -------------------------
def _cfg() -> Dict[str, Dict[str, str]]:
    return {
        "hubspot": {
            "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
            "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
            "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
            "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),  # must match app settings
            "scope": os.getenv("HUBSPOT_SCOPES", "crm.objects.contacts.read crm.objects.contacts.write"),
            "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),  # + /{access_token}
            "type": "oauth",
        },
        "salesforce": {
            "auth_url": os.getenv("SALESFORCE_AUTH_URL", "https://login.salesforce.com/services/oauth2/authorize"),
            "token_url": os.getenv("SALESFORCE_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token"),
            "client_id": os.getenv("SALESFORCE_CLIENT_ID", ""),
            "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", ""),
            "scope": os.getenv("SALESFORCE_SCOPES", "api refresh_token"),
            "type": "oauth",
        },
        "zoho": {
            "auth_url": os.getenv("ZOHO_AUTH_URL", "https://accounts.zoho.com/oauth/v2/auth"),
            "token_url": os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.com/oauth/v2/token"),
            "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("ZOHO_REDIRECT_URI", ""),
            "scope": os.getenv("ZOHO_SCOPES", "ZohoCRM.modules.ALL"),
            "type": "oauth",
        },
        "pipedrive": {
            "auth_url": os.getenv("PIPEDRIVE_AUTH_URL", "https://oauth.pipedrive.com/oauth/authorize"),
            "token_url": os.getenv("PIPEDRIVE_TOKEN_URL", "https://oauth.pipedrive.com/oauth/token"),
            "client_id": os.getenv("PIPEDRIVE_CLIENT_ID", ""),
            "client_secret": os.getenv("PIPEDRIVE_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("PIPEDRIVE_REDIRECT_URI", ""),
            "scope": os.getenv("PIPEDRIVE_SCOPES", "deals:full,contacts:full"),
            "type": "oauth",
        },
        "close": {
            "type": "api_key",  # Close uses API key (Bearer)
        },
    }

SUPPORTED = ("hubspot", "salesforce", "zoho", "pipedrive", "close")


# -------------------------
# Helpers
# -------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)

def _exp_from_seconds(seconds: int) -> datetime:
    # pad a minute early
    return _now() + timedelta(seconds=max(0, seconds - 60))


async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
    """
    Make a tiny test call to confirm access token works and fill org info if possible.
    """
    headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if crm == "hubspot":
            # GET /oauth/v1/access-tokens/{token}
            url = f"{_cfg()['hubspot']['verify_url'].rstrip('/')}/{acc.access_token}"
            r = await client.get(url, headers={"Accept": "application/json"})
            if not r.is_success:
                raise HTTPException(401, "HubSpot token validation failed.")
            j = r.json()
            acc.external_account_id = str(j.get("hub_id") or "")
            acc.external_account_name = j.get("user", {}).get("email") or None

        elif crm == "salesforce":
            # instance_url is in token response; check limits endpoint
            base = acc.instance_url or ""
            if not base:
                raise HTTPException(400, "Salesforce instance_url missing.")
            r = await client.get(f"{base}/services/data/", headers=headers)
            if not r.is_success:
                raise HTTPException(401, "Salesforce token validation failed.")

        elif crm == "zoho":
            # Light probe: users endpoint (org-bound); region default assumed
            r = await client.get("https://www.zohoapis.com/crm/v2/users?per_page=1", headers=headers)
            if r.status_code in (200, 204):
                pass  # ok; not all orgs expose names without extra scopes

        elif crm == "pipedrive":
            r = await client.get("https://api.pipedrive.com/v1/users/me", headers=headers)
            if not r.is_success:
                raise HTTPException(401, "Pipedrive token validation failed.")
            j = r.json().get("data") or {}
            acc.external_account_id = str(j.get("company_id") or "")
            acc.external_account_name = j.get("company_name") or None

        elif crm == "close":
            r = await client.get("https://api.close.com/api/v1/me/", headers=headers)
            if not r.is_success:
                raise HTTPException(401, "Close API key invalid.")
            j = r.json()
            acc.external_account_id = str(j.get("organization_id") or "")
            acc.external_account_name = (j.get("organization") or {}).get("name")


async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
    """
    Refresh OAuth tokens if expired/near-expiry.
    No-op for API-key CRMs (Close).
    """
    if crm == "close":
        return acc

    if not acc.expires_at or acc.expires_at > _now():
        return acc

    cfg = _cfg()[crm]
    data: Dict[str, Any] = {"grant_type": "refresh_token", "refresh_token": acc.refresh_token}

    # Provider-specific fields
    if crm in ("hubspot", "pipedrive", "zoho", "salesforce"):
        data["client_id"] = cfg["client_id"]
        data["client_secret"] = cfg["client_secret"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(cfg["token_url"], data=data)
        if not r.is_success:
            raise HTTPException(401, f"{crm} refresh failed: {r.text}")
        j = r.json()

    # Parse token response
    if crm == "salesforce":
        acc.access_token = j.get("access_token")
        acc.refresh_token = acc.refresh_token or j.get("refresh_token")  # sometimes not returned again
        acc.instance_url = j.get("instance_url") or acc.instance_url
        acc.expires_at = _exp_from_seconds(int(j.get("issued_at")) // 1000 if j.get("issued_at") else 3600)
    else:
        acc.access_token = j.get("access_token")
        acc.refresh_token = acc.refresh_token or j.get("refresh_token")
        expires_in = int(j.get("expires_in", 3600))
        acc.expires_at = _exp_from_seconds(expires_in)

    await acc.save()
    return acc


# -------------------------
# Public routes
# -------------------------

@router.get("/crm/providers")
async def list_providers():
    """List supported CRMs and connection type hints."""
    cfg = _cfg()
    out = []
    for name in SUPPORTED:
        c = cfg.get(name, {})
        out.append({
            "name": name,
            "type": c.get("type", "oauth"),
            "scopes": c.get("scope"),
            "has_oauth": c.get("type") == "oauth",
            "has_api_key": name == "close",
        })
    return out


@router.get("/crm/accounts")
async def list_accounts(user: User = Depends(get_current_user)):
    """List the current user's connected CRM accounts."""
    rows = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
    return [
        {
            "crm": r.crm,
            "label": r.label,
            "external_account_id": r.external_account_id,
            "external_account_name": r.external_account_name,
            "connected_at": r.created_at,
            "expires_at": r.expires_at,
        } for r in rows
    ]


class ConnectIn(BaseException):
    pass  # just to appease type hints in some IDEs


@router.post("/crm/connect/{crm}")
async def start_connect(
    crm: str,
    user: User = Depends(get_current_user),
    redirect_to: Optional[str] = Body(default="/integrations", embed=True),
):
    """
    Start connection:
    - OAuth CRMs → returns {"auth_url": "..."} to redirect browser
    - Close (API key) → use /crm/token/close instead
    """
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")
    if crm == "close":
        raise HTTPException(400, "Close uses API key. Call POST /crm/token/close.")

    cfg = _cfg()[crm]
    if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
        raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

    state = secrets.token_urlsafe(24)
    await IntegrationOAuthState.create(user=user, crm=crm, state=state, redirect_to=redirect_to)

    if crm == "hubspot":
        # https://app.hubspot.com/oauth/authorize?client_id=...&redirect_uri=...&scope=...&state=...
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "scope": cfg["scope"],
            "state": state,
        }
        auth_url = cfg["auth_url"] + "?" + httpx.QueryParams(params)

    elif crm == "salesforce":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
            # Tip: add "prompt=consent" if needed
        }
        auth_url = cfg["auth_url"] + "?" + httpx.QueryParams(params)

    elif crm == "zoho":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "access_type": "offline",
            "scope": cfg["scope"],
            "prompt": "consent",
            "state": state,
        }
        auth_url = cfg["auth_url"] + "?" + httpx.QueryParams(params)

    elif crm == "pipedrive":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        auth_url = cfg["auth_url"] + "?" + httpx.QueryParams(params)

    else:
        raise HTTPException(400, "Unsupported CRM")

    return {"auth_url": str(auth_url)}


@router.get("/crm/callback/{crm}")
async def oauth_callback(
    crm: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    OAuth callback — this one does NOT require auth, we resolve user via saved state.
    On success, redirects the browser back to the saved redirect_to with status.
    """
    crm = crm.lower()
    if crm not in SUPPORTED or crm == "close":
        return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

    st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
    if not st:
        return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

    # prepare redirect target (append status later)
    back = st.redirect_to or "/integrations"
    cfg = _cfg()[crm]

    if error:
        await st.delete()
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={error}")

    if not code:
        await st.delete()
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

    # Exchange code → tokens
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(cfg["token_url"], data=data)
        if not r.is_success:
            await st.delete()
            return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")

        j = r.json()

    # Upsert IntegrationAccount
    acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
    if not acc:
        acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

    # Provider-specific parsing
    if crm == "salesforce":
        acc.access_token = j.get("access_token")
        acc.refresh_token = j.get("refresh_token") or acc.refresh_token
        acc.instance_url = j.get("instance_url")
        # Salesforce doesn't always give expires_in; set 1 hour default
        exp = int(j.get("issued_at")) // 1000 if j.get("issued_at") else 3600
        acc.expires_at = datetime.now(timezone.utc) + timedelta(seconds=exp)
        acc.scope = j.get("scope")

    else:
        acc.access_token = j.get("access_token")
        acc.refresh_token = j.get("refresh_token") or acc.refresh_token
        acc.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(j.get("expires_in", 3600)))
        if crm == "pipedrive":
            # sometimes includes "api_domain"; store in instance_url for convenience
            acc.instance_url = j.get("api_domain") or acc.instance_url

    await _verify_and_fill_account(crm, acc)
    await acc.save()
    await st.delete()

    return RedirectResponse(url=f"{back}?crm={crm}&status=success")


# -------------------------
# API key flow (Close) + optional HubSpot PAT
# -------------------------

@router.post("/crm/token/{crm}")
async def set_token(
    crm: str,
    payload: Dict[str, str] = Body(..., example={"access_token": "xxxx"}),
    user: User = Depends(get_current_user),
):
    """
    For API-key/token CRMs:
    - close → {access_token: "<api key>"}
    Optional: if you prefer PAT for HubSpot, allow crm="hubspot" here as well.
    """
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")

    if crm not in ("close", "hubspot"):
        raise HTTPException(400, "This endpoint is only for Close (and optional HubSpot PAT).")

    token = (payload.get("access_token") or "").strip()
    if not token:
        raise HTTPException(400, "access_token required.")

    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
    if not acc:
        acc = await IntegrationAccount.create(user=user, crm=crm)

    acc.access_token = token
    acc.refresh_token = None
    acc.expires_at = None  # API key does not expire

    # verify
    await _verify_and_fill_account(crm, acc)
    await acc.save()

    return {"success": True, "message": f"{crm} token saved and verified."}


@router.delete("/crm/disconnect/{crm}")
async def disconnect(crm: str, user: User = Depends(get_current_user)):
    """Remove (or deactivate) CRM connection for current user."""
    crm = crm.lower()
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc.is_active = False
    await acc.save()
    return {"success": True, "message": f"Disconnected {crm}."}


# -------------------------
# Internal helper endpoint (optional): ensure token fresh before making API calls elsewhere
# -------------------------
@router.post("/crm/ensure-fresh/{crm}")
async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc = await _ensure_fresh_token(crm.lower(), acc)
    return {"success": True, "expires_at": acc.expires_at}
