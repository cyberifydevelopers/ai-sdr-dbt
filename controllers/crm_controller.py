
# # import os
# # import secrets
# # from datetime import datetime, timedelta, timezone
# # from typing import Optional, Dict, Any
# # from urllib.parse import urlparse, quote_plus

# # import httpx
# # from fastapi import APIRouter, Depends, HTTPException, Query, Body
# # from fastapi.responses import RedirectResponse, JSONResponse

# # from helpers.token_helper import get_current_user
# # from models.auth import User
# # from models.crm import IntegrationAccount, IntegrationOAuthState

# # router = APIRouter()

# # # -------------------------
# # # Provider config (OAuth app creds in env)
# # # -------------------------
# # def _cfg() -> Dict[str, Dict[str, str]]:
# #     return {
# #         "hubspot": {
# #             "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
# #             "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
# #             "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
# #             "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
# #             "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
# #             # default includes contacts/deals/leads/lists + oauth
# #             "scope": os.getenv(
# #                 "HUBSPOT_SCOPES",
# #                 "crm.objects.contacts.read crm.objects.contacts.write "
# #                 "crm.objects.deals.read crm.objects.deals.write "
# #                 "crm.objects.leads.read crm.objects.leads.write "
# #                 "crm.lists.read crm.lists.write oauth"
# #             ),
# #             "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
# #             "type": "oauth",
# #         },
# #         "salesforce": {
# #             "auth_url": os.getenv("SALESFORCE_AUTH_URL", "https://login.salesforce.com/services/oauth2/authorize"),
# #             "token_url": os.getenv("SALESFORCE_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token"),
# #             "client_id": os.getenv("SALESFORCE_CLIENT_ID", ""),
# #             "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET", ""),
# #             "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", ""),
# #             "scope": os.getenv("SALESFORCE_SCOPES", "api refresh_token"),
# #             "type": "oauth",
# #         },
# #         "zoho": {
# #             "auth_url": os.getenv("ZOHO_AUTH_URL", "https://accounts.zoho.com/oauth/v2/auth"),
# #             "token_url": os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.com/oauth/v2/token"),
# #             "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
# #             "client_secret": os.getenv("ZOHO_CLIENT_SECRET", ""),
# #             "redirect_uri": os.getenv("ZOHO_REDIRECT_URI", ""),
# #             # NOTE: multiple scopes are COMMA-separated for Zoho
# #             "scope": os.getenv("ZOHO_SCOPES", "ZohoCRM.modules.ALL"),
# #             "type": "oauth",
# #         },
# #         "pipedrive": {
# #             "auth_url": os.getenv("PIPEDRIVE_AUTH_URL", "https://oauth.pipedrive.com/oauth/authorize"),
# #             "token_url": os.getenv("PIPEDRIVE_TOKEN_URL", "https://oauth.pipedrive.com/oauth/token"),
# #             "client_id": os.getenv("PIPEDRIVE_CLIENT_ID", ""),
# #             "client_secret": os.getenv("PIPEDRIVE_CLIENT_SECRET", ""),
# #             "redirect_uri": os.getenv("PIPEDRIVE_REDIRECT_URI", ""),
# #             # space-separated scopes for Pipedrive
# #             "scope": os.getenv("PIPEDRIVE_SCOPES", "deals:full contacts:full"),
# #             "type": "oauth",
# #         },
# #         "close": {
# #             "type": "api_key",  # Close uses API key (Bearer)
# #         },
# #     }

# # SUPPORTED = ("hubspot", "salesforce", "zoho", "pipedrive", "close")

# # # -------------------------
# # # Helpers
# # # -------------------------
# # def _now() -> datetime:
# #     return datetime.now(timezone.utc)

# # def _exp_from_seconds(seconds: int) -> datetime:
# #     # pad a minute early
# #     return _now() + timedelta(seconds=max(0, seconds - 60))

# # def _sanitize_redirect(back: str) -> str:
# #     """Prevent open-redirects: allow only same-site relative paths or whitelisted origins via env."""
# #     if back and back.startswith("/") and not back.startswith("//"):
# #         return back
# #     allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
# #     if back and allowed:
# #         p = urlparse(back)
# #         origin = f"{p.scheme}://{p.netloc}"
# #         if origin in allowed:
# #             return back
# #     return "/integrations"

# # # ---- Zoho DC helpers ----
# # _ZOHO_ACCOUNTS_TO_API = {
# #     "accounts.zoho.com": "https://www.zohoapis.com",
# #     "accounts.zoho.eu": "https://www.zohoapis.eu",
# #     "accounts.zoho.in": "https://www.zohoapis.in",
# #     "accounts.zoho.com.au": "https://www.zohoapis.com.au",
# #     "accounts.zoho.jp": "https://www.zohoapis.jp",
# #     "accounts.zoho.uk": "https://www.zohoapis.uk",
# # }
# # _ZOHO_API_TO_ACCOUNTS = {
# #     "www.zohoapis.com": "https://accounts.zoho.com",
# #     "www.zohoapis.eu": "https://accounts.zoho.eu",
# #     "www.zohoapis.in": "https://accounts.zoho.in",
# #     "www.zohoapis.com.au": "https://accounts.zoho.com.au",
# #     "www.zohoapis.jp": "https://accounts.zoho.jp",
# #     "www.zohoapis.uk": "https://accounts.zoho.uk",
# # }

# # def _zoho_api_base_from_accounts_server(accounts_server: Optional[str]) -> Optional[str]:
# #     if not accounts_server:
# #         return None
# #     try:
# #         host = urlparse(accounts_server).netloc or accounts_server
# #         return _ZOHO_ACCOUNTS_TO_API.get(host)
# #     except Exception:
# #         return None

# # def _zoho_api_base_from_token_url(token_url: str) -> str:
# #     try:
# #         host = urlparse(token_url).netloc
# #         return _ZOHO_ACCOUNTS_TO_API.get(host, "https://www.zohoapis.com")
# #     except Exception:
# #         return "https://www.zohoapis.com"

# # def _zoho_accounts_from_api_base(api_base: str) -> str:
# #     host = urlparse(api_base).netloc
# #     return _ZOHO_API_TO_ACCOUNTS.get(host, "https://accounts.zoho.com")

# # # -------------------------
# # # Token verification
# # # -------------------------
# # async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
# #     """
# #     Make a tiny test call to confirm access token works and fill org info if possible.
# #     Relaxed for Zoho: if Accounts token is valid but CRM probes fail (new org), we still accept.
# #     """
# #     async with httpx.AsyncClient(timeout=30.0) as client:
# #         if crm == "hubspot":
# #             url = f"{_cfg()['hubspot']['verify_url'].rstrip('/')}/{acc.access_token}"
# #             r = await client.get(url, headers={"Accept": "application/json"})
# #             if r.is_success:
# #                 j = r.json()
# #                 acc.external_account_id = str(j.get("hub_id") or j.get("hubId") or "")
# #                 u = j.get("user")
# #                 if isinstance(u, str):
# #                     acc.external_account_name = u
# #                 elif isinstance(u, dict):
# #                     acc.external_account_name = u.get("email") or u.get("name") or None
# #                 else:
# #                     acc.external_account_name = None
# #             else:
# #                 # Fallback trivial call (also works for PAT)
# #                 r2 = await client.get(
# #                     "https://api.hubapi.com/crm/v3/owners?limit=1",
# #                     headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 )
# #                 if not r2.is_success:
# #                     raise HTTPException(401, "HubSpot token validation failed.")

# #         elif crm == "salesforce":
# #             base = acc.instance_url or ""
# #             if not base:
# #                 raise HTTPException(400, "Salesforce instance_url missing.")
# #             r = await client.get(
# #                 f"{base.rstrip('/')}/services/data/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(401, "Salesforce token validation failed.")

# #         elif crm == "zoho":
# #             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()['zoho']['token_url'])).rstrip("/")
# #             accounts_base = _zoho_accounts_from_api_base(api_base)
# #             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}

# #             r_acc = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
# #             if r_acc.status_code not in (200, 204):
# #                 raise HTTPException(401, f"Zoho accounts verify {r_acc.status_code}: {(r_acc.text or '')[:300]}")
# #             try:
# #                 info = r_acc.json()
# #                 acc.external_account_name = info.get("Email") or info.get("email") or acc.external_account_name
# #             except Exception:
# #                 pass

# #             endpoints = [
# #                 "/crm/v2/Contacts?fields=id&per_page=1",
# #                 "/crm/v2/Leads?fields=id&per_page=1",
# #                 "/crm/v2/settings/modules?per_page=1",
# #             ]
# #             ok = False
# #             for ep in endpoints:
# #                 r = await client.get(f"{api_base}{ep}", headers=zheaders)
# #                 if r.status_code in (200, 204):
# #                     ok = True
# #                     break
# #             if not ok:
# #                 acc.external_account_id = acc.external_account_id or ""

# #         elif crm == "pipedrive":
# #             r = await client.get(
# #                 "https://api.pipedrive.com/v1/users/me",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(401, "Pipedrive token validation failed.")
# #             j = r.json().get("data") or {}
# #             acc.external_account_id = str(j.get("company_id") or "")
# #             acc.external_account_name = j.get("company_name") or None

# #         elif crm == "close":
# #             r = await client.get(
# #                 "https://api.close.com/api/v1/me/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(401, "Close API key invalid.")
# #             j = r.json()
# #             acc.external_account_id = str(j.get("organization_id") or "")
# #             acc.external_account_name = (j.get("organization") or {}).get("name")

# # # -------------------------
# # # Refresh tokens
# # # -------------------------
# # async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
# #     if crm == "close":
# #         return acc

# #     SKEW_SECONDS = 120
# #     if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
# #         return acc

# #     cfg = _cfg()[crm]
# #     if not acc.refresh_token:
# #         return acc

# #     data: Dict[str, Any] = {"grant_type": "refresh_token", "refresh_token": acc.refresh_token}
# #     if crm in ("hubspot", "pipedrive", "zoho", "salesforce"):
# #         data["client_id"] = cfg["client_id"]
# #         data["client_secret"] = cfg["client_secret"]

# #     async with httpx.AsyncClient(timeout=30.0) as client:
# #         r = await client.post(cfg["token_url"], data=data)
# #         if not r.is_success:
# #             raise HTTPException(401, f"{crm} refresh failed: {r.text}")
# #         j = r.json()

# #     # normalize expires_in to int
# #     def _get_exp(v, default=3600):
# #         try:
# #             return int(v)
# #         except Exception:
# #             return default

# #     if crm == "salesforce":
# #         acc.access_token = j.get("access_token")
# #         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
# #         acc.instance_url = j.get("instance_url") or acc.instance_url
# #         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
# #     else:
# #         acc.access_token = j.get("access_token")
# #         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
# #         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
# #         if crm == "pipedrive":
# #             acc.instance_url = j.get("api_domain") or acc.instance_url
# #         if crm == "zoho":
# #             acc.instance_url = j.get("api_domain") or acc.instance_url

# #     await acc.save()
# #     return acc

# # # -------------------------
# # # Public routes
# # # -------------------------
# # @router.get("/crm/providers")
# # async def list_providers():
# #     cfg = _cfg()
# #     out = []
# #     for name in SUPPORTED:
# #         c = cfg.get(name, {})
# #         out.append({
# #             "name": name,
# #             "type": c.get("type", "oauth"),
# #             "scopes": c.get("scope"),
# #             "has_oauth": c.get("type") == "oauth",
# #             "has_api_key": name == "close",
# #         })
# #     return out

# # @router.get("/crm/accounts")
# # async def list_accounts(user: User = Depends(get_current_user)):
# #     rows = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
# #     return [
# #         {
# #             "crm": r.crm,
# #             "label": r.label,
# #             "external_account_id": r.external_account_id,
# #             "external_account_name": r.external_account_name,
# #             "connected_at": r.created_at,
# #             "expires_at": r.expires_at,
# #         } for r in rows
# #     ]

# # @router.post("/crm/connect/{crm}")
# # async def start_connect(
# #     crm: str,
# #     user: User = Depends(get_current_user),
# #     redirect_to: Optional[str] = Body(default="/integrations", embed=True),
# # ):
# #     crm = crm.lower()
# #     if crm not in SUPPORTED:
# #         raise HTTPException(400, "Unsupported CRM")
# #     if crm == "close":
# #         raise HTTPException(400, "Close uses API key. Call POST /crm/token/close.")

# #     cfg = _cfg()[crm]
# #     if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
# #         raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

# #     state = secrets.token_urlsafe(24)
# #     await IntegrationOAuthState.create(
# #         user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/integrations")
# #     )

# #     if crm == "hubspot":
# #         params = {
# #             "client_id": cfg["client_id"],
# #             "redirect_uri": cfg["redirect_uri"],
# #             "scope": cfg["scope"],
# #             "state": state,
# #             "response_type": "code",
# #         }
# #         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

# #     elif crm == "salesforce":
# #         params = {
# #             "client_id": cfg["client_id"],
# #             "redirect_uri": cfg["redirect_uri"],
# #             "response_type": "code",
# #             "scope": cfg["scope"],
# #             "state": state,
# #         }
# #         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

# #     elif crm == "zoho":
# #         params = {
# #             "client_id": cfg["client_id"],
# #             "redirect_uri": cfg["redirect_uri"],
# #             "response_type": "code",
# #             "access_type": "offline",
# #             "scope": cfg["scope"],
# #             "prompt": "consent",
# #             "state": state,
# #         }
# #         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

# #     elif crm == "pipedrive":
# #         params = {
# #             "client_id": cfg["client_id"],
# #             "redirect_uri": cfg["redirect_uri"],
# #             "response_type": "code",
# #             "scope": cfg["scope"],
# #             "state": state,
# #         }
# #         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
# #     else:
# #         raise HTTPException(400, "Unsupported CRM")

# #     return {"auth_url": auth_url}

# # @router.get("/crm/callback/{crm}")
# # async def oauth_callback(
# #     crm: str,
# #     code: Optional[str] = Query(None),
# #     state: Optional[str] = Query(None),
# #     error: Optional[str] = Query(None),
# #     accounts_server: Optional[str] = Query(None, alias="accounts-server"),
# # ):
# #     crm = crm.lower()
# #     if crm not in SUPPORTED or crm == "close":
# #         return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

# #     st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
# #     if not st:
# #         return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

# #     back = _sanitize_redirect(st.redirect_to or "/integrations")
# #     cfg = _cfg()[crm]

# #     if error:
# #         await st.delete()
# #         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

# #     if not code:
# #         await st.delete()
# #         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

# #     data = {
# #         "grant_type": "authorization_code",
# #         "code": code,
# #         "redirect_uri": cfg["redirect_uri"],
# #         "client_id": cfg["client_id"],
# #         "client_secret": cfg["client_secret"],
# #     }

# #     async with httpx.AsyncClient(timeout=30.0) as client:
# #         r = await client.post(cfg["token_url"], data=data)
# #         if not r.is_success:
# #             await st.delete()
# #             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")
# #         j = r.json()

# #     acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
# #     if not acc:
# #         acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

# #     # --- store tokens / instance data
# #     def _as_int(v, default=3600):
# #         try:
# #             return int(v)
# #         except Exception:
# #             return default

# #     if crm == "salesforce":
# #         acc.access_token = j.get("access_token")
# #         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
# #         acc.instance_url = j.get("instance_url") or acc.instance_url
# #         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
# #     else:
# #         acc.access_token = j.get("access_token")
# #         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
# #         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
# #         if crm == "pipedrive":
# #             acc.instance_url = j.get("api_domain") or acc.instance_url
# #         if crm == "zoho":
# #             api_base = (
# #                 j.get("api_domain")
# #                 or _zoho_api_base_from_accounts_server(accounts_server)
# #                 or _zoho_api_base_from_token_url(cfg["token_url"])
# #             )
# #             acc.instance_url = api_base

# #     # --- verify
# #     try:
# #         await _verify_and_fill_account(crm, acc)
# #     except HTTPException as e:
# #         if crm == "zoho":
# #             try:
# #                 async with httpx.AsyncClient(timeout=15.0) as client:
# #                     accounts_base = _zoho_accounts_from_api_base(acc.instance_url or _zoho_api_base_from_token_url(cfg["token_url"]))
# #                     zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
# #                     r = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
# #                     if r.status_code in (200, 204):
# #                         pass
# #                     else:
# #                         await acc.save()
# #                         await st.delete()
# #                         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
# #             except Exception:
# #                 await acc.save()
# #                 await st.delete()
# #                 return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
# #         else:
# #             await acc.save()
# #             await st.delete()
# #             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

# #     # --- IMPORTANT: reactivate on success
# #     acc.is_active = True  # <-- FIX: ensure account is active so /crm/accounts shows it
# #     await acc.save()
# #     await st.delete()
# #     return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# # # -------------------------
# # # API key flow (Close) + optional HubSpot PAT
# # # -------------------------
# # @router.post("/crm/token/{crm}")
# # async def set_token(
# #     crm: str,
# #     payload: Dict[str, str] = Body(..., example={"access_token": "xxxx"}),
# #     user: User = Depends(get_current_user),
# # ):
# #     crm = crm.lower()
# #     if crm not in SUPPORTED:
# #         raise HTTPException(400, "Unsupported CRM")

# #     if crm not in ("close", "hubspot"):
# #         raise HTTPException(400, "This endpoint is only for Close (and optional HubSpot PAT).")

# #     token = (payload.get("access_token") or "").strip()
# #     if not token:
# #         raise HTTPException(400, "access_token required.")

# #     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
# #     if not acc:
# #         acc = await IntegrationAccount.create(user=user, crm=crm)

# #     acc.access_token = token
# #     acc.refresh_token = None
# #     acc.expires_at = None  # API key / PAT do not expire in the OAuth sense

# #     await _verify_and_fill_account(crm, acc)

# #     acc.is_active = True  # <-- FIX: re-activate if it was previously disconnected
# #     await acc.save()

# #     return {"success": True, "message": f"{crm} token saved and verified."}

# # @router.delete("/crm/disconnect/{crm}")
# # async def disconnect(crm: str, user: User = Depends(get_current_user)):
# #     crm = crm.lower()
# #     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
# #     if not acc:
# #         raise HTTPException(404, "Not connected.")
# #     acc.is_active = False
# #     await acc.save()
# #     return {"success": True, "message": f"Disconnected {crm}."}

# # @router.post("/crm/ensure-fresh/{crm}")
# # async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
# #     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
# #     if not acc:
# #         raise HTTPException(404, "Not connected.")
# #     acc = await _ensure_fresh_token(crm.lower(), acc)
# #     return {"success": True, "expires_at": acc.expires_at}

# # # =========================
# # # Contacts & Leads fetchers
# # # =========================

# # async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
# #     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
# #     if not acc:
# #         raise HTTPException(404, f"Not connected to {crm}.")
# #     await _ensure_fresh_token(crm.lower(), acc)
# #     return acc

# # def _norm(
# #     id: str,
# #     name: Optional[str] = None,
# #     email: Optional[str] = None,
# #     phone: Optional[str] = None,
# #     company: Optional[str] = None,
# #     extra: Optional[Dict[str, Any]] = None,
# # ) -> Dict[str, Any]:
# #     return {
# #         "id": str(id) if id is not None else None,
# #         "name": (name or "") or None,
# #         "email": email,
# #         "phone": phone,
# #         "company": company,
# #         "raw": extra or {},
# #     }

# # @router.get("/crm/{crm}/contacts")
# # async def fetch_contacts(
# #     crm: str,
# #     user: User = Depends(get_current_user),
# #     limit: int = Query(25, ge=1, le=100),
# #     cursor: Optional[str] = Query(None, description="Leave empty for first page. HubSpot cursor is 'after' value returned from previous call."),
# #     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# # ):
# #     crm = crm.lower()
# #     if crm not in SUPPORTED:
# #         raise HTTPException(400, "Unsupported CRM")

# #     acc = await _get_active_account(user, crm)
# #     items: list = []
# #     next_cursor: Optional[str] = None
# #     raw_paging: Dict[str, Any] = {}

# #     async with httpx.AsyncClient(timeout=30.0) as client:
# #         if crm == "hubspot":
# #             params = {"limit": limit, "properties": "firstname,lastname,email,phone,company"}
# #             if cursor and str(cursor).lower() not in {"after", "none", "null"}:
# #                 params["after"] = cursor
# #             r = await client.get(
# #                 "https://api.hubapi.com/crm/v3/objects/contacts",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params=params,
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")
# #             j = r.json()
# #             for o in j.get("results", []):
# #                 p = o.get("properties", {}) or {}
# #                 name = (f"{p.get('firstname','')} {p.get('lastname','')}".strip() or p.get("email"))
# #                 items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("company"), o))
# #             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
# #             raw_paging = j.get("paging") or {}

# #         elif crm == "pipedrive":
# #             start = int(cursor) if cursor else 0
# #             r = await client.get(
# #                 "https://api.pipedrive.com/v1/persons",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params={"start": start, "limit": limit},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Pipedrive contacts fetch failed: {r.text}")
# #             j = r.json()
# #             for p in j.get("data") or []:
# #                 name = p.get("name")
# #                 email = None
# #                 phone = None
# #                 emails = p.get("email") or []
# #                 phones = p.get("phone") or []
# #                 if isinstance(emails, list) and emails:
# #                     email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]
# #                 if isinstance(phones, list) and phones:
# #                     phone = phones[0].get("value") if isinstance(phones[0], dict) else phones[0]
# #                 org = (p.get("org_id") or {}).get("name")
# #                 items.append(_norm(p.get("id"), name, email, phone, org, p))
# #             pag = ((j.get("additional_data") or {}).get("pagination") or {})
# #             raw_paging = pag
# #             if pag.get("more_items_in_collection"):
# #                 next_cursor = str(pag.get("next_start"))

# #         elif crm == "zoho":
# #             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
# #             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
# #             page_num = page or (int(cursor) if cursor else 1)
# #             r = await client.get(
# #                 f"{api_base}/crm/v2/Contacts",
# #                 headers=zheaders,
# #                 params={"page": page_num, "per_page": limit, "fields": "Full_Name,Email,Phone,Account_Name"},
# #             )
# #             if r.status_code not in (200, 204):
# #                 raise HTTPException(r.status_code, f"Zoho contacts fetch failed: {r.text}")
# #             j = r.json() if r.text else {}
# #             for c in j.get("data") or []:
# #                 name = c.get("Full_Name") or c.get("Full Name") or c.get("Name")
# #                 email = c.get("Email"); phone = c.get("Phone")
# #                 acct = (c.get("Account_Name") or {}).get("name") if isinstance(c.get("Account_Name"), dict) else None
# #                 items.append(_norm(c.get("id"), name, email, phone, acct, c))
# #             info = j.get("info") or {}
# #             raw_paging = info
# #             if info.get("more_records"):
# #                 next_cursor = str((info.get("page") or page_num) + 1)

# #         elif crm == "salesforce":
# #             base = (acc.instance_url or "").rstrip("/")
# #             r_versions = await client.get(
# #                 f"{base}/services/data/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #             )
# #             if not r_versions.is_success:
# #                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
# #             versions = r_versions.json()
# #             latest = versions[-1]["version"]
# #             offset = int(cursor) if cursor else 0
# #             soql = f"SELECT Id, Name, Email, Phone, Account.Name FROM Contact ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
# #             r = await client.get(
# #                 f"{base}/services/data/v{latest}/query",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params={"q": soql},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Salesforce contacts fetch failed: {r.text}")
# #             j = r.json()
# #             for row in j.get("records") or []:
# #                 acct = (row.get("Account") or {}).get("Name") if isinstance(row.get("Account"), dict) else None
# #                 items.append(_norm(row.get("Id"), row.get("Name"), row.get("Email"), row.get("Phone"), acct, row))
# #             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
# #             if not j.get("done"):
# #                 next_cursor = str(offset + limit)

# #         elif crm == "close":
# #             skip = int(cursor) if cursor else 0
# #             r = await client.get(
# #                 "https://api.close.com/api/v1/contact/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params={"_skip": skip, "_limit": limit},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Close contacts fetch failed: {r.text}")
# #             j = r.json()
# #             for c in j.get("data") or []:
# #                 name = c.get("name")
# #                 email = (c.get("emails") or [{}])[0].get("email") if (c.get("emails") or []) else None
# #                 phone = (c.get("phones") or [{}])[0].get("phone") if (c.get("phones") or []) else None
# #                 items.append(_norm(c.get("id"), name, email, phone, None, c))
# #             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
# #             if j.get("has_more"):
# #                 next_cursor = str(j.get("next") or (skip + limit))

# #         else:
# #             raise HTTPException(400, "Unsupported CRM")

# #     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# # @router.get("/crm/{crm}/leads")
# # async def fetch_leads(
# #     crm: str,
# #     user: User = Depends(get_current_user),
# #     limit: int = Query(25, ge=1, le=100),
# #     cursor: Optional[str] = Query(None),
# #     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# # ):
# #     """
# #     Unified 'leads' listing.
# #     Notes:
# #     - HubSpot: try Leads object first (requires crm.objects.leads.*). Fallback to Deals.
# #     - Pipedrive: try /leads first; fallback to /deals.
# #     - Close: 'Lead' = company; 'Contact' = person.
# #     """
# #     crm = crm.lower()
# #     if crm not in SUPPORTED:
# #         raise HTTPException(400, "Unsupported CRM")

# #     acc = await _get_active_account(user, crm)
# #     items: list = []
# #     next_cursor: Optional[str] = None
# #     raw_paging: Dict[str, Any] = {}

# #     async with httpx.AsyncClient(timeout=30.0) as client:
# #         if crm == "hubspot":
# #             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}

# #             async def _try_leads():
# #                 params = {"limit": limit, "properties": "hs_lead_status,createdate,firstname,lastname,email,phone,company"}
# #                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
# #                     params["after"] = cursor
# #                 return await client.get("https://api.hubapi.com/crm/v3/objects/leads", headers=headers, params=params)

# #             async def _try_deals():
# #                 params = {"limit": limit, "properties": "dealname,amount,dealstage,createdate,hs_lead_status"}
# #                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
# #                     params["after"] = cursor
# #                 return await client.get("https://api.hubapi.com/crm/v3/objects/deals", headers=headers, params=params)

# #             r = await _try_leads()
# #             if r.status_code in (404, 403):
# #                 r = await _try_deals()

# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"HubSpot leads/deals fetch failed: {r.text}")

# #             j = r.json()
# #             results = j.get("results") or []
# #             for d in results:
# #                 p = d.get("properties", {}) or {}
# #                 # best-effort name
# #                 name = p.get("dealname") or (f"{p.get('firstname','')} {p.get('lastname','')}".strip()) or p.get("email")
# #                 items.append(_norm(d.get("id"), name, p.get("email"), p.get("phone"), p.get("company"), d))
# #             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
# #             raw_paging = j.get("paging") or {}

# #         elif crm == "pipedrive":
# #             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}
# #             start = int(cursor) if cursor else 0

# #             async def _try_leads():
# #                 return await client.get("https://api.pipedrive.com/v1/leads", headers=headers, params={"start": start, "limit": limit})

# #             async def _try_deals():
# #                 return await client.get("https://api.pipedrive.com/v1/deals", headers=headers, params={"start": start, "limit": limit})

# #             r = await _try_leads()
# #             if r.status_code in (403, 404):
# #                 r = await _try_deals()
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Pipedrive leads/deals fetch failed: {r.text}")

# #             j = r.json()
# #             data = j.get("data") or []
# #             for d in data:
# #                 name = d.get("title") or d.get("deal_title") or d.get("org_name") or d.get("person_name")
# #                 items.append(_norm(d.get("id"), name, None, None, d.get("org_name"), d))
# #             pag = ((j.get("additional_data") or {}).get("pagination") or {})
# #             raw_paging = pag
# #             if pag.get("more_items_in_collection"):
# #                 next_cursor = str(pag.get("next_start"))

# #         elif crm == "zoho":
# #             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
# #             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
# #             page_num = page or (int(cursor) if cursor else 1)
# #             r = await client.get(
# #                 f"{api_base}/crm/v2/Leads",
# #                 headers=zheaders,
# #                 params={"page": page_num, "per_page": limit, "fields": "Company,Last_Name,First_Name,Email,Phone,Lead_Status"},
# #             )
# #             if r.status_code not in (200, 204):
# #                 raise HTTPException(r.status_code, f"Zoho leads fetch failed: {r.text}")
# #             j = r.json() if r.text else {}
# #             for l in j.get("data") or []:
# #                 name = (f"{l.get('First_Name','')} {l.get('Last_Name','')}".strip() or l.get("Company") or None)
# #                 items.append(_norm(l.get("id"), name, l.get("Email"), l.get("Phone"), l.get("Company"), l))
# #             info = j.get("info") or {}
# #             raw_paging = info
# #             if info.get("more_records"):
# #                 next_cursor = str((info.get("page") or page_num) + 1)

# #         elif crm == "salesforce":
# #             base = (acc.instance_url or "").rstrip("/")
# #             r_versions = await client.get(
# #                 f"{base}/services/data/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #             )
# #             if not r_versions.is_success:
# #                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
# #             versions = r_versions.json()
# #             latest = versions[-1]["version"]
# #             offset = int(cursor) if cursor else 0
# #             soql = f"SELECT Id, Company, FirstName, LastName, Email, Phone, Status FROM Lead ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
# #             r = await client.get(
# #                 f"{base}/services/data/v{latest}/query",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params={"q": soql},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Salesforce leads fetch failed: {r.text}")
# #             j = r.json()
# #             for row in j.get("records") or []:
# #                 name = (f"{row.get('FirstName','')} {row.get('LastName','')}".strip() or row.get("Company") or None)
# #                 items.append(_norm(row.get("Id"), name, row.get("Email"), row.get("Phone"), row.get("Company"), row))
# #             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
# #             if not j.get("done"):
# #                 next_cursor = str(offset + limit)

# #         elif crm == "close":
# #             skip = int(cursor) if cursor else 0
# #             r = await client.get(
# #                 "https://api.close.com/api/v1/lead/",
# #                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
# #                 params={"_skip": skip, "_limit": limit},
# #             )
# #             if not r.is_success:
# #                 raise HTTPException(r.status_code, f"Close leads fetch failed: {r.text}")
# #             j = r.json()
# #             for l in j.get("data") or []:
# #                 items.append(_norm(l.get("id"), l.get("name"), None, None, None, l))
# #             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
# #             if j.get("has_more"):
# #                 next_cursor = str(j.get("next") or (skip + limit))

# #         else:
# #             raise HTTPException(400, "Unsupported CRM")

# #     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}


























# import os
# import secrets
# from datetime import datetime, timedelta, timezone
# from typing import Optional, Dict, Any, List, Tuple
# from urllib.parse import urlparse, quote_plus

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query, Body
# from fastapi.responses import RedirectResponse, JSONResponse

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.crm import IntegrationAccount, IntegrationOAuthState
# # >>> NEW: we will create files and store leads
# from models.file import File as FileModel
# from models.lead import Lead

# router = APIRouter()

# # -------------------------
# # Provider config (OAuth app creds in env)
# # -------------------------
# def _cfg() -> Dict[str, Dict[str, str]]:
#     return {
#         "hubspot": {
#             "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
#             "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
#             "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
#             "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
#             # default includes contacts/deals/leads/lists + oauth
#             "scope": os.getenv(
#                 "HUBSPOT_SCOPES",
#                 "crm.objects.contacts.read crm.objects.contacts.write "
#                 "crm.objects.deals.read crm.objects.deals.write "
#                 "crm.objects.leads.read crm.objects.leads.write "
#                 "crm.lists.read crm.lists.write oauth"
#             ),
#             "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
#             "type": "oauth",
#         },
#         "salesforce": {
#             "auth_url": os.getenv("SALESFORCE_AUTH_URL", "https://login.salesforce.com/services/oauth2/authorize"),
#             "token_url": os.getenv("SALESFORCE_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token"),
#             "client_id": os.getenv("SALESFORCE_CLIENT_ID", ""),
#             "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", ""),
#             "scope": os.getenv("SALESFORCE_SCOPES", "api refresh_token"),
#             "type": "oauth",
#         },
#         "zoho": {
#             "auth_url": os.getenv("ZOHO_AUTH_URL", "https://accounts.zoho.com/oauth/v2/auth"),
#             "token_url": os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.com/oauth/v2/token"),
#             "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
#             "client_secret": os.getenv("ZOHO_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("ZOHO_REDIRECT_URI", ""),
#             # NOTE: multiple scopes are COMMA-separated for Zoho
#             "scope": os.getenv("ZOHO_SCOPES", "ZohoCRM.modules.ALL"),
#             "type": "oauth",
#         },
#         "pipedrive": {
#             "auth_url": os.getenv("PIPEDRIVE_AUTH_URL", "https://oauth.pipedrive.com/oauth/authorize"),
#             "token_url": os.getenv("PIPEDRIVE_TOKEN_URL", "https://oauth.pipedrive.com/oauth/token"),
#             "client_id": os.getenv("PIPEDRIVE_CLIENT_ID", ""),
#             "client_secret": os.getenv("PIPEDRIVE_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("PIPEDRIVE_REDIRECT_URI", ""),
#             # space-separated scopes for Pipedrive
#             "scope": os.getenv("PIPEDRIVE_SCOPES", "deals:full contacts:full"),
#             "type": "oauth",
#         },
#         "close": {
#             "type": "api_key",  # Close uses API key (Bearer)
#         },
#     }

# SUPPORTED = ("hubspot", "salesforce", "zoho", "pipedrive", "close")

# # -------------------------
# # Helpers
# # -------------------------
# def _now() -> datetime:
#     return datetime.now(timezone.utc)

# def _exp_from_seconds(seconds: int) -> datetime:
#     # pad a minute early
#     return _now() + timedelta(seconds=max(0, seconds - 60))

# def _sanitize_redirect(back: str) -> str:
#     """Prevent open-redirects: allow only same-site relative paths or whitelisted origins via env."""
#     if back and back.startswith("/") and not back.startswith("//"):
#         return back
#     allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
#     if back and allowed:
#         p = urlparse(back)
#         origin = f"{p.scheme}://{p.netloc}"
#         if origin in allowed:
#             return back
#     return "/integrations"

# # ---- Zoho DC helpers ----
# _ZOHO_ACCOUNTS_TO_API = {
#     "accounts.zoho.com": "https://www.zohoapis.com",
#     "accounts.zoho.eu": "https://www.zohoapis.eu",
#     "accounts.zoho.in": "https://www.zohoapis.in",
#     "accounts.zoho.com.au": "https://www.zohoapis.com.au",
#     "accounts.zoho.jp": "https://www.zohoapis.jp",
#     "accounts.zoho.uk": "https://www.zohoapis.uk",
# }
# _ZOHO_API_TO_ACCOUNTS = {
#     "www.zohoapis.com": "https://accounts.zoho.com",
#     "www.zohoapis.eu": "https://accounts.zoho.eu",
#     "www.zohoapis.in": "https://accounts.zoho.in",
#     "www.zohoapis.com.au": "https://accounts.zoho.com.au",
#     "www.zohoapis.jp": "https://accounts.zoho.jp",
#     "www.zohoapis.uk": "https://accounts.zoho.uk",
# }

# def _zoho_api_base_from_accounts_server(accounts_server: Optional[str]) -> Optional[str]:
#     if not accounts_server:
#         return None
#     try:
#         host = urlparse(accounts_server).netloc or accounts_server
#         return _ZOHO_ACCOUNTS_TO_API.get(host)
#     except Exception:
#         return None

# def _zoho_api_base_from_token_url(token_url: str) -> str:
#     try:
#         host = urlparse(token_url).netloc
#         return _ZOHO_ACCOUNTS_TO_API.get(host, "https://www.zohoapis.com")
#     except Exception:
#         return "https://www.zohoapis.com"

# def _zoho_accounts_from_api_base(api_base: str) -> str:
#     host = urlparse(api_base).netloc
#     return _ZOHO_API_TO_ACCOUNTS.get(host, "https://accounts.zoho.com")

# # -------------------------
# # Token verification
# # -------------------------
# async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
#     """
#     Make a tiny test call to confirm access token works and fill org info if possible.
#     Relaxed for Zoho: if Accounts token is valid but CRM probes fail (new org), we still accept.
#     """
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             url = f"{_cfg()['hubspot']['verify_url'].rstrip('/')}/{acc.access_token}"
#             r = await client.get(url, headers={"Accept": "application/json"})
#             if r.is_success:
#                 j = r.json()
#                 acc.external_account_id = str(j.get("hub_id") or j.get("hubId") or "")
#                 u = j.get("user")
#                 if isinstance(u, str):
#                     acc.external_account_name = u
#                 elif isinstance(u, dict):
#                     acc.external_account_name = u.get("email") or u.get("name") or None
#                 else:
#                     acc.external_account_name = None
#             else:
#                 # Fallback trivial call (also works for PAT)
#                 r2 = await client.get(
#                     "https://api.hubapi.com/crm/v3/owners?limit=1",
#                     headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 )
#                 if not r2.is_success:
#                     raise HTTPException(401, "HubSpot token validation failed.")

#         elif crm == "salesforce":
#             base = acc.instance_url or ""
#             if not base:
#                 raise HTTPException(400, "Salesforce instance_url missing.")
#             r = await client.get(
#                 f"{base.rstrip('/')}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Salesforce token validation failed.")

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()['zoho']['token_url'])).rstrip("/")
#             accounts_base = _zoho_accounts_from_api_base(api_base)
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}

#             r_acc = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
#             if r_acc.status_code not in (200, 204):
#                 raise HTTPException(401, f"Zoho accounts verify {r_acc.status_code}: {(r_acc.text or '')[:300]}")
#             try:
#                 info = r_acc.json()
#                 acc.external_account_name = info.get("Email") or info.get("email") or acc.external_account_name
#             except Exception:
#                 pass

#             endpoints = [
#                 "/crm/v2/Contacts?fields=id&per_page=1",
#                 "/crm/v2/Leads?fields=id&per_page=1",
#                 "/crm/v2/settings/modules?per_page=1",
#             ]
#             ok = False
#             for ep in endpoints:
#                 r = await client.get(f"{api_base}{ep}", headers=zheaders)
#                 if r.status_code in (200, 204):
#                     ok = True
#                     break
#             if not ok:
#                 acc.external_account_id = acc.external_account_id or ""

#         elif crm == "pipedrive":
#             r = await client.get(
#                 "https://api.pipedrive.com/v1/users/me",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Pipedrive token validation failed.")
#             j = r.json().get("data") or {}
#             acc.external_account_id = str(j.get("company_id") or "")
#             acc.external_account_name = j.get("company_name") or None

#         elif crm == "close":
#             r = await client.get(
#                 "https://api.close.com/api/v1/me/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Close API key invalid.")
#             j = r.json()
#             acc.external_account_id = str(j.get("organization_id") or "")
#             acc.external_account_name = (j.get("organization") or {}).get("name")

# # -------------------------
# # Refresh tokens
# # -------------------------
# async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
#     if crm == "close":
#         return acc

#     SKEW_SECONDS = 120
#     if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
#         return acc

#     cfg = _cfg()[crm]
#     if not acc.refresh_token:
#         return acc

#     data: Dict[str, Any] = {"grant_type": "refresh_token", "refresh_token": acc.refresh_token}
#     if crm in ("hubspot", "pipedrive", "zoho", "salesforce"):
#         data["client_id"] = cfg["client_id"]
#         data["client_secret"] = cfg["client_secret"]

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             raise HTTPException(401, f"{crm} refresh failed: {r.text}")
#         j = r.json()

#     # normalize expires_in to int
#     def _get_exp(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     if crm == "salesforce":
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#         acc.instance_url = j.get("instance_url") or acc.instance_url
#         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#     else:
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#         if crm == "pipedrive":
#             acc.instance_url = j.get("api_domain") or acc.instance_url
#         if crm == "zoho":
#             acc.instance_url = j.get("api_domain") or acc.instance_url

#     await acc.save()
#     return acc

# # -------------------------
# # Public routes
# # -------------------------
# @router.get("/crm/providers")
# async def list_providers():
#     cfg = _cfg()
#     out = []
#     for name in SUPPORTED:
#         c = cfg.get(name, {})
#         out.append({
#             "name": name,
#             "type": c.get("type", "oauth"),
#             "scopes": c.get("scope"),
#             "has_oauth": c.get("type") == "oauth",
#             "has_api_key": name == "close",
#         })
#     return out

# @router.get("/crm/accounts")
# async def list_accounts(user: User = Depends(get_current_user)):
#     rows = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
#     return [
#         {
#             "crm": r.crm,
#             "label": r.label,
#             "external_account_id": r.external_account_id,
#             "external_account_name": r.external_account_name,
#             "connected_at": r.created_at,
#             "expires_at": r.expires_at,
#         } for r in rows
#     ]

# @router.post("/crm/connect/{crm}")
# async def start_connect(
#     crm: str,
#     user: User = Depends(get_current_user),
#     redirect_to: Optional[str] = Body(default="/integrations", embed=True),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     if crm == "close":
#         raise HTTPException(400, "Close uses API key. Call POST /crm/token/close.")

#     cfg = _cfg()[crm]
#     if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
#         raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

#     state = secrets.token_urlsafe(24)
#     await IntegrationOAuthState.create(
#         user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/integrations")
#     )

#     if crm == "hubspot":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "scope": cfg["scope"],
#             "state": state,
#             "response_type": "code",
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "salesforce":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "zoho":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "access_type": "offline",
#             "scope": cfg["scope"],
#             "prompt": "consent",
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "pipedrive":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
#     else:
#         raise HTTPException(400, "Unsupported CRM")

#     return {"auth_url": auth_url}

# @router.get("/crm/callback/{crm}")
# async def oauth_callback(
#     crm: str,
#     code: Optional[str] = Query(None),
#     state: Optional[str] = Query(None),
#     error: Optional[str] = Query(None),
#     accounts_server: Optional[str] = Query(None, alias="accounts-server"),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED or crm == "close":
#         return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

#     st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
#     if not st:
#         return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

#     back = _sanitize_redirect(st.redirect_to or "/integrations")
#     cfg = _cfg()[crm]

#     if error:
#         await st.delete()
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

#     if not code:
#         await st.delete()
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

#     data = {
#         "grant_type": "authorization_code",
#         "code": code,
#         "redirect_uri": cfg["redirect_uri"],
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             await st.delete()
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")
#         j = r.json()

#     acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

#     # --- store tokens / instance data
#     def _as_int(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     if crm == "salesforce":
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.instance_url = j.get("instance_url") or acc.instance_url
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#     else:
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#         if crm == "pipedrive":
#             acc.instance_url = j.get("api_domain") or acc.instance_url
#         if crm == "zoho":
#             api_base = (
#                 j.get("api_domain")
#                 or _zoho_api_base_from_accounts_server(accounts_server)
#                 or _zoho_api_base_from_token_url(cfg["token_url"])
#             )
#             acc.instance_url = api_base

#     # --- verify
#     try:
#         await _verify_and_fill_account(crm, acc)
#     except HTTPException as e:
#         if crm == "zoho":
#             try:
#                 async with httpx.AsyncClient(timeout=15.0) as client:
#                     accounts_base = _zoho_accounts_from_api_base(acc.instance_url or _zoho_api_base_from_token_url(cfg["token_url"]))
#                     zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#                     r = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
#                     if r.status_code in (200, 204):
#                         pass
#                     else:
#                         await acc.save()
#                         await st.delete()
#                         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
#             except Exception:
#                 await acc.save()
#                 await st.delete()
#                 return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
#         else:
#             await acc.save()
#             await st.delete()
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

#     # --- IMPORTANT: reactivate on success
#     acc.is_active = True  # ensure account is active so /crm/accounts shows it
#     await acc.save()
#     await st.delete()
#     return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# # -------------------------
# # API key flow (Close) + optional HubSpot PAT
# # -------------------------
# @router.post("/crm/token/{crm}")
# async def set_token(
#     crm: str,
#     payload: Dict[str, str] = Body(..., example={"access_token": "xxxx"}),
#     user: User = Depends(get_current_user),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     if crm not in ("close", "hubspot"):
#         raise HTTPException(400, "This endpoint is only for Close (and optional HubSpot PAT).")

#     token = (payload.get("access_token") or "").strip()
#     if not token:
#         raise HTTPException(400, "access_token required.")

#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user=user, crm=crm)

#     acc.access_token = token
#     acc.refresh_token = None
#     acc.expires_at = None  # API key / PAT do not expire in the OAuth sense

#     await _verify_and_fill_account(crm, acc)

#     acc.is_active = True  # re-activate if it was previously disconnected
#     await acc.save()

#     return {"success": True, "message": f"{crm} token saved and verified."}

# @router.delete("/crm/disconnect/{crm}")
# async def disconnect(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc.is_active = False
#     await acc.save()
#     return {"success": True, "message": f"Disconnected {crm}."}

# @router.post("/crm/ensure-fresh/{crm}")
# async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc = await _ensure_fresh_token(crm.lower(), acc)
#     return {"success": True, "expires_at": acc.expires_at}

# # =========================
# # Contacts & Leads fetchers
# # =========================

# async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")
#     await _ensure_fresh_token(crm.lower(), acc)
#     return acc

# def _norm(
#     id: str,
#     name: Optional[str] = None,
#     email: Optional[str] = None,
#     phone: Optional[str] = None,
#     company: Optional[str] = None,
#     extra: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     return {
#         "id": str(id) if id is not None else None,
#         "name": (name or "") or None,
#         "email": email,
#         "phone": phone,
#         "company": company,
#         "raw": extra or {},
#     }

# @router.get("/crm/{crm}/contacts")
# async def fetch_contacts(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None, description="Leave empty for first page. HubSpot cursor is 'after' value returned from previous call."),
#     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     acc = await _get_active_account(user, crm)
#     items: list = []
#     next_cursor: Optional[str] = None
#     raw_paging: Dict[str, Any] = {}

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             params = {"limit": limit, "properties": "firstname,lastname,email,phone,company"}
#             if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                 params["after"] = cursor
#             r = await client.get(
#                 "https://api.hubapi.com/crm/v3/objects/contacts",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params=params,
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")
#             j = r.json()
#             for o in j.get("results", []):
#                 p = o.get("properties", {}) or {}
#                 name = (f"{p.get('firstname','')} {p.get('lastname','')}".strip() or p.get("email"))
#                 items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("company"), o))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "pipedrive":
#             start = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.pipedrive.com/v1/persons",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"start": start, "limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Pipedrive contacts fetch failed: {r.text}")
#             j = r.json()
#             for p in j.get("data") or []:
#                 name = p.get("name")
#                 email = None
#                 phone = None
#                 emails = p.get("email") or []
#                 phones = p.get("phone") or []
#                 if isinstance(emails, list) and emails:
#                     email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]
#                 if isinstance(phones, list) and phones:
#                     phone = phones[0].get("value") if isinstance(phones[0], dict) else phones[0]
#                 org = (p.get("org_id") or {}).get("name")
#                 items.append(_norm(p.get("id"), name, email, phone, org, p))
#             pag = ((j.get("additional_data") or {}).get("pagination") or {})
#             raw_paging = pag
#             if pag.get("more_items_in_collection"):
#                 next_cursor = str(pag.get("next_start"))

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#             page_num = page or (int(cursor) if cursor else 1)
#             r = await client.get(
#                 f"{api_base}/crm/v2/Contacts",
#                 headers=zheaders,
#                 params={"page": page_num, "per_page": limit, "fields": "Full_Name,Email,Phone,Account_Name"},
#             )
#             if r.status_code not in (200, 204):
#                 raise HTTPException(r.status_code, f"Zoho contacts fetch failed: {r.text}")
#             j = r.json() if r.text else {}
#             for c in j.get("data") or []:
#                 name = c.get("Full_Name") or c.get("Full Name") or c.get("Name")
#                 email = c.get("Email"); phone = c.get("Phone")
#                 acct = (c.get("Account_Name") or {}).get("name") if isinstance(c.get("Account_Name"), dict) else None
#                 items.append(_norm(c.get("id"), name, email, phone, acct, c))
#             info = j.get("info") or {}
#             raw_paging = info
#             if info.get("more_records"):
#                 next_cursor = str((info.get("page") or page_num) + 1)

#         elif crm == "salesforce":
#             base = (acc.instance_url or "").rstrip("/")
#             r_versions = await client.get(
#                 f"{base}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r_versions.is_success:
#                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
#             versions = r_versions.json()
#             latest = versions[-1]["version"]
#             offset = int(cursor) if cursor else 0
#             soql = f"SELECT Id, Name, Email, Phone, Account.Name FROM Contact ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
#             r = await client.get(
#                 f"{base}/services/data/v{latest}/query",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"q": soql},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Salesforce contacts fetch failed: {r.text}")
#             j = r.json()
#             for row in j.get("records") or []:
#                 acct = (row.get("Account") or {}).get("Name") if isinstance(row.get("Account"), dict) else None
#                 items.append(_norm(row.get("Id"), row.get("Name"), row.get("Email"), row.get("Phone"), acct, row))
#             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
#             if not j.get("done"):
#                 next_cursor = str(offset + limit)

#         elif crm == "close":
#             skip = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.close.com/api/v1/contact/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"_skip": skip, "_limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Close contacts fetch failed: {r.text}")
#             j = r.json()
#             for c in j.get("data") or []:
#                 name = c.get("name")
#                 email = (c.get("emails") or [{}])[0].get("email") if (c.get("emails") or []) else None
#                 phone = (c.get("phones") or [{}])[0].get("phone") if (c.get("phones") or []) else None
#                 items.append(_norm(c.get("id"), name, email, phone, None, c))
#             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
#             if j.get("has_more"):
#                 next_cursor = str(j.get("next") or (skip + limit))

#         else:
#             raise HTTPException(400, "Unsupported CRM")

#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# @router.get("/crm/{crm}/leads")
# async def fetch_leads(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None),
#     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# ):
#     """
#     Unified 'leads' listing.
#     Notes:
#     - HubSpot: try Leads object first (requires crm.objects.leads.*). Fallback to Deals.
#     - Pipedrive: try /leads first; fallback to /deals.
#     - Close: 'Lead' = company; 'Contact' = person.
#     """
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     acc = await _get_active_account(user, crm)
#     items: list = []
#     next_cursor: Optional[str] = None
#     raw_paging: Dict[str, Any] = {}

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}

#             async def _try_leads():
#                 params = {"limit": limit, "properties": "hs_lead_status,createdate,firstname,lastname,email,phone,company"}
#                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                     params["after"] = cursor
#                 return await client.get("https://api.hubapi.com/crm/v3/objects/leads", headers=headers, params=params)

#             async def _try_deals():
#                 params = {"limit": limit, "properties": "dealname,amount,dealstage,createdate,hs_lead_status"}
#                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                     params["after"] = cursor
#                 return await client.get("https://api.hubapi.com/crm/v3/objects/deals", headers=headers, params=params)

#             r = await _try_leads()
#             if r.status_code in (404, 403):
#                 r = await _try_deals()

#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"HubSpot leads/deals fetch failed: {r.text}")

#             j = r.json()
#             results = j.get("results") or []
#             for d in results:
#                 p = d.get("properties", {}) or {}
#                 # best-effort name
#                 name = p.get("dealname") or (f"{p.get('firstname','')} {p.get('lastname','')}".strip()) or p.get("email")
#                 items.append(_norm(d.get("id"), name, p.get("Email") or p.get("email"), p.get("phone"), p.get("company"), d))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "pipedrive":
#             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}
#             start = int(cursor) if cursor else 0

#             async def _try_leads():
#                 return await client.get("https://api.pipedrive.com/v1/leads", headers=headers, params={"start": start, "limit": limit})

#             async def _try_deals():
#                 return await client.get("https://api.pipedrive.com/v1/deals", headers=headers, params={"start": start, "limit": limit})

#             r = await _try_leads()
#             if r.status_code in (403, 404):
#                 r = await _try_deals()
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Pipedrive leads/deals fetch failed: {r.text}")

#             j = r.json()
#             data = j.get("data") or []
#             for d in data:
#                 name = d.get("title") or d.get("deal_title") or d.get("org_name") or d.get("person_name")
#                 items.append(_norm(d.get("id"), name, None, None, d.get("org_name"), d))
#             pag = ((j.get("additional_data") or {}).get("pagination") or {})
#             raw_paging = pag
#             if pag.get("more_items_in_collection"):
#                 next_cursor = str(pag.get("next_start"))

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#             page_num = page or (int(cursor) if cursor else 1)
#             r = await client.get(
#                 f"{api_base}/crm/v2/Leads",
#                 headers=zheaders,
#                 params={"page": page_num, "per_page": limit, "fields": "Company,Last_Name,First_Name,Email,Phone,Lead_Status"},
#             )
#             if r.status_code not in (200, 204):
#                 raise HTTPException(r.status_code, f"Zoho leads fetch failed: {r.text}")
#             j = r.json() if r.text else {}
#             for l in j.get("data") or []:
#                 name = (f"{l.get('First_Name','')} {l.get('Last_Name','')}".strip() or l.get("Company") or None)
#                 items.append(_norm(l.get("id"), name, l.get("Email"), l.get("Phone"), l.get("Company"), l))
#             info = j.get("info") or {}
#             raw_paging = info
#             if info.get("more_records"):
#                 next_cursor = str((info.get("page") or page_num) + 1)

#         elif crm == "salesforce":
#             base = (acc.instance_url or "").rstrip("/")
#             r_versions = await client.get(
#                 f"{base}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r_versions.is_success:
#                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
#             versions = r_versions.json()
#             latest = versions[-1]["version"]
#             offset = int(cursor) if cursor else 0
#             soql = f"SELECT Id, Company, FirstName, LastName, Email, Phone, Status FROM Lead ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
#             r = await client.get(
#                 f"{base}/services/data/v{latest}/query",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"q": soql},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Salesforce leads fetch failed: {r.text}")
#             j = r.json()
#             for row in j.get("records") or []:
#                 name = (f"{row.get('FirstName','')} {row.get('LastName','')}".strip() or row.get("Company") or None)
#                 items.append(_norm(row.get("Id"), name, row.get("Email"), row.get("Phone"), row.get("Company"), row))
#             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
#             if not j.get("done"):
#                 next_cursor = str(offset + limit)

#         elif crm == "close":
#             skip = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.close.com/api/v1/lead/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"_skip": skip, "_limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Close leads fetch failed: {r.text}")
#             j = r.json()
#             for l in j.get("data") or []:
#                 items.append(_norm(l.get("id"), l.get("name"), None, None, None, l))
#             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
#             if j.get("has_more"):
#                 next_cursor = str(j.get("next") or (skip + limit))

#         else:
#             raise HTTPException(400, "Unsupported CRM")

#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# # ================
# # NEW: Bulk sync -> auto create files and import leads/contacts
# # ================

# def _split_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
#     if not full_name:
#         return None, None
#     parts = (full_name or "").strip().split()
#     if not parts:
#         return None, None
#     if len(parts) == 1:
#         return parts[0], None
#     return parts[0], " ".join(parts[1:])

# def _clean_phone(phone: Optional[str]) -> Optional[str]:
#     if not phone:
#         return None
#     digits = "".join(ch for ch in str(phone) if ch.isdigit())
#     return digits or None

# async def _fetch_all_items(user: User, crm: str, mode: str) -> List[Dict[str, Any]]:
#     """Use our own endpoints to page through ALL items."""
#     items: List[Dict[str, Any]] = []
#     cursor: Optional[str] = None
#     while True:
#         if mode == "contacts":
#             page = await fetch_contacts(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
#         else:
#             page = await fetch_leads(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
#         batch = page.get("items") or []
#         items.extend(batch)
#         nxt = page.get("next_cursor")
#         if not nxt:
#             break
#         cursor = str(nxt)
#     return items

# async def _ensure_file(user: User, name: str) -> FileModel:
#     file = await FileModel.get_or_none(user_id=user.id, name=name)
#     if not file:
#         file = FileModel(name=name, user=user)
#         await file.save()
#     return file

# async def _upsert_lead_from_item(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
#     """
#     Returns (created, updated)
#     We map our normalized item -> Lead model.
#     """
#     full_name = item.get("name")
#     first, last = _split_name(full_name)
#     email = item.get("email")
#     phone = _clean_phone(item.get("phone"))
#     external_id = item.get("id")  # stored in salesforce_id field (generic external id)
#     company = item.get("company")

#     # Check existing by file + external id
#     existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
#     payload = {
#         "first_name": first or "",
#         "last_name": last or "",
#         "email": email,
#         "mobile": phone,
#         "salesforce_id": external_id,
#         "add_date": datetime.now(),
#         "other_data": {
#             "Custom_0": company or "",
#             "Custom_1": f"source:{crm}"
#         }
#     }

#     if existing:
#         # Update basic fields if changed
#         changed = False
#         for k, v in payload.items():
#             if getattr(existing, k, None) != v:
#                 setattr(existing, k, v)
#                 changed = True
#         if existing.file_id != file.id:
#             existing.file = file
#             changed = True
#         if changed:
#             await existing.save()
#             return (False, True)
#         return (False, False)
#     else:
#         new = Lead(file=file, **payload)
#         await new.save()
#         return (True, False)

# @router.post("/crm/sync-to-files")
# async def sync_connected_crms_to_files(
#     user: User = Depends(get_current_user),
#     crm: Optional[str] = Query(None, description="If provided, only sync this CRM (hubspot, salesforce, zoho, pipedrive, close)"),
#     mode: str = Query("leads", pattern="^(leads|contacts)$", description="What to import into the file")
# ):
#     """
#     For each connected CRM:
#       - Ensure a file exists named '<CRM> Leads' (or 'Contacts')
#       - Fetch ALL pages from that CRM
#       - Upsert into the file (no duplicates on rerun)
#     """
#     # Which CRMs to run
#     connected = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
#     if crm:
#         crm = crm.lower()
#         connected = [a for a in connected if a.crm == crm]
#         if not connected:
#             raise HTTPException(404, f"Not connected to {crm}.")
#     if not connected:
#         return {"success": True, "ran": 0, "details": []}

#     results = []
#     for acc in connected:
#         label = acc.crm.capitalize()
#         file_name = f"{label} {mode.capitalize()}"  # e.g. "HubSpot Leads"
#         file = await _ensure_file(user, file_name)

#         try:
#             items = await _fetch_all_items(user, acc.crm, mode)
#             created = 0
#             updated = 0
#             for it in items:
#                 c, u = await _upsert_lead_from_item(file, it, acc.crm)
#                 created += 1 if c else 0
#                 updated += 1 if u else 0

#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "fetched": len(items),
#                 "created": created,
#                 "updated": updated,
#             })
#         except HTTPException as e:
#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "error": str(e.detail),
#             })
#         except Exception as e:
#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "error": str(e),
#             })

#     return {"success": True, "ran": len(connected), "details": results}



















# import os
# import secrets
# from datetime import datetime, timedelta, timezone
# from typing import Optional, Dict, Any, List, Tuple
# from urllib.parse import urlparse, quote_plus

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query, Body
# from fastapi.responses import RedirectResponse, JSONResponse

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.crm import IntegrationAccount, IntegrationOAuthState
# # >>> NEW: we will create files and store leads
# from models.file import File as FileModel
# from models.lead import Lead

# router = APIRouter()

# # -------------------------
# # Provider config (OAuth app creds in env)
# # -------------------------
# def _cfg() -> Dict[str, Dict[str, str]]:
#     return {
#         "hubspot": {
#             "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
#             "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
#             "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
#             "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
#             # default includes contacts/deals/leads/lists + oauth
#             "scope": os.getenv(
#                 "HUBSPOT_SCOPES",
#                 "crm.objects.contacts.read crm.objects.contacts.write "
#                 "crm.objects.deals.read crm.objects.deals.write "
#                 "crm.objects.leads.read crm.objects.leads.write "
#                 "crm.lists.read crm.lists.write oauth"
#             ),
#             "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
#             "type": "oauth",
#         },
#         "salesforce": {
#             "auth_url": os.getenv("SALESFORCE_AUTH_URL", "https://login.salesforce.com/services/oauth2/authorize"),
#             "token_url": os.getenv("SALESFORCE_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token"),
#             "client_id": os.getenv("SALESFORCE_CLIENT_ID", ""),
#             "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", ""),
#             "scope": os.getenv("SALESFORCE_SCOPES", "api refresh_token"),
#             "type": "oauth",
#         },
#         "zoho": {
#             "auth_url": os.getenv("ZOHO_AUTH_URL", "https://accounts.zoho.com/oauth/v2/auth"),
#             "token_url": os.getenv("ZOHO_TOKEN_URL", "https://accounts.zoho.com/oauth/v2/token"),
#             "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
#             "client_secret": os.getenv("ZOHO_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("ZOHO_REDIRECT_URI", ""),
#             # NOTE: multiple scopes are COMMA-separated for Zoho
#             "scope": os.getenv("ZOHO_SCOPES", "ZohoCRM.modules.ALL"),
#             "type": "oauth",
#         },
#         "pipedrive": {
#             "auth_url": os.getenv("PIPEDRIVE_AUTH_URL", "https://oauth.pipedrive.com/oauth/authorize"),
#             "token_url": os.getenv("PIPEDRIVE_TOKEN_URL", "https://oauth.pipedrive.com/oauth/token"),
#             "client_id": os.getenv("PIPEDRIVE_CLIENT_ID", ""),
#             "client_secret": os.getenv("PIPEDRIVE_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("PIPEDRIVE_REDIRECT_URI", ""),
#             # space-separated scopes for Pipedrive
#             "scope": os.getenv("PIPEDRIVE_SCOPES", "deals:full contacts:full"),
#             "type": "oauth",
#         },
#         "close": {
#             "type": "api_key",  # Close uses API key (Bearer)
#         },
#     }

# SUPPORTED = ("hubspot", "salesforce", "zoho", "pipedrive", "close")

# # -------------------------
# # Helpers
# # -------------------------
# def _now() -> datetime:
#     return datetime.now(timezone.utc)

# def _exp_from_seconds(seconds: int) -> datetime:
#     # pad a minute early
#     return _now() + timedelta(seconds=max(0, seconds - 60))

# def _sanitize_redirect(back: str) -> str:
#     """Prevent open-redirects: allow only same-site relative paths or whitelisted origins via env."""
#     if back and back.startswith("/") and not back.startswith("//"):
#         return back
#     allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
#     if back and allowed:
#         p = urlparse(back)
#         origin = f"{p.scheme}://{p.netloc}"
#         if origin in allowed:
#             return back
#     return "/integrations"

# # ---- Zoho DC helpers ----
# _ZOHO_ACCOUNTS_TO_API = {
#     "accounts.zoho.com": "https://www.zohoapis.com",
#     "accounts.zoho.eu": "https://www.zohoapis.eu",
#     "accounts.zoho.in": "https://www.zohoapis.in",
#     "accounts.zoho.com.au": "https://www.zohoapis.com.au",
#     "accounts.zoho.jp": "https://www.zohoapis.jp",
#     "accounts.zoho.uk": "https://www.zohoapis.uk",
# }
# _ZOHO_API_TO_ACCOUNTS = {
#     "www.zohoapis.com": "https://accounts.zoho.com",
#     "www.zohoapis.eu": "https://accounts.zoho.eu",
#     "www.zohoapis.in": "https://accounts.zoho.in",
#     "www.zohoapis.com.au": "https://accounts.zoho.com.au",
#     "www.zohoapis.jp": "https://accounts.zoho.jp",
#     "www.zohoapis.uk": "https://accounts.zoho.uk",
# }

# def _zoho_api_base_from_accounts_server(accounts_server: Optional[str]) -> Optional[str]:
#     if not accounts_server:
#         return None
#     try:
#         host = urlparse(accounts_server).netloc or accounts_server
#         return _ZOHO_ACCOUNTS_TO_API.get(host)
#     except Exception:
#         return None

# def _zoho_api_base_from_token_url(token_url: str) -> str:
#     try:
#         host = urlparse(token_url).netloc
#         return _ZOHO_ACCOUNTS_TO_API.get(host, "https://www.zohoapis.com")
#     except Exception:
#         return "https://www.zohoapis.com"

# def _zoho_accounts_from_api_base(api_base: str) -> str:
#     host = urlparse(api_base).netloc
#     return _ZOHO_API_TO_ACCOUNTS.get(host, "https://accounts.zoho.com")

# # -------------------------
# # Token verification
# # -------------------------
# async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
#     """
#     Make a tiny test call to confirm access token works and fill org info if possible.
#     Relaxed for Zoho: if Accounts token is valid but CRM probes fail (new org), we still accept.
#     """
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             url = f"{_cfg()['hubspot']['verify_url'].rstrip('/')}/{acc.access_token}"
#             r = await client.get(url, headers={"Accept": "application/json"})
#             if r.is_success:
#                 j = r.json()
#                 acc.external_account_id = str(j.get("hub_id") or j.get("hubId") or "")
#                 u = j.get("user")
#                 if isinstance(u, str):
#                     acc.external_account_name = u
#                 elif isinstance(u, dict):
#                     acc.external_account_name = u.get("email") or u.get("name") or None
#                 else:
#                     acc.external_account_name = None
#             else:
#                 # Fallback trivial call (also works for PAT)
#                 r2 = await client.get(
#                     "https://api.hubapi.com/crm/v3/owners?limit=1",
#                     headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 )
#                 if not r2.is_success:
#                     raise HTTPException(401, "HubSpot token validation failed.")

#         elif crm == "salesforce":
#             base = acc.instance_url or ""
#             if not base:
#                 raise HTTPException(400, "Salesforce instance_url missing.")
#             r = await client.get(
#                 f"{base.rstrip('/')}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Salesforce token validation failed.")

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()['zoho']['token_url'])).rstrip("/")
#             accounts_base = _zoho_accounts_from_api_base(api_base)
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}

#             r_acc = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
#             if r_acc.status_code not in (200, 204):
#                 raise HTTPException(401, f"Zoho accounts verify {r_acc.status_code}: {(r_acc.text or '')[:300]}")
#             try:
#                 info = r_acc.json()
#                 acc.external_account_name = info.get("Email") or info.get("email") or acc.external_account_name
#             except Exception:
#                 pass

#             endpoints = [
#                 "/crm/v2/Contacts?fields=id&per_page=1",
#                 "/crm/v2/Leads?fields=id&per_page=1",
#                 "/crm/v2/settings/modules?per_page=1",
#             ]
#             ok = False
#             for ep in endpoints:
#                 r = await client.get(f"{api_base}{ep}", headers=zheaders)
#                 if r.status_code in (200, 204):
#                     ok = True
#                     break
#             if not ok:
#                 acc.external_account_id = acc.external_account_id or ""

#         elif crm == "pipedrive":
#             r = await client.get(
#                 "https://api.pipedrive.com/v1/users/me",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Pipedrive token validation failed.")
#             j = r.json().get("data") or {}
#             acc.external_account_id = str(j.get("company_id") or "")
#             acc.external_account_name = j.get("company_name") or None

#         elif crm == "close":
#             r = await client.get(
#                 "https://api.close.com/api/v1/me/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 raise HTTPException(401, "Close API key invalid.")
#             j = r.json()
#             acc.external_account_id = str(j.get("organization_id") or "")
#             acc.external_account_name = (j.get("organization") or {}).get("name")

# # -------------------------
# # Refresh tokens
# # -------------------------
# async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
#     if crm == "close":
#         return acc

#     SKEW_SECONDS = 120
#     if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
#         return acc

#     cfg = _cfg()[crm]
#     if not acc.refresh_token:
#         return acc

#     data: Dict[str, Any] = {"grant_type": "refresh_token", "refresh_token": acc.refresh_token}
#     if crm in ("hubspot", "pipedrive", "zoho", "salesforce"):
#         data["client_id"] = cfg["client_id"]
#         data["client_secret"] = cfg["client_secret"]

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             raise HTTPException(401, f"{crm} refresh failed: {r.text}")
#         j = r.json()

#     # normalize expires_in to int
#     def _get_exp(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     if crm == "salesforce":
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#         acc.instance_url = j.get("instance_url") or acc.instance_url
#         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#     else:
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#         acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#         if crm == "pipedrive":
#             acc.instance_url = j.get("api_domain") or acc.instance_url
#         if crm == "zoho":
#             acc.instance_url = j.get("api_domain") or acc.instance_url

#     await acc.save()
#     return acc

# # -------------------------
# # Public routes
# # -------------------------
# @router.get("/crm/providers")
# async def list_providers():
#     cfg = _cfg()
#     out = []
#     for name in SUPPORTED:
#         c = cfg.get(name, {})
#         out.append({
#             "name": name,
#             "type": c.get("type", "oauth"),
#             "scopes": c.get("scope"),
#             "has_oauth": c.get("type") == "oauth",
#             "has_api_key": name == "close",
#         })
#     return out

# @router.get("/crm/accounts")
# async def list_accounts(user: User = Depends(get_current_user)):
#     rows = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
#     return [
#         {
#             "crm": r.crm,
#             "label": r.label,
#             "external_account_id": r.external_account_id,
#             "external_account_name": r.external_account_name,
#             "connected_at": r.created_at,
#             "expires_at": r.expires_at,
#         } for r in rows
#     ]

# @router.post("/crm/connect/{crm}")
# async def start_connect(
#     crm: str,
#     user: User = Depends(get_current_user),
#     redirect_to: Optional[str] = Body(default="/integrations", embed=True),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     if crm == "close":
#         raise HTTPException(400, "Close uses API key. Call POST /crm/token/close.")

#     cfg = _cfg()[crm]
#     if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
#         raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

#     state = secrets.token_urlsafe(24)
#     await IntegrationOAuthState.create(
#         user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/integrations")
#     )

#     if crm == "hubspot":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "scope": cfg["scope"],
#             "state": state,
#             "response_type": "code",
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "salesforce":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "zoho":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "access_type": "offline",
#             "scope": cfg["scope"],
#             "prompt": "consent",
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "pipedrive":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
#     else:
#         raise HTTPException(400, "Unsupported CRM")

#     return {"auth_url": auth_url}

# @router.get("/crm/callback/{crm}")
# async def oauth_callback(
#     crm: str,
#     code: Optional[str] = Query(None),
#     state: Optional[str] = Query(None),
#     error: Optional[str] = Query(None),
#     accounts_server: Optional[str] = Query(None, alias="accounts-server"),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED or crm == "close":
#         return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

#     st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
#     if not st:
#         return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

#     back = _sanitize_redirect(st.redirect_to or "/integrations")
#     cfg = _cfg()[crm]

#     if error:
#         await st.delete()
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

#     if not code:
#         await st.delete()
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

#     data = {
#         "grant_type": "authorization_code",
#         "code": code,
#         "redirect_uri": cfg["redirect_uri"],
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             await st.delete()
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")
#         j = r.json()

#     acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

#     # --- store tokens / instance data
#     def _as_int(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     if crm == "salesforce":
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.instance_url = j.get("instance_url") or acc.instance_url
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#     else:
#         acc.access_token = j.get("access_token")
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#         if crm == "pipedrive":
#             acc.instance_url = j.get("api_domain") or acc.instance_url
#         if crm == "zoho":
#             api_base = (
#                 j.get("api_domain")
#                 or _zoho_api_base_from_accounts_server(accounts_server)
#                 or _zoho_api_base_from_token_url(cfg["token_url"])
#             )
#             acc.instance_url = api_base

#     # --- verify
#     try:
#         await _verify_and_fill_account(crm, acc)
#     except HTTPException as e:
#         if crm == "zoho":
#             try:
#                 async with httpx.AsyncClient(timeout=15.0) as client:
#                     accounts_base = _zoho_accounts_from_api_base(acc.instance_url or _zoho_api_base_from_token_url(cfg["token_url"]))
#                     zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#                     r = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
#                     if r.status_code in (200, 204):
#                         pass
#                     else:
#                         await acc.save()
#                         await st.delete()
#                         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
#             except Exception:
#                 await acc.save()
#                 await st.delete()
#                 return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
#         else:
#             await acc.save()
#             await st.delete()
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

#     # --- IMPORTANT: reactivate on success
#     acc.is_active = True  # ensure account is active so /crm/accounts shows it
#     await acc.save()
#     await st.delete()
#     return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# # -------------------------
# # API key flow (Close) + optional HubSpot PAT
# # -------------------------
# @router.post("/crm/token/{crm}")
# async def set_token(
#     crm: str,
#     payload: Dict[str, str] = Body(..., example={"access_token": "xxxx"}),
#     user: User = Depends(get_current_user),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     if crm not in ("close", "hubspot"):
#         raise HTTPException(400, "This endpoint is only for Close (and optional HubSpot PAT).")

#     token = (payload.get("access_token") or "").strip()
#     if not token:
#         raise HTTPException(400, "access_token required.")

#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user=user, crm=crm)

#     acc.access_token = token
#     acc.refresh_token = None
#     acc.expires_at = None  # API key / PAT do not expire in the OAuth sense

#     await _verify_and_fill_account(crm, acc)

#     acc.is_active = True  # re-activate if it was previously disconnected
#     await acc.save()

#     return {"success": True, "message": f"{crm} token saved and verified."}

# @router.delete("/crm/disconnect/{crm}")
# async def disconnect(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc.is_active = False
#     await acc.save()
#     return {"success": True, "message": f"Disconnected {crm}."}

# @router.post("/crm/ensure-fresh/{crm}")
# async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc = await _ensure_fresh_token(crm.lower(), acc)
#     return {"success": True, "expires_at": acc.expires_at}

# # =========================
# # Contacts & Leads fetchers
# # =========================

# async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")
#     await _ensure_fresh_token(crm.lower(), acc)
#     return acc

# def _norm(
#     id: str,
#     name: Optional[str] = None,
#     email: Optional[str] = None,
#     phone: Optional[str] = None,
#     company: Optional[str] = None,
#     extra: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     return {
#         "id": str(id) if id is not None else None,
#         "name": (name or "") or None,
#         "email": email,
#         "phone": phone,
#         "company": company,
#         "raw": extra or {},
#     }

# @router.get("/crm/{crm}/contacts")
# async def fetch_contacts(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None, description="Leave empty for first page. HubSpot cursor is 'after' value returned from previous call."),
#     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     acc = await _get_active_account(user, crm)
#     items: list = []
#     next_cursor: Optional[str] = None
#     raw_paging: Dict[str, Any] = {}

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             params = {"limit": limit, "properties": "firstname,lastname,email,phone,company"}
#             if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                 params["after"] = cursor
#             r = await client.get(
#                 "https://api.hubapi.com/crm/v3/objects/contacts",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params=params,
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")
#             j = r.json()
#             for o in j.get("results", []):
#                 p = o.get("properties", {}) or {}
#                 name = (f"{p.get('firstname','')} {p.get('lastname','')}".strip() or p.get("email"))
#                 items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("company"), o))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "pipedrive":
#             start = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.pipedrive.com/v1/persons",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"start": start, "limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Pipedrive contacts fetch failed: {r.text}")
#             j = r.json()
#             for p in j.get("data") or []:
#                 name = p.get("name")
#                 email = None
#                 phone = None
#                 emails = p.get("email") or []
#                 phones = p.get("phone") or []
#                 if isinstance(emails, list) and emails:
#                     email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]
#                 if isinstance(phones, list) and phones:
#                     phone = phones[0].get("value") if isinstance(phones[0], dict) else phones[0]
#                 org = (p.get("org_id") or {}).get("name")
#                 items.append(_norm(p.get("id"), name, email, phone, org, p))
#             pag = ((j.get("additional_data") or {}).get("pagination") or {})
#             raw_paging = pag
#             if pag.get("more_items_in_collection"):
#                 next_cursor = str(pag.get("next_start"))

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#             page_num = page or (int(cursor) if cursor else 1)
#             r = await client.get(
#                 f"{api_base}/crm/v2/Contacts",
#                 headers=zheaders,
#                 params={"page": page_num, "per_page": limit, "fields": "Full_Name,Email,Phone,Account_Name"},
#             )
#             if r.status_code not in (200, 204):
#                 raise HTTPException(r.status_code, f"Zoho contacts fetch failed: {r.text}")
#             j = r.json() if r.text else {}
#             for c in j.get("data") or []:
#                 name = c.get("Full_Name") or c.get("Full Name") or c.get("Name")
#                 email = c.get("Email"); phone = c.get("Phone")
#                 acct = (c.get("Account_Name") or {}).get("name") if isinstance(c.get("Account_Name"), dict) else None
#                 items.append(_norm(c.get("id"), name, email, phone, acct, c))
#             info = j.get("info") or {}
#             raw_paging = info
#             if info.get("more_records"):
#                 next_cursor = str((info.get("page") or page_num) + 1)

#         elif crm == "salesforce":
#             base = (acc.instance_url or "").rstrip("/")
#             r_versions = await client.get(
#                 f"{base}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r_versions.is_success:
#                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
#             versions = r_versions.json()
#             latest = versions[-1]["version"]
#             offset = int(cursor) if cursor else 0
#             soql = f"SELECT Id, Name, Email, Phone, Account.Name FROM Contact ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
#             r = await client.get(
#                 f"{base}/services/data/v{latest}/query",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"q": soql},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Salesforce contacts fetch failed: {r.text}")
#             j = r.json()
#             for row in j.get("records") or []:
#                 acct = (row.get("Account") or {}).get("Name") if isinstance(row.get("Account"), dict) else None
#                 items.append(_norm(row.get("Id"), row.get("Name"), row.get("Email"), row.get("Phone"), acct, row))
#             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
#             if not j.get("done"):
#                 next_cursor = str(offset + limit)

#         elif crm == "close":
#             skip = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.close.com/api/v1/contact/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"_skip": skip, "_limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Close contacts fetch failed: {r.text}")
#             j = r.json()
#             for c in j.get("data") or []:
#                 name = c.get("name")
#                 email = (c.get("emails") or [{}])[0].get("email") if (c.get("emails") or []) else None
#                 phone = (c.get("phones") or [{}])[0].get("phone") if (c.get("phones") or []) else None
#                 items.append(_norm(c.get("id"), name, email, phone, None, c))
#             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
#             if j.get("has_more"):
#                 next_cursor = str(j.get("next") or (skip + limit))

#         else:
#             raise HTTPException(400, "Unsupported CRM")

#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# @router.get("/crm/{crm}/leads")
# async def fetch_leads(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None),
#     page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
# ):
#     """
#     Unified 'leads' listing.
#     Notes:
#     - HubSpot: try Leads object first (requires crm.objects.leads.*). Fallback to Deals.
#     - Pipedrive: try /leads first; fallback to /deals.
#     - Close: 'Lead' = company; 'Contact' = person.
#     """
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     acc = await _get_active_account(user, crm)
#     items: list = []
#     next_cursor: Optional[str] = None
#     raw_paging: Dict[str, Any] = {}

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         if crm == "hubspot":
#             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}

#             async def _try_leads():
#                 params = {"limit": limit, "properties": "hs_lead_status,createdate,firstname,lastname,email,phone,company"}
#                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                     params["after"] = cursor
#                 return await client.get("https://api.hubapi.com/crm/v3/objects/leads", headers=headers, params=params)

#             async def _try_deals():
#                 params = {"limit": limit, "properties": "dealname,amount,dealstage,createdate,hs_lead_status"}
#                 if cursor and str(cursor).lower() not in {"after", "none", "null"}:
#                     params["after"] = cursor
#                 return await client.get("https://api.hubapi.com/crm/v3/objects/deals", headers=headers, params=params)

#             r = await _try_leads()
#             if r.status_code in (404, 403):
#                 r = await _try_deals()

#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"HubSpot leads/deals fetch failed: {r.text}")

#             j = r.json()
#             results = j.get("results") or []
#             for d in results:
#                 p = d.get("properties", {}) or {}
#                 # best-effort name
#                 name = p.get("dealname") or (f"{p.get('firstname','')} {p.get('lastname','')}".strip()) or p.get("email")
#                 items.append(_norm(d.get("id"), name, p.get("Email") or p.get("email"), p.get("phone"), p.get("company"), d))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "pipedrive":
#             headers = {"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"}
#             start = int(cursor) if cursor else 0

#             async def _try_leads():
#                 return await client.get("https://api.pipedrive.com/v1/leads", headers=headers, params={"start": start, "limit": limit})

#             async def _try_deals():
#                 return await client.get("https://api.pipedrive.com/v1/deals", headers=headers, params={"start": start, "limit": limit})

#             r = await _try_leads()
#             if r.status_code in (403, 404):
#                 r = await _try_deals()
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Pipedrive leads/deals fetch failed: {r.text}")

#             j = r.json()
#             data = j.get("data") or []
#             for d in data:
#                 name = d.get("title") or d.get("deal_title") or d.get("org_name") or d.get("person_name")
#                 items.append(_norm(d.get("id"), name, None, None, d.get("org_name"), d))
#             pag = ((j.get("additional_data") or {}).get("pagination") or {})
#             raw_paging = pag
#             if pag.get("more_items_in_collection"):
#                 next_cursor = str(pag.get("next_start"))

#         elif crm == "zoho":
#             api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
#             zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
#             page_num = page or (int(cursor) if cursor else 1)
#             r = await client.get(
#                 f"{api_base}/crm/v2/Leads",
#                 headers=zheaders,
#                 params={"page": page_num, "per_page": limit, "fields": "Company,Last_Name,First_Name,Email,Phone,Lead_Status"},
#             )
#             if r.status_code not in (200, 204):
#                 raise HTTPException(r.status_code, f"Zoho leads fetch failed: {r.text}")
#             j = r.json() if r.text else {}
#             for l in j.get("data") or []:
#                 name = (f"{l.get('First_Name','')} {l.get('Last_Name','')}".strip() or l.get("Company") or None)
#                 items.append(_norm(l.get("id"), name, l.get("Email"), l.get("Phone"), l.get("Company"), l))
#             info = j.get("info") or {}
#             raw_paging = info
#             if info.get("more_records"):
#                 next_cursor = str((info.get("page") or page_num) + 1)

#         elif crm == "salesforce":
#             base = (acc.instance_url or "").rstrip("/")
#             r_versions = await client.get(
#                 f"{base}/services/data/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r_versions.is_success:
#                 raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
#             versions = r_versions.json()
#             latest = versions[-1]["version"]
#             offset = int(cursor) if cursor else 0
#             soql = f"SELECT Id, Company, FirstName, LastName, Email, Phone, Status FROM Lead ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
#             r = await client.get(
#                 f"{base}/services/data/v{latest}/query",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"q": soql},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Salesforce leads fetch failed: {r.text}")
#             j = r.json()
#             for row in j.get("records") or []:
#                 name = (f"{row.get('FirstName','')} {row.get('LastName','')}".strip() or row.get("Company") or None)
#                 items.append(_norm(row.get("Id"), name, row.get("Email"), row.get("Phone"), row.get("Company"), row))
#             raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
#             if not j.get("done"):
#                 next_cursor = str(offset + limit)

#         elif crm == "close":
#             skip = int(cursor) if cursor else 0
#             r = await client.get(
#                 "https://api.close.com/api/v1/lead/",
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params={"_skip": skip, "_limit": limit},
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"Close leads fetch failed: {r.text}")
#             j = r.json()
#             for l in j.get("data") or []:
#                 items.append(_norm(l.get("id"), l.get("name"), None, None, None, l))
#             raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
#             if j.get("has_more"):
#                 next_cursor = str(j.get("next") or (skip + limit))

#         else:
#             raise HTTPException(400, "Unsupported CRM")

#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# # ================
# # NEW: Bulk sync -> auto create files and import leads/contacts
# # ================

# def _split_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
#     if not full_name:
#         return None, None
#     parts = (full_name or "").strip().split()
#     if not parts:
#         return None, None
#     if len(parts) == 1:
#         return parts[0], None
#     return parts[0], " ".join(parts[1:])

# def _clean_phone(phone: Optional[str]) -> Optional[str]:
#     if not phone:
#         return None
#     digits = "".join(ch for ch in str(phone) if ch.isdigit())
#     return digits or None

# async def _fetch_all_items(user: User, crm: str, mode: str) -> List[Dict[str, Any]]:
#     """Use our own endpoints to page through ALL items."""
#     items: List[Dict[str, Any]] = []
#     cursor: Optional[str] = None
#     while True:
#         if mode == "contacts":
#             page = await fetch_contacts(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
#         else:
#             page = await fetch_leads(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
#         batch = page.get("items") or []
#         items.extend(batch)
#         nxt = page.get("next_cursor")
#         if not nxt:
#             break
#         cursor = str(nxt)
#     return items

# async def _ensure_file(user: User, name: str) -> FileModel:
#     file = await FileModel.get_or_none(user_id=user.id, name=name)
#     if not file:
#         file = FileModel(name=name, user=user)
#         await file.save()
#     return file

# async def _upsert_lead_from_item(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
#     """
#     Returns (created, updated)
#     We map our normalized item -> Lead model.
#     """
#     full_name = item.get("name")
#     first, last = _split_name(full_name)
#     email = item.get("email")
#     phone = _clean_phone(item.get("phone"))
#     external_id = item.get("id")  # stored in salesforce_id field (generic external id)
#     company = item.get("company")

#     # Check existing by file + external id
#     existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
#     payload = {
#         "first_name": first or "",
#         "last_name": last or "",
#         "email": email,
#         "mobile": phone,
#         "salesforce_id": external_id,
#         "add_date": datetime.now(),
#         "other_data": {
#             "Custom_0": company or "",
#             "Custom_1": f"source:{crm}"
#         }
#     }

#     if existing:
#         # Update basic fields if changed
#         changed = False
#         for k, v in payload.items():
#             if getattr(existing, k, None) != v:
#                 setattr(existing, k, v)
#                 changed = True
#         if existing.file_id != file.id:
#             existing.file = file
#             changed = True
#         if changed:
#             await existing.save()
#             return (False, True)
#         return (False, False)
#     else:
#         new = Lead(file=file, **payload)
#         await new.save()
#         return (True, False)

# @router.post("/crm/sync-to-files")
# async def sync_connected_crms_to_files(
#     user: User = Depends(get_current_user),
#     crm: Optional[str] = Query(None, description="If provided, only sync this CRM (hubspot, salesforce, zoho, pipedrive, close)"),
#     mode: str = Query("leads", pattern="^(leads|contacts)$", description="What to import into the file")
# ):
#     """
#     For each connected CRM:
#       - Ensure a file exists named '<CRM> Leads' (or 'Contacts')
#       - Fetch ALL pages from that CRM
#       - Upsert into the file (no duplicates on rerun)
#     """
#     # Which CRMs to run
#     connected = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
#     if crm:
#         crm = crm.lower()
#         connected = [a for a in connected if a.crm == crm]
#         if not connected:
#             raise HTTPException(404, f"Not connected to {crm}.")
#     if not connected:
#         return {"success": True, "ran": 0, "details": []}

#     results = []
#     for acc in connected:
#         label = acc.crm.capitalize()
#         file_name = f"{label} {mode.capitalize()}"  # e.g. "HubSpot Leads"
#         file = await _ensure_file(user, file_name)

#         try:
#             items = await _fetch_all_items(user, acc.crm, mode)
#             created = 0
#             updated = 0
#             for it in items:
#                 c, u = await _upsert_lead_from_item(file, it, acc.crm)
#                 created += 1 if c else 0
#                 updated += 1 if u else 0

#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "fetched": len(items),
#                 "created": created,
#                 "updated": updated,
#             })
#         except HTTPException as e:
#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "error": str(e.detail),
#             })
#         except Exception as e:
#             results.append({
#                 "crm": acc.crm,
#                 "file_id": file.id,
#                 "file_name": file.name,
#                 "error": str(e),
#             })

#     return {"success": True, "ran": len(connected), "details": results}



































import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import RedirectResponse, JSONResponse

from helpers.token_helper import get_current_user
from models.auth import User
from models.crm import IntegrationAccount, IntegrationOAuthState
from models.file import File as FileModel
from models.lead import Lead

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
            "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
            # default includes contacts/deals/leads/lists + oauth
            "scope": os.getenv(
                "HUBSPOT_SCOPES",
                "crm.objects.contacts.read crm.objects.contacts.write "
                "crm.objects.deals.read crm.objects.deals.write "
                "crm.objects.leads.read crm.objects.leads.write "
                "crm.lists.read crm.lists.write oauth"
            ),
            "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
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
            "scope": os.getenv("PIPEDRIVE_SCOPES", "deals:full contacts:full"),
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
    return _now() + timedelta(seconds=max(0, seconds - 60))

def _sanitize_redirect(back: str) -> str:
    """Prevent open-redirects: allow only same-site relative paths or whitelisted origins via env."""
    if back and back.startswith("/") and not back.startswith("//"):
        return back
    allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
    if back and allowed:
        p = urlparse(back)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in allowed:
            return back
    return "/integrations"

# ---- Zoho DC helpers ----
_ZOHO_ACCOUNTS_TO_API = {
    "accounts.zoho.com": "https://www.zohoapis.com",
    "accounts.zoho.eu": "https://www.zohoapis.eu",
    "accounts.zoho.in": "https://www.zohoapis.in",
    "accounts.zoho.com.au": "https://www.zohoapis.com.au",
    "accounts.zoho.jp": "https://www.zohoapis.jp",
    "accounts.zoho.uk": "https://www.zohoapis.uk",
}
_ZOHO_API_TO_ACCOUNTS = {
    "www.zohoapis.com": "https://accounts.zoho.com",
    "www.zohoapis.eu": "https://accounts.zoho.eu",
    "www.zohoapis.in": "https://accounts.zoho.in",
    "www.zohoapis.com.au": "https://accounts.zoho.com.au",
    "www.zohoapis.jp": "https://accounts.zoho.jp",
    "www.zohoapis.uk": "https://accounts.zoho.uk",
}

def _zoho_api_base_from_accounts_server(accounts_server: Optional[str]) -> Optional[str]:
    if not accounts_server:
        return None
    try:
        host = urlparse(accounts_server).netloc or accounts_server
        return _ZOHO_ACCOUNTS_TO_API.get(host)
    except Exception:
        return None

def _zoho_api_base_from_token_url(token_url: str) -> str:
    try:
        host = urlparse(token_url).netloc
        return _ZOHO_ACCOUNTS_TO_API.get(host, "https://www.zohoapis.com")
    except Exception:
        return "https://www.zohoapis.com"

def _zoho_accounts_from_api_base(api_base: str) -> str:
    host = urlparse(api_base).netloc
    return _ZOHO_API_TO_ACCOUNTS.get(host, "https://accounts.zoho.com")

# -------------------------
# Token verification
# -------------------------
async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        if crm == "hubspot":
            url = f"{_cfg()['hubspot']['verify_url'].rstrip('/')}/{acc.access_token}"
            r = await client.get(url, headers={"Accept": "application/json"})
            if r.is_success:
                j = r.json()
                acc.external_account_id = str(j.get("hub_id") or j.get("hubId") or "")
                u = j.get("user")
                if isinstance(u, str):
                    acc.external_account_name = u
                elif isinstance(u, dict):
                    acc.external_account_name = u.get("email") or u.get("name") or None
                else:
                    acc.external_account_name = None
            else:
                r2 = await client.get(
                    "https://api.hubapi.com/crm/v3/owners?limit=1",
                    headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                )
                if not r2.is_success:
                    raise HTTPException(401, "HubSpot token validation failed.")

        elif crm == "salesforce":
            base = acc.instance_url or ""
            if not base:
                raise HTTPException(400, "Salesforce instance_url missing.")
            r = await client.get(
                f"{base.rstrip('/')}/services/data/",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(401, "Salesforce token validation failed.")

        elif crm == "zoho":
            api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()['zoho']['token_url'])).rstrip("/")
            accounts_base = _zoho_accounts_from_api_base(api_base)
            zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}

            r_acc = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
            if r_acc.status_code not in (200, 204):
                raise HTTPException(401, f"Zoho accounts verify {r_acc.status_code}: {(r_acc.text or '')[:300]}")
            try:
                info = r_acc.json()
                acc.external_account_name = info.get("Email") or info.get("email") or acc.external_account_name
            except Exception:
                pass

            endpoints = [
                "/crm/v2/Contacts?fields=id&per_page=1",
                "/crm/v2/Leads?fields=id&per_page=1",
                "/crm/v2/settings/modules?per_page=1",
            ]
            ok = False
            for ep in endpoints:
                r = await client.get(f"{api_base}{ep}", headers=zheaders)
                if r.status_code in (200, 204):
                    ok = True
                    break
            if not ok:
                acc.external_account_id = acc.external_account_id or ""

        elif crm == "pipedrive":
            r = await client.get(
                "https://api.pipedrive.com/v1/users/me",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(401, "Pipedrive token validation failed.")
            j = r.json().get("data") or {}
            acc.external_account_id = str(j.get("company_id") or "")
            acc.external_account_name = j.get("company_name") or None

        elif crm == "close":
            r = await client.get(
                "https://api.close.com/api/v1/me/",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(401, "Close API key invalid.")
            j = r.json()
            acc.external_account_id = str(j.get("organization_id") or "")
            acc.external_account_name = (j.get("organization") or {}).get("name")

# -------------------------
# Refresh tokens
# -------------------------
async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
    if crm == "close":
        return acc

    SKEW_SECONDS = 120
    if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
        return acc

    cfg = _cfg()[crm]
    if not acc.refresh_token:
        return acc

    data: Dict[str, Any] = {"grant_type": "refresh_token", "refresh_token": acc.refresh_token}
    if crm in ("hubspot", "pipedrive", "zoho", "salesforce"):
        data["client_id"] = cfg["client_id"]
        data["client_secret"] = cfg["client_secret"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(cfg["token_url"], data=data)
        if not r.is_success:
            raise HTTPException(401, f"{crm} refresh failed: {r.text}")
        j = r.json()

    def _get_exp(v, default=3600):
        try:
            return int(v)
        except Exception:
            return default

    if crm == "salesforce":
        acc.access_token = j.get("access_token")
        acc.refresh_token = acc.refresh_token or j.get("refresh_token")
        acc.instance_url = j.get("instance_url") or acc.instance_url
        acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
    else:
        acc.access_token = j.get("access_token")
        acc.refresh_token = acc.refresh_token or j.get("refresh_token")
        acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
        if crm == "pipedrive":
            acc.instance_url = j.get("api_domain") or acc.instance_url
        if crm == "zoho":
            acc.instance_url = j.get("api_domain") or acc.instance_url

    await acc.save()
    return acc

# -------------------------
# Public routes
# -------------------------
@router.get("/crm/providers")
async def list_providers():
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

@router.post("/crm/connect/{crm}")
async def start_connect(
    crm: str,
    user: User = Depends(get_current_user),
    redirect_to: Optional[str] = Body(default="/integrations", embed=True),
):
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")
    if crm == "close":
        raise HTTPException(400, "Close uses API key. Call POST /crm/token/close.")

    cfg = _cfg()[crm]
    if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
        raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

    state = secrets.token_urlsafe(24)
    await IntegrationOAuthState.create(
        user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/integrations")
    )

    if crm == "hubspot":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "scope": cfg["scope"],
            "state": state,
            "response_type": "code",
        }
        auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

    elif crm == "salesforce":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

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
        auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

    elif crm == "pipedrive":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
    else:
        raise HTTPException(400, "Unsupported CRM")

    return {"auth_url": auth_url}

@router.get("/crm/callback/{crm}")
async def oauth_callback(
    crm: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    accounts_server: Optional[str] = Query(None, alias="accounts-server"),
):
    crm = crm.lower()
    if crm not in SUPPORTED or crm == "close":
        return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

    st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
    if not st:
        return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

    back = _sanitize_redirect(st.redirect_to or "/integrations")
    cfg = _cfg()[crm]

    if error:
        await st.delete()
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

    if not code:
        await st.delete()
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

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

    acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
    if not acc:
        acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

    def _as_int(v, default=3600):
        try:
            return int(v)
        except Exception:
            return default

    if crm == "salesforce":
        acc.access_token = j.get("access_token")
        acc.refresh_token = j.get("refresh_token") or acc.refresh_token
        acc.instance_url = j.get("instance_url") or acc.instance_url
        acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
    else:
        acc.access_token = j.get("access_token")
        acc.refresh_token = j.get("refresh_token") or acc.refresh_token
        acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
        if crm == "pipedrive":
            acc.instance_url = j.get("api_domain") or acc.instance_url
        if crm == "zoho":
            api_base = (
                j.get("api_domain")
                or _zoho_api_base_from_accounts_server(accounts_server)
                or _zoho_api_base_from_token_url(cfg["token_url"])
            )
            acc.instance_url = api_base

    try:
        await _verify_and_fill_account(crm, acc)
    except HTTPException as e:
        if crm == "zoho":
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    accounts_base = _zoho_accounts_from_api_base(acc.instance_url or _zoho_api_base_from_token_url(cfg["token_url"]))
                    zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
                    r = await client.get(f"{accounts_base}/oauth/user/info", headers=zheaders)
                    if r.status_code in (200, 204):
                        pass
                    else:
                        await acc.save()
                        await st.delete()
                        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
            except Exception:
                await acc.save()
                await st.delete()
                return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")
        else:
            await acc.save()
            await st.delete()
            return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

    acc.is_active = True
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
    acc.expires_at = None

    await _verify_and_fill_account(crm, acc)

    acc.is_active = True
    await acc.save()

    return {"success": True, "message": f"{crm} token saved and verified."}

@router.delete("/crm/disconnect/{crm}")
async def disconnect(crm: str, user: User = Depends(get_current_user)):
    crm = crm.lower()
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc.is_active = False
    await acc.save()
    return {"success": True, "message": f"Disconnected {crm}."}

@router.post("/crm/ensure-fresh/{crm}")
async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc = await _ensure_fresh_token(crm.lower(), acc)
    return {"success": True, "expires_at": acc.expires_at}

# =========================
# Contacts fetchers (we treat Contacts as Leads)
# =========================

async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
    if not acc:
        raise HTTPException(404, f"Not connected to {crm}.")
    await _ensure_fresh_token(crm.lower(), acc)
    return acc

def _norm(
    id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    state: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(id) if id is not None else None,
        "name": (name or "") or None,
        "email": email,
        "phone": phone,
        "state": state,
        "raw": extra or {},
    }

@router.get("/crm/{crm}/contacts")
async def fetch_contacts(
    crm: str,
    user: User = Depends(get_current_user),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Leave empty for first page. HubSpot cursor is 'after' value returned from previous call."),
    page: Optional[int] = Query(None, description="Zoho helper: 1-based page number"),
):
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")

    acc = await _get_active_account(user, crm)
    items: list = []
    next_cursor: Optional[str] = None
    raw_paging: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if crm == "hubspot":
            params = {"limit": limit, "properties": "firstname,lastname,email,phone,company,state"}
            if cursor and str(cursor).lower() not in {"after", "none", "null"}:
                params["after"] = cursor
            r = await client.get(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                params=params,
            )
            if not r.is_success:
                raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")
            j = r.json()
            for o in j.get("results", []):
                p = o.get("properties", {}) or {}
                name = (f"{p.get('firstname','')} {p.get('lastname','')}".strip() or p.get("email"))
                items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("state"), o))
            next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
            raw_paging = j.get("paging") or {}

        elif crm == "pipedrive":
            start = int(cursor) if cursor else 0
            r = await client.get(
                "https://api.pipedrive.com/v1/persons",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                params={"start": start, "limit": limit},
            )
            if not r.is_success:
                raise HTTPException(r.status_code, f"Pipedrive contacts fetch failed: {r.text}")
            j = r.json()
            for p in j.get("data") or []:
                name = p.get("name")
                email = None
                phone = None
                emails = p.get("email") or []
                phones = p.get("phone") or []
                if isinstance(emails, list) and emails:
                    email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]
                if isinstance(phones, list) and phones:
                    phone = phones[0].get("value") if isinstance(phones[0], dict) else phones[0]
                org = (p.get("org_id") or {}).get("name")
                items.append(_norm(p.get("id"), name, email, phone, org, p))
            pag = ((j.get("additional_data") or {}).get("pagination") or {})
            raw_paging = pag
            if pag.get("more_items_in_collection"):
                next_cursor = str(pag.get("next_start"))

        elif crm == "zoho":
            api_base = (acc.instance_url or _zoho_api_base_from_token_url(_cfg()["zoho"]["token_url"])).rstrip("/")
            zheaders = {"Authorization": f"Zoho-oauthtoken {acc.access_token}", "Accept": "application/json"}
            page_num = page or (int(cursor) if cursor else 1)
            r = await client.get(
                f"{api_base}/crm/v2/Contacts",
                headers=zheaders,
                params={"page": page_num, "per_page": limit, "fields": "Full_Name,Email,Phone,Account_Name"},
            )
            if r.status_code not in (200, 204):
                raise HTTPException(r.status_code, f"Zoho contacts fetch failed: {r.text}")
            j = r.json() if r.text else {}
            for c in j.get("data") or []:
                name = c.get("Full_Name") or c.get("Full Name") or c.get("Name")
                email = c.get("Email")
                phone = c.get("Phone")
                acct = (c.get("Account_Name") or {}).get("name") if isinstance(c.get("Account_Name"), dict) else None
                items.append(_norm(c.get("id"), name, email, phone, acct, c))
            info = j.get("info") or {}
            raw_paging = info
            if info.get("more_records"):
                next_cursor = str((info.get("page") or page_num) + 1)

        elif crm == "salesforce":
            base = (acc.instance_url or "").rstrip("/")
            r_versions = await client.get(
                f"{base}/services/data/",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
            )
            if not r_versions.is_success:
                raise HTTPException(r_versions.status_code, f"Salesforce version probe failed: {r_versions.text}")
            versions = r_versions.json()
            latest = versions[-1]["version"]
            offset = int(cursor) if cursor else 0
            soql = f"SELECT Id, Name, Email, Phone, Account.Name FROM Contact ORDER BY CreatedDate DESC LIMIT {limit} OFFSET {offset}"
            r = await client.get(
                f"{base}/services/data/v{latest}/query",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                params={"q": soql},
            )
            if not r.is_success:
                raise HTTPException(r.status_code, f"Salesforce contacts fetch failed: {r.text}")
            j = r.json()
            for row in j.get("records") or []:
                acct = (row.get("Account") or {}).get("Name") if isinstance(row.get("Account"), dict) else None
                items.append(_norm(row.get("Id"), row.get("Name"), row.get("Email"), row.get("Phone"), acct, row))
            raw_paging = {"totalSize": j.get("totalSize"), "done": j.get("done")}
            if not j.get("done"):
                next_cursor = str(offset + limit)

        elif crm == "close":
            skip = int(cursor) if cursor else 0
            r = await client.get(
                "https://api.close.com/api/v1/contact/",
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                params={"_skip": skip, "_limit": limit},
            )
            if not r.is_success:
                raise HTTPException(r.status_code, f"Close contacts fetch failed: {r.text}")
            j = r.json()
            for c in j.get("data") or []:
                name = c.get("name")
                email = (c.get("emails") or [{}])[0].get("email") if (c.get("emails") or []) else None
                phone = (c.get("phones") or [{}])[0].get("phone") if (c.get("phones") or []) else None
                items.append(_norm(c.get("id"), name, email, phone, None, c))
            raw_paging = {"has_more": j.get("has_more"), "next": j.get("next")}
            if j.get("has_more"):
                next_cursor = str(j.get("next") or (skip + limit))

        else:
            raise HTTPException(400, "Unsupported CRM")

    return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# =========================
# Treat Contacts as Leads -> auto-create "<CRM> Leads" file and upsert
# =========================

def _split_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not full_name:
        return None, None
    parts = (full_name or "").strip().split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])

def _clean_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits or None

async def _fetch_all_contacts(user: User, crm: str) -> List[Dict[str, Any]]:
    """Use our own /contacts endpoint to pull ALL pages."""
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        page = await fetch_contacts(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
        batch = page.get("items") or []
        items.extend(batch)
        nxt = page.get("next_cursor")
        if not nxt:
            break
        cursor = str(nxt)
    return items

async def _ensure_file(user: User, name: str) -> FileModel:
    file = await FileModel.get_or_none(user_id=user.id, name=name)
    if not file:
        file = FileModel(name=name, user=user)
        await file.save()
    return file

async def _upsert_lead_from_contact(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
    """
    Upsert a Lead from a normalized contact item.
    Uses (file_id, salesforce_id=<external id>) to dedupe.
    Returns (created, updated).
    """
    full_name = item.get("name")
    first, last = _split_name(full_name)
    email = item.get("email")
    phone = _clean_phone(item.get("phone"))
    external_id = item.get("id")  # store as generic external id in salesforce_id field
    state = item.get("state")

    existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
    payload = {
        "first_name": first or "",
        "last_name": last or "",
        "email": email,
        "mobile": phone,
        "state": state,
        "salesforce_id": external_id,
        "add_date": datetime.now(),
        "other_data": {
            "Custom_0": company or "",
            "Custom_1": f"source:{crm}"
        }
    }

    if existing:
        changed = False
        # update only when changed
        for k, v in payload.items():
            if getattr(existing, k, None) != v:
                setattr(existing, k, v)
                changed = True
        if existing.file_id != file.id:
            existing.file = file
            changed = True
        if changed:
            await existing.save()
            return (False, True)
        return (False, False)

    new = Lead(file=file, **payload)
    await new.save()
    return (True, False)

@router.post("/crm/sync-to-files")
async def sync_connected_crms_to_files(
    user: User = Depends(get_current_user),
    crm: Optional[str] = Query(None, description="If provided, only sync this CRM (hubspot, salesforce, zoho, pipedrive, close)")
):
    """
    For each connected CRM:
      - Ensure a file exists named '<CRM> Leads'
      - Fetch ALL CONTACTS from that CRM
      - Upsert them into the file as Leads (no duplicates on rerun)
    """
    connected = await IntegrationAccount.filter(user_id=user.id, is_active=True).all()
    if crm:
        crm = crm.lower()
        connected = [a for a in connected if a.crm == crm]
        if not connected:
            raise HTTPException(404, f"Not connected to {crm}.")
    if not connected:
        return {"success": True, "ran": 0, "details": []}

    results = []
    for acc in connected:
        label = acc.crm.capitalize()
        file_name = f"{label} Leads"          # e.g., "HubSpot Leads"
        file = await _ensure_file(user, file_name)

        try:
            items = await _fetch_all_contacts(user, acc.crm)
            created = 0
            updated = 0
            for it in items:
                c, u = await _upsert_lead_from_contact(file, it, acc.crm)
                if c: created += 1
                if u: updated += 1

            results.append({
                "crm": acc.crm,
                "file_id": file.id,
                "file_name": file.name,
                "fetched_contacts": len(items),
                "created_leads": created,
                "updated_leads": updated,
            })
        except HTTPException as e:
            results.append({
                "crm": acc.crm,
                "file_id": file.id,
                "file_name": file.name,
                "error": str(e.detail),
            })
        except Exception as e:
            results.append({
                "crm": acc.crm,
                "file_id": file.id,
                "file_name": file.name,
                "error": str(e),
            })

    return {"success": True, "ran": len(connected), "details": results}
