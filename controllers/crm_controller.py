

# import os
# import secrets
# import logging
# from datetime import datetime, timedelta, timezone
# from typing import Optional, Dict, Any, List, Tuple
# from urllib.parse import urlparse, urlencode, urlsplit, urlunsplit, parse_qsl, quote_plus

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
# from fastapi.responses import RedirectResponse, JSONResponse

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.crm import IntegrationAccount, IntegrationOAuthState
# from models.file import File as FileModel
# from models.lead import Lead

# router = APIRouter()
# logger = logging.getLogger("crm")

# # ─────────────────────────────────────────────────────────────────────────────
# # Config (HubSpot + GHL + MONDAY)
# # ─────────────────────────────────────────────────────────────────────────────

# def _cfg() -> Dict[str, Dict[str, str]]:
#     return {
#         "hubspot": {
#             "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
#             "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
#             "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
#             "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
#             "scope": os.getenv(
#                 "HUBSPOT_SCOPES",
#                 "crm.objects.contacts.read crm.objects.contacts.write oauth"
#             ),
#             "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
#             "type": "oauth",
#         },
#         "ghl": {
#             "install_url": os.getenv("GHL_INSTALL_URL", ""),
#             "install_base": os.getenv("GHL_INSTALL_BASE", "https://marketplace.gohighlevel.com"),
#             "auth_path": "/oauth/chooselocation",
#             "token_url": os.getenv("GHL_TOKEN_URL", "https://services.leadconnectorhq.com/oauth/token"),
#             "contacts_url": os.getenv("GHL_CONTACTS_URL", "https://services.leadconnectorhq.com/contacts/"),
#             "client_id": os.getenv("GHL_CLIENT_ID", ""),
#             "client_secret": os.getenv("GHL_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("GHL_REDIRECT_URI", ""),
#             "scope": os.getenv("GHL_SCOPES", "contacts.readonly contacts.write"),
#             "type": "oauth",
#         },
#         # MONDAY: OAuth & GraphQL API
#         "monday": {
#             "auth_url": os.getenv("MONDAY_AUTH_URL", "https://auth.monday.com/oauth2/authorize"),
#             "token_url": os.getenv("MONDAY_TOKEN_URL", "https://auth.monday.com/oauth2/token"),
#             "api_url": os.getenv("MONDAY_API_URL", "https://api.monday.com/v2"),
#             "client_id": os.getenv("MONDAY_CLIENT_ID", ""),
#             "client_secret": os.getenv("MONDAY_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("MONDAY_REDIRECT_URI", ""),
#             "scope": os.getenv("MONDAY_SCOPES", ""),  
#             # optional board-based contacts:
#             "board_id": os.getenv("MONDAY_BOARD_ID", ""),
#             "email_col": os.getenv("MONDAY_EMAIL_COLUMN_ID", ""),
#             "phone_col": os.getenv("MONDAY_PHONE_COLUMN_ID", ""),
#             "state_col": os.getenv("MONDAY_STATE_COLUMN_ID", ""),
#             # subdomain targeting + install behavior
#             "subdomain": os.getenv("MONDAY_SUBDOMAIN", ""),  # e.g. "aisdrdbt"
#             "subdomain_strategy": os.getenv("MONDAY_SUBDOMAIN_STRATEGY", "param"),  # "param" | "host"
#             "force_install_if_needed": (os.getenv("MONDAY_FORCE_INSTALL_IF_NEEDED", "false") or "").lower() == "true",
#             "type": "oauth",
#         },
#     }

# SUPPORTED = ("hubspot", "ghl", "monday")

# # ─────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────────────────────────────────────

# def _now() -> datetime:
#     return datetime.now(timezone.utc)

# def _exp_from_seconds(seconds: int) -> datetime:
#     return _now() + timedelta(seconds=max(0, seconds - 60))

# def _sanitize_redirect(back: str) -> str:
#     if back and back.startswith("/") and not back.startswith("//"):
#         return back
#     allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
#     if back and allowed:
#         p = urlparse(back)
#         origin = f"{p.scheme}://{p.netloc}"
#         if origin in allowed:
#             return back
#     return "/user/CRM"

# def _append_qs(url: str, params: Dict[str, str]) -> str:
#     parts = list(urlsplit(url))
#     q = dict(parse_qsl(parts[3], keep_blank_values=True))
#     q.update({k: v for k, v in params.items() if v is not None})
#     parts[3] = urlencode(q)
#     return urlunsplit(parts)

# # ─────────────────────────────────────────────────────────────────────────────
# # Token verification
# # ─────────────────────────────────────────────────────────────────────────────

# async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
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
#                 logger.info("hubspot verify ok hub_id=%s user=%s",
#                             acc.external_account_id, acc.external_account_name)
#             else:
#                 r2 = await client.get(
#                     "https://api.hubapi.com/crm/v3/owners?limit=1",
#                     headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 )
#                 if not r2.is_success:
#                     logger.error("hubspot verify failed: %s %s", r.status_code, r.text[:200])
#                     raise HTTPException(401, "HubSpot token validation failed.")

#         elif crm == "ghl":
#             contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
#             probe = f"{contacts_url}?limit=1"
#             r = await client.get(
#                 probe,
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 logger.error("GHL verify failed: %s %s", r.status_code, r.text[:200])
#                 raise HTTPException(401, "GHL token validation failed.")
#             try:
#                 _ = r.json()
#             except Exception:
#                 pass
#             acc.external_account_name = acc.external_account_name or "GHL"
#             logger.info("GHL verify ok")

#         elif crm == "monday":
#             # Probe with GraphQL `me`
#             q = """
#             query {
#               me {
#                 id
#                 name
#                 email
#                 account { id name }
#               }
#             }
#             """
#             r = await client.post(
#                 _cfg()["monday"]["api_url"],
#                 headers={
#                     "Authorization": f"Bearer {acc.access_token}",
#                     "Content-Type": "application/json",
#                 },
#                 json={"query": q},
#             )
#             if not r.is_success:
#                 logger.error("monday verify failed: %s %s", r.status_code, r.text[:200])
#                 raise HTTPException(401, "monday token validation failed.")
#             j = r.json()
#             me = ((j or {}).get("data") or {}).get("me") or {}
#             if not me:
#                 logger.error("monday verify: empty `me`")
#                 raise HTTPException(401, "monday token validation failed.")
#             acct = me.get("account") or {}
#             acc.external_account_id = str(acct.get("id") or "")
#             acc.external_account_name = acct.get("name") or me.get("email") or me.get("name") or "monday"
#             logger.info("monday verify ok account_id=%s name=%s",
#                         acc.external_account_id, acc.external_account_name)

#         else:
#             raise HTTPException(400, "Unsupported CRM for verification")

# # ─────────────────────────────────────────────────────────────────────────────
# # Refresh tokens (OAuth2)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
#     SKEW_SECONDS = 120
#     if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
#         return acc

#     cfg = _cfg()[crm]
#     # MONDAY: tokens do not expire and no refresh_token is issued.
#     if not acc.refresh_token:
#         logger.debug("%s: no refresh_token present; assuming still valid", crm)
#         return acc

#     data: Dict[str, Any] = {
#         "grant_type": "refresh_token",
#         "refresh_token": acc.refresh_token,
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             logger.error("%s refresh failed: %s %s", crm, r.status_code, r.text[:300])
#             raise HTTPException(401, f"{crm} refresh failed: {r.text}")
#         j = r.json()

#     def _get_exp(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     acc.access_token = j.get("access_token") or acc.access_token
#     acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#     acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#     await acc.save()
#     logger.info("%s refreshed; exp=%s", crm, acc.expires_at)
#     return acc

# # ─────────────────────────────────────────────────────────────────────────────
# # Public routes
# # ─────────────────────────────────────────────────────────────────────────────

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
#     redirect_to: Optional[str] = Body(default="/user/CRM", embed=True),
# ):
#     """
#     Starts OAuth:
#       • HubSpot: standard authorize URL.
#       • GHL: Marketplace Install link or build from parts.
#       • monday: standard OAuth authorize URL with optional subdomain targeting.
#     """
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     cfg = _cfg()[crm]
#     if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
#         raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

#     state = secrets.token_urlsafe(24)
#     await IntegrationOAuthState.create(
#         user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/user/CRM")
#     )

#     if crm == "hubspot":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "ghl":
#         install_url = (cfg["install_url"] or "").strip()
#         if install_url:
#             auth_url = _append_qs(install_url, {"state": state})
#         else:
#             built = f'{cfg["install_base"].rstrip("/")}{cfg["auth_path"]}'
#             params = {
#                 "response_type": "code",
#                 "redirect_uri": cfg["redirect_uri"],
#                 "client_id": cfg["client_id"],
#                 "scope": cfg["scope"],
#                 "state": state,
#             }
#             auth_url = f"{built}?{urlencode(params)}"

#     else:  # MONDAY
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "state": state,
#         }
#         # Optional explicit scopes (if provided) – otherwise Monday uses app-configured scopes
#         if cfg.get("scope"):
#             params["scope"] = cfg["scope"]
#         # Optionally nudge Monday to install app first if missing
#         if cfg.get("force_install_if_needed"):
#             params["force_install_if_needed"] = "true"

#         sub = (cfg.get("subdomain") or "").strip()
#         strat = (cfg.get("subdomain_strategy") or "param").lower()

#         if sub:
#             if strat == "host":
#                 # Soft default: user can still change the account
#                 base = f"https://{sub}.monday.com/oauth2/authorize"
#                 auth_url = f"{base}?{httpx.QueryParams(params)}"
#             else:
#                 # Hard lock: force a specific account
#                 params["subdomain"] = sub
#                 auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
#         else:
#             auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     logger.info("oauth start crm=%s user=%s state=%s", crm, user.id, state)
#     return {"auth_url": auth_url}

# @router.get("/crm/callback/{crm}")
# async def oauth_callback(
#     crm: str,
#     code: Optional[str] = Query(None),
#     state: Optional[str] = Query(None),
#     error: Optional[str] = Query(None),
#     background_tasks: BackgroundTasks = None,
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

#     st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
#     if not st:
#         return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

#     back = _sanitize_redirect(st.redirect_to or "/user/CRM")
#     cfg = _cfg()[crm]

#     if error:
#         await st.delete()
#         logger.warning("oauth error crm=%s state=%s error=%s", crm, state, error)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

#     if not code:
#         await st.delete()
#         logger.warning("oauth no_code crm=%s state=%s", crm, state)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

#     data = {
#         "grant_type": "authorization_code",
#         "code": code,
#         "redirect_uri": cfg["redirect_uri"],
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     logger.info("oauth exchanging code crm=%s state=%s", crm, state)
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             await st.delete()
#             logger.error("oauth token exchange failed crm=%s status=%s body=%s",
#                          crm, r.status_code, r.text[:300])
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")
#         j = r.json()

#     acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

#     def _as_int(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     acc.access_token = j.get("access_token")
#     # MONDAY: no refresh token & tokens do not expire
#     if crm == "monday":
#         acc.refresh_token = None
#         acc.expires_at = None
#     else:
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#     await acc.save()

#     try:
#         await _verify_and_fill_account(crm, acc)
#     except HTTPException as e:
#         await acc.save()
#         await st.delete()
#         logger.error("oauth verify failed crm=%s detail=%s", crm, e.detail)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

#     acc.is_active = True
#     await acc.save()

#     # Auto-ingest Monday leads right after successful auth (non-blocking)
#     if crm == "monday" and background_tasks is not None:
#         user_obj = await User.get(id=st.user_id)
#         background_tasks.add_task(_sync_one_crm, user_obj, "monday")

#     await st.delete()
#     logger.info("oauth success crm=%s user=%s", crm, acc.user_id if hasattr(acc, "user_id") else st.user_id)
#     return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# @router.delete("/crm/disconnect/{crm}")
# async def disconnect(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc.is_active = False
#     await acc.save()
#     logger.info("disconnected crm=%s user=%s", crm, user.id)
#     return {"success": True, "message": f"Disconnected {crm}."}

# @router.post("/crm/ensure-fresh/{crm}")
# async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc = await _ensure_fresh_token(crm, acc)
#     return {"success": True, "expires_at": acc.expires_at}

# # ─────────────────────────────────────────────────────────────────────────────
# # Contacts fetchers (normalize to Lead-like rows)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")
#     await _ensure_fresh_token(crm.lower(), acc)
#     return acc

# def _norm(
#     id: Any,
#     name: Optional[str] = None,
#     email: Optional[str] = None,
#     phone: Optional[str] = None,
#     state: Optional[str] = None,
#     extra: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     return {
#         "id": (str(id) if id is not None else None),
#         "name": (name or "") or None,
#         "email": email,
#         "phone": phone,
#         "state": state,
#         "raw": extra or {},
#     }

# @router.get("/crm/{crm}/contacts")
# async def fetch_contacts(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None, description="Opaque paging cursor/token"),
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
#             params = {"limit": limit, "properties": "firstname,lastname,email,phone,company,state"}
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
#                 items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("state"), o))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "ghl":
#             contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
#             url = contacts_url
#             params = {"limit": limit}
#             if cursor:
#                 params.update({"cursor": cursor, "nextPageToken": cursor, "page": cursor})

#             r = await client.get(
#                 url,
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params=params,
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"GHL contacts fetch failed: {r.text[:300]}")
#             j = r.json() if r.text else {}

#             data_list = None
#             for key in ("contacts", "data", "items", "results"):
#                 if isinstance(j.get(key), list):
#                     data_list = j.get(key)
#                     break
#             if data_list is None and isinstance(j, list):
#                 data_list = j

#             for c in (data_list or []):
#                 cid = c.get("id") or c.get("_id") or c.get("contactId")
#                 first = c.get("firstName") or c.get("first_name")
#                 last = c.get("lastName") or c.get("last_name")
#                 full = c.get("name") or " ".join(x for x in [first, last] if x)
#                 email = c.get("email")
#                 phone = c.get("phone") or c.get("phoneNumber") or c.get("phone_number")
#                 state = (
#                     c.get("state")
#                     or (c.get("address", {}) or {}).get("state")
#                     or c.get("region")
#                     or None
#                 )
#                 items.append(_norm(cid, full or None, email, phone, state, c))

#             if isinstance(j.get("meta"), dict):
#                 meta = j["meta"]
#                 raw_paging["meta"] = meta
#                 next_cursor = (
#                     meta.get("nextPageToken")
#                     or meta.get("next_token")
#                     or meta.get("next")
#                     or None
#                 )
#             if not next_cursor:
#                 for k in ("next", "nextPageToken", "nextCursor", "next_page_token"):
#                     if j.get(k):
#                         next_cursor = str(j.get(k))
#                         break

#         else:  # MONDAY
#             cfgm = _cfg()["monday"]
#             api_url = cfgm["api_url"]

#             # If board_id is configured, use items_page on that board. Otherwise, fallback to account users.
#             board_id = (cfgm.get("board_id") or "").strip()
#             headers = {
#                 "Authorization": f"Bearer {acc.access_token}",
#                 "Content-Type": "application/json",
#             }

#             if board_id:
#                 # items_page with cursor-based pagination (limit up to 500; we honor <=100 like others)
#                 q = """
#                 query($board_id: [ID!], $limit: Int!, $cursor: String) {
#                   boards (ids: $board_id) {
#                     items_page (limit: $limit, cursor: $cursor) {
#                       cursor
#                       items {
#                         id
#                         name
#                         column_values {
#                           id
#                           text
#                           value
#                           column { id type title }
#                         }
#                       }
#                     }
#                   }
#                 }
#                 """
#                 vars_ = {
#                     "board_id": [int(board_id)],
#                     "limit": int(limit),
#                     "cursor": cursor if cursor not in (None, "", "null") else None,
#                 }
#                 r = await client.post(api_url, headers=headers, json={"query": q, "variables": vars_})
#                 if not r.is_success:
#                     raise HTTPException(r.status_code, f"monday items_page failed: {r.text[:300]}")
#                 j = r.json() or {}
#                 boards = (((j.get("data") or {}).get("boards")) or [])
#                 page = (boards[0].get("items_page") if boards else None) or {}
#                 next_cursor = page.get("cursor")
#                 raw_paging["cursor"] = next_cursor

#                 email_col = (cfgm.get("email_col") or "").strip()
#                 phone_col = (cfgm.get("phone_col") or "").strip()
#                 state_col = (cfgm.get("state_col") or "").strip()

#                 for it in (page.get("items") or []):
#                     name = it.get("name")
#                     email = None
#                     phone = None
#                     state = None
#                     # extract by configured column ids first, else by type
#                     for cv in (it.get("column_values") or []):
#                         cid = str(cv.get("id") or "")
#                         ctype = ((cv.get("column") or {}).get("type") or "").lower()
#                         text = cv.get("text")
#                         # prefer configured ids
#                         if email is None and (email_col and cid == email_col or (not email_col and ctype == "email")):
#                             email = text or email
#                         if phone is None and (phone_col and cid == phone_col or (not phone_col and ctype == "phone")):
#                             phone = text or phone
#                         if state is None and (state_col and cid == state_col):
#                             state = text or state
#                     items.append(_norm(it.get("id"), name, email, phone, state, it))

#             else:
#                 # fallback: list users (paged by page number)
#                 # Convert our opaque cursor into a simple page integer
#                 page_num = 1
#                 try:
#                     if cursor not in (None, "", "null"):
#                         page_num = max(1, int(str(cursor)))
#                 except Exception:
#                     page_num = 1

#                 q = """
#                 query($limit: Int!, $page: Int) {
#                   users (limit: $limit, page: $page) {
#                     id
#                     name
#                     email
#                   }
#                 }
#                 """
#                 vars_ = {"limit": int(limit), "page": page_num}
#                 r = await client.post(api_url, headers=headers, json={"query": q, "variables": vars_})
#                 if not r.is_success:
#                     raise HTTPException(r.status_code, f"monday users fetch failed: {r.text[:300]}")
#                 j = r.json() or {}
#                 users_ = ((j.get("data") or {}).get("users")) or []
#                 for u in users_:
#                     items.append(_norm(u.get("id"), u.get("name"), u.get("email"), None, None, u))
#                 # very simple paging heuristic: next page if we filled the page
#                 next_cursor = str(page_num + 1) if len(users_) >= int(limit) else None
#                 raw_paging["page"] = page_num

#     logger.info("contacts fetched crm=%s items=%s next=%s", crm, len(items), bool(next_cursor))
#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# # ─────────────────────────────────────────────────────────────────────────────
# # Treat Contacts as Leads -> auto-create "<CRM> Leads" file and upsert
# # ─────────────────────────────────────────────────────────────────────────────

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

# async def _fetch_all_contacts(user: User, crm: str) -> List[Dict[str, Any]]:
#     """Use our own /contacts endpoint to pull ALL pages."""
#     items: List[Dict[str, Any]] = []
#     cursor: Optional[str] = None
#     while True:
#         page = await fetch_contacts(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
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
#         logger.info("created file '%s' (id=%s) for user=%s", name, file.id, user.id)
#     return file

# async def _upsert_lead_from_contact(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
#     full_name = item.get("name")
#     first, last = _split_name(full_name)
#     email = item.get("email")
#     phone = _clean_phone(item.get("phone"))
#     external_id = item.get("id")
#     state = item.get("state")
#     raw = item.get("raw") or {}
#     company = (
#         raw.get("company")
#         or raw.get("organization")
#         or raw.get("companyName")
#         or raw.get("account")
#         or ""
#     )

#     existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
#     payload = {
#         "first_name": first or "",
#         "last_name": last or "",
#         "email": email,
#         "mobile": phone,
#         "state": state,
#         "salesforce_id": external_id,
#         "add_date": datetime.utcnow(),
#         "other_data": {
#             "Custom_0": company,
#             "Custom_1": f"source:{crm}"
#         }
#     }

#     if existing:
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

#     new = Lead(file=file, **payload)
#     await new.save()
#     return (True, False)

# # ─────────────────────────────────────────────────────────────────────────────
# # Sync endpoints
# # ─────────────────────────────────────────────────────────────────────────────

# async def _sync_one_crm(user: User, crm: str) -> Dict[str, Any]:
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")

#     label_map = {"hubspot": "HubSpot", "ghl": "GHL", "monday": "Monday"}
#     label = label_map.get(crm, crm)
#     file_name = f"{label} Leads"

#     file = await _ensure_file(user, file_name)

#     try:
#         items = await _fetch_all_contacts(user, crm)
#         created = 0
#         updated = 0
#         for it in items:
#             c, u = await _upsert_lead_from_contact(file, it, crm)
#             created += int(c)
#             updated += int(u)

#         logger.info("sync ok crm=%s file=%s fetched=%s created=%s updated=%s",
#                     crm, file.id, len(items), created, updated)

#         return {
#             "crm": crm,
#             "file_id": file.id,
#             "file_name": file.name,
#             "fetched_contacts": len(items),
#             "created_leads": created,
#             "updated_leads": updated,
#         }
#     except HTTPException as e:
#         logger.exception("sync http error crm=%s: %s", crm, e.detail)
#         return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e.detail)}
#     except Exception as e:
#         logger.exception("sync error crm=%s", crm)
#         return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e)}

# @router.post("/crm/ingest/hubspot")
# async def ingest_hubspot(user: User = Depends(get_current_user)):
#     out = await _sync_one_crm(user, "hubspot")
#     return {"success": True, "details": [out]}

# @router.post("/crm/ingest/ghl")
# async def ingest_ghl(user: User = Depends(get_current_user)):
#     out = await _sync_one_crm(user, "ghl")
#     return {"success": True, "details": [out]}

# # MONDAY: ingest endpoint
# @router.post("/crm/ingest/monday")
# async def ingest_monday(user: User = Depends(get_current_user)):
#     """Create/Update 'Monday Leads' and pull contacts (board items or users)."""
#     out = await _sync_one_crm(user, "monday")
#     return {"success": True, "details": [out]}

# @router.post("/crm/sync-to-files")
# async def sync_connected_crms_to_files(
#     user: User = Depends(get_current_user),
#     crm: Optional[str] = Query(None, description="Optional: 'hubspot' or 'ghl' or 'monday'"),
# ):
#     """
#     For each connected CRM:
#       - Ensure a file exists named '<CRM> Leads'
#       - Fetch ALL CONTACTS
#       - Upsert them into the file as Leads (no duplicates on rerun)
#     """
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
#         results.append(await _sync_one_crm(user, acc.crm))

#     return {"success": True, "ran": len(connected), "details": results}


























# import os
# import json
# import secrets
# import logging
# from datetime import datetime, timedelta, timezone
# from typing import Optional, Dict, Any, List, Tuple
# from urllib.parse import urlparse, urlencode, urlsplit, urlunsplit, parse_qsl, quote_plus

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
# from fastapi.responses import RedirectResponse, JSONResponse

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.crm import IntegrationAccount, IntegrationOAuthState
# from models.file import File as FileModel
# from models.lead import Lead

# router = APIRouter()
# logger = logging.getLogger("crm")

# # ─────────────────────────────────────────────────────────────────────────────
# # Config (HubSpot + GHL + MONDAY)
# # ─────────────────────────────────────────────────────────────────────────────

# def _cfg() -> Dict[str, Dict[str, str]]:
#     return {
#         "hubspot": {
#             "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
#             "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
#             "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
#             "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
#             "scope": os.getenv(
#                 "HUBSPOT_SCOPES",
#                 "crm.objects.contacts.read crm.objects.contacts.write oauth"
#             ),
#             "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
#             "type": "oauth",
#         },
#         "ghl": {
#             "install_url": os.getenv("GHL_INSTALL_URL", ""),
#             "install_base": os.getenv("GHL_INSTALL_BASE", "https://marketplace.gohighlevel.com"),
#             "auth_path": "/oauth/chooselocation",
#             "token_url": os.getenv("GHL_TOKEN_URL", "https://services.leadconnectorhq.com/oauth/token"),
#             "contacts_url": os.getenv("GHL_CONTACTS_URL", "https://services.leadconnectorhq.com/contacts/"),
#             "client_id": os.getenv("GHL_CLIENT_ID", ""),
#             "client_secret": os.getenv("GHL_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("GHL_REDIRECT_URI", ""),
#             "scope": os.getenv("GHL_SCOPES", "contacts.readonly contacts.write"),
#             "type": "oauth",
#         },
#         # MONDAY: OAuth & GraphQL API (multi-tenant friendly)
#         "monday": {
#             "auth_url": os.getenv("MONDAY_AUTH_URL", "https://auth.monday.com/oauth2/authorize"),
#             "token_url": os.getenv("MONDAY_TOKEN_URL", "https://auth.monday.com/oauth2/token"),
#             "api_url": os.getenv("MONDAY_API_URL", "https://api.monday.com/v2"),
#             "client_id": os.getenv("MONDAY_CLIENT_ID", ""),
#             "client_secret": os.getenv("MONDAY_CLIENT_SECRET", ""),
#             "redirect_uri": os.getenv("MONDAY_REDIRECT_URI", ""),
#             "scope": os.getenv("MONDAY_SCOPES", ""),
#             # Leads board config (per-account; we auto-discover by name if id not set)
#             "board_id": os.getenv("MONDAY_BOARD_ID", ""),
#             "board_name": os.getenv("MONDAY_BOARD_NAME", ""),          # e.g., "Leads"
#             "email_col": os.getenv("MONDAY_EMAIL_COLUMN_ID", ""),
#             "phone_col": os.getenv("MONDAY_PHONE_COLUMN_ID", ""),
#             "state_col": os.getenv("MONDAY_STATE_COLUMN_ID", ""),
#             "owner_col": os.getenv("MONDAY_OWNER_COLUMN_ID", ""),      # People/Owner column id
#             # install behavior
#             # IMPORTANT: We do NOT lock to a subdomain; any user can connect their own Monday account.
#             "force_install_if_needed": (os.getenv("MONDAY_FORCE_INSTALL_IF_NEEDED", "true") or "").lower() != "false",
#             "type": "oauth",
#         },
#     }

# SUPPORTED = ("hubspot", "ghl", "monday")

# # ─────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────────────────────────────────────

# def _now() -> datetime:
#     return datetime.now(timezone.utc)

# def _exp_from_seconds(seconds: int) -> datetime:
#     return _now() + timedelta(seconds=max(0, seconds - 60))

# def _sanitize_redirect(back: str) -> str:
#     if back and back.startswith("/") and not back.startswith("//"):
#         return back
#     allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
#     if back and allowed:
#         p = urlparse(back)
#         origin = f"{p.scheme}://{p.netloc}"
#         if origin in allowed:
#             return back
#     return "/user/CRM"

# def _append_qs(url: str, params: Dict[str, str]) -> str:
#     parts = list(urlsplit(url))
#     q = dict(parse_qsl(parts[3], keep_blank_values=True))
#     q.update({k: v for k, v in params.items() if v is not None})
#     parts[3] = urlencode(q)
#     return urlunsplit(parts)

# # ─────────────────────────────────────────────────────────────────────────────
# # Token verification
# # ─────────────────────────────────────────────────────────────────────────────

# async def _verify_and_fill_account(crm: str, acc: IntegrationAccount) -> None:
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
#                 logger.info("hubspot verify ok hub_id=%s user=%s",
#                             acc.external_account_id, acc.external_account_name)
#             else:
#                 r2 = await client.get(
#                     "https://api.hubapi.com/crm/v3/owners?limit=1",
#                     headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 )
#                 if not r2.is_success:
#                     logger.error("hubspot verify failed: %s %s", r.status_code, r.text[:200])
#                     raise HTTPException(401, "HubSpot token validation failed.")

#         elif crm == "ghl":
#             contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
#             probe = f"{contacts_url}?limit=1"
#             r = await client.get(
#                 probe,
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#             )
#             if not r.is_success:
#                 logger.error("GHL verify failed: %s %s", r.status_code, r.text[:200])
#                 raise HTTPException(401, "GHL token validation failed.")
#             try:
#                 _ = r.json()
#             except Exception:
#                 pass
#             acc.external_account_name = acc.external_account_name or "GHL"
#             logger.info("GHL verify ok")

#         elif crm == "monday":
#             # Verify with GraphQL `me`
#             q = """
#             query {
#               me {
#                 id
#                 name
#                 email
#                 account { id name }
#               }
#             }
#             """
#             r = await client.post(
#                 _cfg()["monday"]["api_url"],
#                 headers={
#                     "Authorization": f"Bearer {acc.access_token}",
#                     "Content-Type": "application/json",
#                 },
#                 json={"query": q},
#             )
#             if not r.is_success:
#                 logger.error("monday verify failed: %s %s", r.status_code, r.text[:200])
#                 raise HTTPException(401, "monday token validation failed.")
#             j = r.json()
#             me = ((j or {}).get("data") or {}).get("me") or {}
#             if not me:
#                 logger.error("monday verify: empty `me`")
#                 raise HTTPException(401, "monday token validation failed.")
#             acct = me.get("account") or {}
#             acc.external_account_id = str(acct.get("id") or "")
#             acc.external_account_name = acct.get("name") or me.get("email") or me.get("name") or "monday"
#             logger.info("monday verify ok account_id=%s name=%s",
#                         acc.external_account_id, acc.external_account_name)

#         else:
#             raise HTTPException(400, "Unsupported CRM for verification")

# # ─────────────────────────────────────────────────────────────────────────────
# # Refresh tokens (OAuth2)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
#     SKEW_SECONDS = 120
#     if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
#         return acc

#     cfg = _cfg()[crm]
#     # MONDAY: tokens do not expire and no refresh_token is issued.
#     if not acc.refresh_token:
#         logger.debug("%s: no refresh_token present; assuming still valid", crm)
#         return acc

#     data: Dict[str, Any] = {
#         "grant_type": "refresh_token",
#         "refresh_token": acc.refresh_token,
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             logger.error("%s refresh failed: %s %s", crm, r.status_code, r.text[:300])
#             raise HTTPException(401, f"{crm} refresh failed: {r.text}")
#         j = r.json()

#     def _get_exp(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     acc.access_token = j.get("access_token") or acc.access_token
#     acc.refresh_token = acc.refresh_token or j.get("refresh_token")
#     acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
#     await acc.save()
#     logger.info("%s refreshed; exp=%s", crm, acc.expires_at)
#     return acc

# # ─────────────────────────────────────────────────────────────────────────────
# # Public routes
# # ─────────────────────────────────────────────────────────────────────────────

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
#     redirect_to: Optional[str] = Body(default="/user/CRM", embed=True),
# ):
#     """
#     Starts OAuth:
#       • HubSpot: standard authorize URL.
#       • GHL: Marketplace Install link or build from parts.
#       • monday: standard OAuth authorize URL — **no admin invite / no subdomain lock**.
#         Any user can install/connect their own Monday account. If the app is not installed,
#         the OAuth screen will prompt install automatically (force_install_if_needed=true).
#     """
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")

#     cfg = _cfg()[crm]
#     if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
#         raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

#     state = secrets.token_urlsafe(24)
#     await IntegrationOAuthState.create(
#         user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/user/CRM")
#     )

#     if crm == "hubspot":
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "scope": cfg["scope"],
#             "state": state,
#         }
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     elif crm == "ghl":
#         install_url = (cfg["install_url"] or "").strip()
#         if install_url:
#             auth_url = _append_qs(install_url, {"state": state})
#         else:
#             built = f'{cfg["install_base"].rstrip("/")}{cfg["auth_path"]}'
#             params = {
#                 "response_type": "code",
#                 "redirect_uri": cfg["redirect_uri"],
#                 "client_id": cfg["client_id"],
#                 "scope": cfg["scope"],
#                 "state": state,
#             }
#             auth_url = f"{built}?{urlencode(params)}"

#     else:  # MONDAY (multi-tenant; do not restrict to a subdomain)
#         params = {
#             "client_id": cfg["client_id"],
#             "redirect_uri": cfg["redirect_uri"],
#             "response_type": "code",
#             "state": state,
#             # Always allow install during OAuth so *any* user can connect without admin invites.
#             "force_install_if_needed": "true" if cfg.get("force_install_if_needed") else "false",
#         }
#         # Optional explicit scopes (if provided) – otherwise Monday uses app-configured scopes
#         if cfg.get("scope"):
#             params["scope"] = cfg["scope"]

#         # NOTE: We intentionally do NOT pass any subdomain param here.
#         auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

#     logger.info("oauth start crm=%s user=%s state=%s", crm, user.id, state)
#     return {"auth_url": auth_url}

# @router.get("/crm/callback/{crm}")
# async def oauth_callback(
#     crm: str,
#     code: Optional[str] = Query(None),
#     state: Optional[str] = Query(None),
#     error: Optional[str] = Query(None),
#     background_tasks: BackgroundTasks = None,
# ):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

#     st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
#     if not st:
#         return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

#     back = _sanitize_redirect(st.redirect_to or "/user/CRM")
#     cfg = _cfg()[crm]

#     if error:
#         await st.delete()
#         logger.warning("oauth error crm=%s state=%s error=%s", crm, state, error)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

#     if not code:
#         await st.delete()
#         logger.warning("oauth no_code crm=%s state=%s", crm, state)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

#     data = {
#         "grant_type": "authorization_code",
#         "code": code,
#         "redirect_uri": cfg["redirect_uri"],
#         "client_id": cfg["client_id"],
#         "client_secret": cfg["client_secret"],
#     }

#     logger.info("oauth exchanging code crm=%s state=%s", crm, state)
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(cfg["token_url"], data=data)
#         if not r.is_success:
#             await st.delete()
#             logger.error("oauth token exchange failed crm=%s status=%s body=%s",
#                          crm, r.status_code, r.text[:300])
#             return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=token_exchange_failed")
#         j = r.json()

#     acc = await IntegrationAccount.get_or_none(user_id=st.user_id, crm=crm)
#     if not acc:
#         acc = await IntegrationAccount.create(user_id=st.user_id, crm=crm)

#     def _as_int(v, default=3600):
#         try:
#             return int(v)
#         except Exception:
#             return default

#     acc.access_token = j.get("access_token")
#     # MONDAY: no refresh token & tokens typically long-lived
#     if crm == "monday":
#         acc.refresh_token = None
#         acc.expires_at = None
#     else:
#         acc.refresh_token = j.get("refresh_token") or acc.refresh_token
#         acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
#     await acc.save()

#     try:
#         await _verify_and_fill_account(crm, acc)
#     except HTTPException as e:
#         await acc.save()
#         await st.delete()
#         logger.error("oauth verify failed crm=%s detail=%s", crm, e.detail)
#         return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

#     acc.is_active = True
#     await acc.save()

#     # Auto-ingest Monday leads right after successful auth (non-blocking)
#     if crm == "monday" and background_tasks is not None:
#         user_obj = await User.get(id=st.user_id)
#         background_tasks.add_task(_sync_one_crm, user_obj, "monday")

#     await st.delete()
#     logger.info("oauth success crm=%s user=%s", crm, acc.user_id if hasattr(acc, "user_id") else st.user_id)
#     return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# @router.delete("/crm/disconnect/{crm}")
# async def disconnect(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc.is_active = False
#     await acc.save()
#     logger.info("disconnected crm=%s user=%s", crm, user.id)
#     return {"success": True, "message": f"Disconnected {crm}."}

# @router.post("/crm/ensure-fresh/{crm}")
# async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
#     if not acc:
#         raise HTTPException(404, "Not connected.")
#     acc = await _ensure_fresh_token(crm, acc)
#     return {"success": True, "expires_at": acc.expires_at}

# # ─────────────────────────────────────────────────────────────────────────────
# # Contacts/Leads fetchers (normalize to Lead-like rows)
# # ─────────────────────────────────────────────────────────────────────────────

# async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")
#     await _ensure_fresh_token(crm.lower(), acc)
#     return acc

# def _norm(
#     id: Any,
#     name: Optional[str] = None,
#     email: Optional[str] = None,
#     phone: Optional[str] = None,
#     state: Optional[str] = None,
#     extra: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     return {
#         "id": (str(id) if id is not None else None),
#         "name": (name or "") or None,
#         "email": email,
#         "phone": phone,
#         "state": state,
#         "raw": extra or {},
#     }

# @router.get("/crm/{crm}/contacts")
# async def fetch_contacts(
#     crm: str,
#     user: User = Depends(get_current_user),
#     limit: int = Query(25, ge=1, le=100),
#     cursor: Optional[str] = Query(None, description="Opaque paging cursor/token"),
# ):
#     """
#     HubSpot/GHL: contacts.
#     Monday: **current user's leads** from a Leads board (NOT account users).
#            Every user only sees their own leads.
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
#             params = {"limit": limit, "properties": "firstname,lastname,email,phone,company,state"}
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
#                 items.append(_norm(o.get("id"), name or None, p.get("email"), p.get("phone"), p.get("state"), o))
#             next_cursor = ((j.get("paging") or {}).get("next") or {}).get("after")
#             raw_paging = j.get("paging") or {}

#         elif crm == "ghl":
#             contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
#             url = contacts_url
#             params = {"limit": limit}
#             if cursor:
#                 params.update({"cursor": cursor, "nextPageToken": cursor, "page": cursor})

#             r = await client.get(
#                 url,
#                 headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
#                 params=params,
#             )
#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"GHL contacts fetch failed: {r.text[:300]}")
#             j = r.json() if r.text else {}

#             data_list = None
#             for key in ("contacts", "data", "items", "results"):
#                 if isinstance(j.get(key), list):
#                     data_list = j.get(key)
#                     break
#             if data_list is None and isinstance(j, list):
#                 data_list = j

#             for c in (data_list or []):
#                 cid = c.get("id") or c.get("_id") or c.get("contactId")
#                 first = c.get("firstName") or c.get("first_name")
#                 last = c.get("lastName") or c.get("last_name")
#                 full = c.get("name") or " ".join(x for x in [first, last] if x)
#                 email = c.get("email")
#                 phone = c.get("phone") or c.get("phoneNumber") or c.get("phone_number")
#                 state = (
#                     c.get("state")
#                     or (c.get("address", {}) or {}).get("state")
#                     or c.get("region")
#                     or None
#                 )
#                 items.append(_norm(cid, full or None, email, phone, state, c))

#             if isinstance(j.get("meta"), dict):
#                 meta = j["meta"]
#                 raw_paging["meta"] = meta
#                 next_cursor = (
#                     meta.get("nextPageToken")
#                     or meta.get("next_token")
#                     or meta.get("next")
#                     or None
#                 )
#             if not next_cursor:
#                 for k in ("next", "nextPageToken", "nextCursor", "next_page_token"):
#                     if j.get(k):
#                         next_cursor = str(j.get(k))
#                         break

#         else:  # MONDAY -> fetch **user's leads** from a Leads board
#             cfgm = _cfg()["monday"]
#             api_url = cfgm["api_url"]
#             headers = {
#                 "Authorization": f"Bearer {acc.access_token}",
#                 "Content-Type": "application/json",
#             }

#             # me.id (for owner/creator filtering)
#             q_me = "query { me { id } }"
#             r_me = await client.post(api_url, headers=headers, json={"query": q_me})
#             if not r_me.is_success:
#                 raise HTTPException(r_me.status_code, f"monday me() failed: {r_me.text[:300]}")
#             me_id = str(((r_me.json() or {}).get("data") or {}).get("me", {}).get("id") or "")

#             board_id = (cfgm.get("board_id") or "").strip()
#             board_name = (cfgm.get("board_name") or "").strip()

#             async def _discover_board_id(name_hint: str) -> Optional[int]:
#                 if not name_hint:
#                     return None
#                 q_boards = """
#                 query {
#                   boards (limit: 200) { id name }
#                 }
#                 """
#                 rb = await client.post(api_url, headers=headers, json={"query": q_boards})
#                 if not rb.is_success:
#                     return None
#                 bj = rb.json() or {}
#                 for b in ((bj.get("data") or {}).get("boards") or []):
#                     try:
#                         if str(b.get("name") or "").strip().lower() == name_hint.strip().lower():
#                             return int(b["id"])
#                     except Exception:
#                         continue
#                 return None

#             if not board_id:
#                 # Try MONDAY_BOARD_NAME, then a few common defaults
#                 found = await _discover_board_id(board_name) if board_name else None
#                 if not found:
#                     for candidate in ("Leads", "leads", "CRM Leads", "Sales Leads"):
#                         found = await _discover_board_id(candidate)
#                         if found:
#                             break
#                 if not found:
#                     raise HTTPException(
#                         400,
#                         "monday: Leads board not found. Set MONDAY_BOARD_ID/MONDAY_BOARD_NAME or create a 'Leads' board.",
#                     )
#                 board_id = str(found)

#             # Pull items with cursor paging
#             q_items = """
#             query($board_id: [ID!], $limit: Int!, $cursor: String) {
#               boards(ids: $board_id) {
#                 items_page(limit: $limit, cursor: $cursor) {
#                   cursor
#                   items {
#                     id
#                     name
#                     creator_id
#                     column_values {
#                       id
#                       text
#                       value
#                       column { id type title }
#                     }
#                   }
#                 }
#               }
#             }
#             """
#             vars_ = {
#                 "board_id": [int(board_id)],
#                 "limit": int(limit),
#                 "cursor": cursor if cursor not in (None, "", "null") else None,
#             }
#             ri = await client.post(api_url, headers=headers, json={"query": q_items, "variables": vars_})
#             if not ri.is_success:
#                 raise HTTPException(ri.status_code, f"monday items_page failed: {ri.text[:300]}")
#             ji = ri.json() or {}
#             boards = ((ji.get("data") or {}).get("boards")) or []
#             page = (boards[0].get("items_page") if boards else None) or {}
#             next_cursor = page.get("cursor")
#             raw_paging["cursor"] = next_cursor

#             email_col = (cfgm.get("email_col") or "").strip()
#             phone_col = (cfgm.get("phone_col") or "").strip()
#             state_col = (cfgm.get("state_col") or "").strip()
#             owner_col = (cfgm.get("owner_col") or "").strip()

#             def _owned_by_me(cv_list: List[Dict[str, Any]]) -> bool:
#                 """True if owner_col (people) contains me_id."""
#                 if not owner_col:
#                     return False
#                 for cv in cv_list or []:
#                     if str(cv.get("id") or "") == owner_col:
#                         try:
#                             v = cv.get("value")
#                             data = json.loads(v) if isinstance(v, str) and v else (v if isinstance(v, dict) else {})
#                             persons = (data.get("personsAndTeams") or []) or data.get("persons") or []
#                             for p in persons:
#                                 if str(p.get("id")) == me_id and (p.get("kind") in (None, "person")):
#                                     return True
#                         except Exception:
#                             return False
#                 return False

#             for it in (page.get("items") or []):
#                 cv_list = it.get("column_values") or []

#                 # ENFORCED: every user sees only **their** leads
#                 if owner_col:
#                     if not _owned_by_me(cv_list):
#                         continue
#                 else:
#                     # fallback to creator_id check
#                     try:
#                         if str(it.get("creator_id")) != me_id:
#                             continue
#                     except Exception:
#                         continue  # if creator_id missing, be safe: exclude

#                 name = it.get("name")
#                 email = None
#                 phone = None
#                 state = None
#                 for cv in cv_list:
#                     cid = str(cv.get("id") or "")
#                     ctype = ((cv.get("column") or {}).get("type") or "").lower()
#                     text = cv.get("text")
#                     if email is None and (email_col and cid == email_col or (not email_col and ctype == "email")):
#                         email = text or email
#                     if phone is None and (phone_col and cid == phone_col or (not phone_col and ctype == "phone")):
#                         phone = text or phone
#                     if state is None and (state_col and cid == state_col):
#                         state = text or state

#                 items.append(_norm(it.get("id"), name, email, phone, state, it))

#     logger.info("contacts/leads fetched crm=%s items=%s next=%s", crm, len(items), bool(next_cursor))
#     return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# # ─────────────────────────────────────────────────────────────────────────────
# # Treat Contacts as Leads -> auto-create "<CRM> Leads" file and upsert
# # ─────────────────────────────────────────────────────────────────────────────

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

# async def _fetch_all_contacts(user: User, crm: str) -> List[Dict[str, Any]]:
#     """Use our own /contacts endpoint to pull ALL pages (already user-scoped for Monday)."""
#     items: List[Dict[str, Any]] = []
#     cursor: Optional[str] = None
#     while True:
#         page = await fetch_contacts(crm=crm, user=user, limit=100, cursor=cursor)  # type: ignore
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
#         logger.info("created file '%s' (id=%s) for user=%s", name, file.id, user.id)
#     return file

# async def _upsert_lead_from_contact(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
#     full_name = item.get("name")
#     first, last = _split_name(full_name)
#     email = item.get("email")
#     phone = _clean_phone(item.get("phone"))
#     external_id = item.get("id")
#     state = item.get("state")
#     raw = item.get("raw") or {}
#     company = (
#         raw.get("company")
#         or raw.get("organization")
#         or raw.get("companyName")
#         or raw.get("account")
#         or ""
#     )

#     existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
#     payload = {
#         "first_name": first or "",
#         "last_name": last or "",
#         "email": email,
#         "mobile": phone,
#         "state": state,
#         "salesforce_id": external_id,
#         "add_date": datetime.utcnow(),
#         "other_data": {
#             "Custom_0": company,
#             "Custom_1": f"source:{crm}"
#         }
#     }

#     if existing:
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

#     new = Lead(file=file, **payload)
#     await new.save()
#     return (True, False)

# # ─────────────────────────────────────────────────────────────────────────────
# # Sync endpoints
# # ─────────────────────────────────────────────────────────────────────────────

# async def _sync_one_crm(user: User, crm: str) -> Dict[str, Any]:
#     crm = crm.lower()
#     if crm not in SUPPORTED:
#         raise HTTPException(400, "Unsupported CRM")
#     acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
#     if not acc:
#         raise HTTPException(404, f"Not connected to {crm}.")

#     label_map = {"hubspot": "HubSpot", "ghl": "GHL", "monday": "Monday"}
#     label = label_map.get(crm, crm)
#     file_name = f"{label} Leads"

#     file = await _ensure_file(user, file_name)

#     try:
#         items = await _fetch_all_contacts(user, crm)
#         created = 0
#         updated = 0
#         for it in items:
#             c, u = await _upsert_lead_from_contact(file, it, crm)
#             created += int(c)
#             updated += int(u)

#         logger.info("sync ok crm=%s file=%s fetched=%s created=%s updated=%s",
#                     crm, file.id, len(items), created, updated)

#         return {
#             "crm": crm,
#             "file_id": file.id,
#             "file_name": file.name,
#             "fetched_contacts": len(items),
#             "created_leads": created,
#             "updated_leads": updated,
#         }
#     except HTTPException as e:
#         logger.exception("sync http error crm=%s: %s", crm, e.detail)
#         return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e.detail)}
#     except Exception as e:
#         logger.exception("sync error crm=%s", crm)
#         return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e)}

# @router.post("/crm/ingest/hubspot")
# async def ingest_hubspot(user: User = Depends(get_current_user)):
#     out = await _sync_one_crm(user, "hubspot")
#     return {"success": True, "details": [out]}

# @router.post("/crm/ingest/ghl")
# async def ingest_ghl(user: User = Depends(get_current_user)):
#     out = await _sync_one_crm(user, "ghl")
#     return {"success": True, "details": [out]}

# @router.post("/crm/ingest/monday")
# async def ingest_monday(user: User = Depends(get_current_user)):
#     """Create/Update 'Monday Leads' and pull the *current user's* leads from the configured board."""
#     out = await _sync_one_crm(user, "monday")
#     return {"success": True, "details": [out]}

# @router.post("/crm/sync-to-files")
# async def sync_connected_crms_to_files(
#     user: User = Depends(get_current_user),
#     crm: Optional[str] = Query(None, description="Optional: 'hubspot' or 'ghl' or 'monday'"),
# ):
#     """
#     For each connected CRM:
#       - Ensure a file exists named '<CRM> Leads'
#       - Fetch ALL (scoped) contacts/leads
#       - Upsert them into the file as Leads (no duplicates on rerun)
#     """
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
#         results.append(await _sync_one_crm(user, acc.crm))

#     return {"success": True, "ran": len(connected), "details": results}









import os
import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, urlencode, urlsplit, urlunsplit, parse_qsl, quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel

from helpers.token_helper import get_current_user
from models.auth import User
from models.crm import IntegrationAccount, IntegrationOAuthState
from models.file import File as FileModel
from models.lead import Lead

router = APIRouter()
logger = logging.getLogger("crm")

# ─────────────────────────────────────────────────────────────────────────────
# Config (HubSpot + GHL + Monday)
# ─────────────────────────────────────────────────────────────────────────────

def _cfg() -> Dict[str, Dict[str, str]]:
    return {
        "hubspot": {
            "auth_url": os.getenv("HUBSPOT_AUTH_URL", "https://app.hubspot.com/oauth/authorize"),
            "token_url": os.getenv("HUBSPOT_TOKEN_URL", "https://api.hubapi.com/oauth/v1/token"),
            "client_id": os.getenv("HUBSPOT_CLIENT_ID", ""),
            "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", ""),
            "scope": os.getenv(
                "HUBSPOT_SCOPES",
                "crm.objects.contacts.read crm.objects.contacts.write oauth"
            ),
            "verify_url": os.getenv("HUBSPOT_VERIFY_URL", "https://api.hubapi.com/oauth/v1/access-tokens"),
            "type": "oauth",
        },
        "ghl": {
            "install_url": os.getenv("GHL_INSTALL_URL", ""),
            "install_base": os.getenv("GHL_INSTALL_BASE", "https://marketplace.gohighlevel.com"),
            "auth_path": "/oauth/chooselocation",
            "token_url": os.getenv("GHL_TOKEN_URL", "https://services.leadconnectorhq.com/oauth/token"),
            "contacts_url": os.getenv("GHL_CONTACTS_URL", "https://services.leadconnectorhq.com/contacts/"),
            "client_id": os.getenv("GHL_CLIENT_ID", ""),
            "client_secret": os.getenv("GHL_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("GHL_REDIRECT_URI", ""),
            "scope": os.getenv("GHL_SCOPES", "contacts.readonly contacts.write"),
            "type": "oauth",
        },
        # MONDAY
        "monday": {
            "auth_url": os.getenv("MONDAY_AUTH_URL", "https://auth.monday.com/oauth2/authorize"),
            "token_url": os.getenv("MONDAY_TOKEN_URL", "https://auth.monday.com/oauth2/token"),
            "api_url": os.getenv("MONDAY_API_URL", "https://api.monday.com/v2"),
            "client_id": os.getenv("MONDAY_CLIENT_ID", ""),
            "client_secret": os.getenv("MONDAY_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv("MONDAY_REDIRECT_URI", ""),
            "scope": os.getenv("MONDAY_SCOPES", ""),
            # Optional owner column for per-user privacy (people column id)
            "owner_col": os.getenv("MONDAY_OWNER_COLUMN_ID", ""),
            # Optional IDs to help pick email/phone/state columns
            "email_col": os.getenv("MONDAY_EMAIL_COLUMN_ID", ""),
            "phone_col": os.getenv("MONDAY_PHONE_COLUMN_ID", ""),
            "state_col": os.getenv("MONDAY_STATE_COLUMN_ID", ""),
            # subdomain targeting + install behavior
            "subdomain": os.getenv("MONDAY_SUBDOMAIN", ""),
            "subdomain_strategy": os.getenv("MONDAY_SUBDOMAIN_STRATEGY", "param"),  # "param" | "host"
            "force_install_if_needed": (os.getenv("MONDAY_FORCE_INSTALL_IF_NEEDED", "false") or "").lower() == "true",
            "type": "oauth",
        },
    }

SUPPORTED = ("hubspot", "ghl", "monday")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _exp_from_seconds(seconds: int) -> datetime:
    return _now() + timedelta(seconds=max(0, seconds - 60))

def _sanitize_redirect(back: str) -> str:
    if back and back.startswith("/") and not back.startswith("//"):
        return back
    allowed = set((os.getenv("ALLOWED_REDIRECT_ORIGINS") or "").split(",")) - {""}
    if back and allowed:
        p = urlparse(back)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in allowed:
            return back
    return "/user/CRM"

def _append_qs(url: str, params: Dict[str, str]) -> str:
    parts = list(urlsplit(url))
    q = dict(parse_qsl(parts[3], keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v is not None})
    parts[3] = urlencode(q)
    return urlunsplit(parts)

def _acc_meta(acc: IntegrationAccount) -> Dict[str, Any]:
    md = acc.metadata if hasattr(acc, "metadata") and isinstance(acc.metadata, dict) else {}
    return md or {}

async def _save_acc_meta(acc: IntegrationAccount, meta: Dict[str, Any]) -> None:
    acc.metadata = meta
    await acc.save()

# ─────────────────────────────────────────────────────────────────────────────
# Token verification
# ─────────────────────────────────────────────────────────────────────────────

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
                logger.info("hubspot verify ok hub_id=%s user=%s",
                            acc.external_account_id, acc.external_account_name)
            else:
                r2 = await client.get(
                    "https://api.hubapi.com/crm/v3/owners?limit=1",
                    headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                )
                if not r2.is_success:
                    logger.error("hubspot verify failed: %s %s", r.status_code, r.text[:200])
                    raise HTTPException(401, "HubSpot token validation failed.")

        elif crm == "ghl":
            contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
            probe = f"{contacts_url}?limit=1"
            r = await client.get(
                probe,
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
            )
            if not r.is_success:
                logger.error("GHL verify failed: %s %s", r.status_code, r.text[:200])
                raise HTTPException(401, "GHL token validation failed.")
            acc.external_account_name = acc.external_account_name or "GHL"
            logger.info("GHL verify ok")

        elif crm == "monday":
            q = """
            query {
              me {
                id
                name
                email
                account { id name }
              }
            }
            """
            r = await client.post(
                _cfg()["monday"]["api_url"],
                headers={
                    "Authorization": f"Bearer {acc.access_token}",
                    "Content-Type": "application/json",
                },
                json={"query": q},
            )
            if not r.is_success:
                logger.error("monday verify failed: %s %s", r.status_code, r.text[:200])
                raise HTTPException(401, "monday token validation failed.")
            j = r.json()
            me = ((j or {}).get("data") or {}).get("me") or {}
            if not me:
                logger.error("monday verify: empty `me`")
                raise HTTPException(401, "monday token validation failed.")
            acct = me.get("account") or {}
            acc.external_account_id = str(acct.get("id") or "")
            acc.external_account_name = acct.get("name") or me.get("email") or me.get("name") or "monday"
            logger.info("monday verify ok account_id=%s name=%s",
                        acc.external_account_id, acc.external_account_name)

        else:
            raise HTTPException(400, "Unsupported CRM for verification")

# ─────────────────────────────────────────────────────────────────────────────
# Refresh tokens (OAuth2)
# ─────────────────────────────────────────────────────────────────────────────

async def _ensure_fresh_token(crm: str, acc: IntegrationAccount) -> IntegrationAccount:
    SKEW_SECONDS = 120
    if acc.expires_at and (acc.expires_at - _now()).total_seconds() > SKEW_SECONDS:
        return acc

    cfg = _cfg()[crm]
    # MONDAY: tokens do not expire and no refresh_token is issued.
    if not acc.refresh_token:
        logger.debug("%s: no refresh_token present; assuming still valid", crm)
        return acc

    data: Dict[str, Any] = {
        "grant_type": "refresh_token",
        "refresh_token": acc.refresh_token,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(cfg["token_url"], data=data)
        if not r.is_success:
            logger.error("%s refresh failed: %s %s", crm, r.status_code, r.text[:300])
            raise HTTPException(401, f"{crm} refresh failed: {r.text}")
        j = r.json()

    def _get_exp(v, default=3600):
        try:
            return int(v)
        except Exception:
            return default

    acc.access_token = j.get("access_token") or acc.access_token
    acc.refresh_token = acc.refresh_token or j.get("refresh_token")
    acc.expires_at = _exp_from_seconds(_get_exp(j.get("expires_in", 3600)))
    await acc.save()
    logger.info("%s refreshed; exp=%s", crm, acc.expires_at)
    return acc

# ─────────────────────────────────────────────────────────────────────────────
# Public routes (generic)
# ─────────────────────────────────────────────────────────────────────────────

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
            "metadata": (r.metadata if hasattr(r, "metadata") else None),
        } for r in rows
    ]

# ─────────────────────────────────────────────────────────────────────────────
# OAuth start/callback
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/crm/connect/{crm}")
async def start_connect(
    crm: str,
    user: User = Depends(get_current_user),
    redirect_to: Optional[str] = Body(default="/user/CRM", embed=True),
):
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")

    cfg = _cfg()[crm]
    if not all([cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"]]):
        raise HTTPException(500, f"{crm} OAuth app not configured (env missing).")

    state = secrets.token_urlsafe(24)
    await IntegrationOAuthState.create(
        user=user, crm=crm, state=state, redirect_to=_sanitize_redirect(redirect_to or "/user/CRM")
    )

    if crm == "hubspot":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

    elif crm == "ghl":
        install_url = (cfg["install_url"] or "").strip()
        if install_url:
            auth_url = _append_qs(install_url, {"state": state})
        else:
            built = f'{cfg["install_base"].rstrip("/")}{cfg["auth_path"]}'
            params = {
                "response_type": "code",
                "redirect_uri": cfg["redirect_uri"],
                "client_id": cfg["client_id"],
                "scope": cfg["scope"],
                "state": state,
            }
            auth_url = f"{built}?{urlencode(params)}"

    else:  # monday
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "state": state,
        }
        if cfg.get("scope"):
            params["scope"] = cfg["scope"]
        if cfg.get("force_install_if_needed"):
            params["force_install_if_needed"] = "true"

        sub = (cfg.get("subdomain") or "").strip()
        strat = (cfg.get("subdomain_strategy") or "param").lower()
        if sub:
            if strat == "host":
                base = f"https://{sub}.monday.com/oauth2/authorize"
                auth_url = f"{base}?{httpx.QueryParams(params)}"
            else:
                params["subdomain"] = sub
                auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'
        else:
            auth_url = f'{cfg["auth_url"]}?{httpx.QueryParams(params)}'

    logger.info("oauth start crm=%s user=%s state=%s", crm, user.id, state)
    return {"auth_url": auth_url}

@router.get("/crm/callback/{crm}")
async def oauth_callback(
    crm: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    background_tasks: BackgroundTasks = None,
):
    crm = crm.lower()
    if crm not in SUPPORTED:
        return JSONResponse(status_code=400, content={"detail": "Unsupported CRM or wrong flow."})

    st = await IntegrationOAuthState.get_or_none(state=state, crm=crm)
    if not st:
        return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})

    back = _sanitize_redirect(st.redirect_to or "/user/CRM")
    cfg = _cfg()[crm]

    if error:
        await st.delete()
        logger.warning("oauth error crm=%s state=%s error=%s", crm, state, error)
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(error)}")

    if not code:
        await st.delete()
        logger.warning("oauth no_code crm=%s state=%s", crm, state)
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason=no_code")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }

    logger.info("oauth exchanging code crm=%s state=%s", crm, state)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(cfg["token_url"], data=data)
        if not r.is_success:
            await st.delete()
            logger.error("oauth token exchange failed crm=%s status=%s body=%s",
                         crm, r.status_code, r.text[:300])
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

    acc.access_token = j.get("access_token")
    if crm == "monday":
        acc.refresh_token = None
        acc.expires_at = None
    else:
        acc.refresh_token = j.get("refresh_token") or acc.refresh_token
        acc.expires_at = _exp_from_seconds(_as_int(j.get("expires_in", 3600)))
    await acc.save()

    try:
        await _verify_and_fill_account(crm, acc)
    except HTTPException as e:
        await acc.save()
        await st.delete()
        logger.error("oauth verify failed crm=%s detail=%s", crm, e.detail)
        return RedirectResponse(url=f"{back}?crm={crm}&status=error&reason={quote_plus(str(e.detail))}")

    acc.is_active = True
    if crm == "monday":
        meta = _acc_meta(acc)
        meta.setdefault("monday", {})
        meta["monday"]["board_selected"] = bool(meta["monday"].get("board_id"))
        await _save_acc_meta(acc, meta)
    else:
        await acc.save()

    await st.delete()
    logger.info("oauth success crm=%s user=%s", crm, acc.user_id if hasattr(acc, "user_id") else st.user_id)
    return RedirectResponse(url=f"{back}?crm={crm}&status=success")

# ─────────────────────────────────────────────────────────────────────────────
# Connect/disconnect/fresh
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/crm/disconnect/{crm}")
async def disconnect(crm: str, user: User = Depends(get_current_user)):
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc.is_active = False
    await acc.save()
    logger.info("disconnected crm=%s user=%s", crm, user.id)
    return {"success": True, "message": f"Disconnected {crm}."}

@router.post("/crm/ensure-fresh/{crm}")
async def ensure_fresh(crm: str, user: User = Depends(get_current_user)):
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
    if not acc:
        raise HTTPException(404, "Not connected.")
    acc = await _ensure_fresh_token(crm, acc)
    return {"success": True, "expires_at": acc.expires_at}

# ─────────────────────────────────────────────────────────────────────────────
# Monday: board discovery & selection (per-user)
# ─────────────────────────────────────────────────────────────────────────────

def _monday_headers(acc: IntegrationAccount) -> Dict[str, str]:
    return {"Authorization": f"Bearer {acc.access_token}", "Content-Type": "application/json"}

async def _get_active_account(user: User, crm: str) -> IntegrationAccount:
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm.lower(), is_active=True)
    if not acc:
        raise HTTPException(404, f"Not connected to {crm}.")
    await _ensure_fresh_token(crm.lower(), acc)
    return acc

def _get_selected_monday_board(acc: IntegrationAccount) -> Optional[int]:
    meta = _acc_meta(acc)
    try:
        return int(meta.get("monday", {}).get("board_id"))
    except Exception:
        return None

@router.get("/crm/monday/boards")
async def monday_list_boards(
    search: Optional[str] = Query(None, description="Optional case-insensitive search by name"),
    user: User = Depends(get_current_user),
):
    acc = await _get_active_account(user, "monday")
    api_url = _cfg()["monday"]["api_url"]

    q = """
    query($limit: Int!, $page: Int) {
      boards (limit: $limit, page: $page) {
        id
        name
        state
        board_kind
        workspace { id name }
      }
    }
    """

    items: List[Dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            r = await client.post(api_url, headers=_monday_headers(acc), json={"query": q, "variables": {"limit": 100, "page": page}})
            if not r.is_success:
                raise HTTPException(r.status_code, f"monday boards list failed: {r.text[:300]}")
            j = r.json() or {}
            bs = ((j.get("data") or {}).get("boards")) or []
            if not bs:
                break
            items.extend(bs)
            if len(bs) < 100:
                break
            page += 1

    if search:
        s = search.strip().lower()
        items = [b for b in items if s in str(b.get("name","")).lower()]

    return {
        "items": [
            {"id": int(b["id"]), "name": b.get("name"), "state": b.get("state"), "kind": b.get("board_kind"),
             "workspace": (b.get("workspace") or {})}
            for b in items
        ],
        "selected_board_id": _get_selected_monday_board(acc),
    }

@router.get("/crm/monday/board")
async def monday_get_selected_board(user: User = Depends(get_current_user)):
    acc = await _get_active_account(user, "monday")
    meta = _acc_meta(acc)
    return {"selected": meta.get("monday", {}).get("board_id"), "meta": meta.get("monday", {})}

class MondaySelectBoardPayload(BaseModel):
    board_id: int
    board_name: Optional[str] = None

@router.post("/crm/monday/board")
async def monday_select_board(
    payload: MondaySelectBoardPayload,
    user: User = Depends(get_current_user),
):
    acc = await _get_active_account(user, "monday")
    board_id = payload.board_id

    # Validate the board exists & is accessible
    api_url = _cfg()["monday"]["api_url"]
    q = """
    query($ids: [ID!]) {
      boards(ids: $ids) { id name }
    }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(api_url, headers=_monday_headers(acc), json={"query": q, "variables": {"ids": [int(board_id)]}})
        if not r.is_success:
            raise HTTPException(r.status_code, f"monday board verify failed: {r.text[:200]}")
        j = r.json() or {}
        boards = ((j.get("data") or {}).get("boards")) or []
        if not boards:
            raise HTTPException(404, "Board not found or not accessible by this token.")
        name = boards[0].get("name")

    meta = _acc_meta(acc)
    meta.setdefault("monday", {})
    meta["monday"]["board_id"] = int(board_id)
    meta["monday"]["board_name"] = payload.board_name or name
    meta["monday"]["board_selected"] = True
    await _save_acc_meta(acc, meta)

    return {"success": True, "selected": {"board_id": meta["monday"]["board_id"], "board_name": meta["monday"]["board_name"]}}

@router.delete("/crm/monday/board")
async def monday_clear_board(user: User = Depends(get_current_user)):
    acc = await _get_active_account(user, "monday")
    meta = _acc_meta(acc)
    meta.setdefault("monday", {})
    meta["monday"].pop("board_id", None)
    meta["monday"].pop("board_name", None)
    meta["monday"]["board_selected"] = False
    await _save_acc_meta(acc, meta)
    return {"success": True}

# ─────────────────────────────────────────────────────────────────────────────
# Contacts / Leads fetchers (normalize to Lead-like rows)
# ─────────────────────────────────────────────────────────────────────────────

def _norm(
    id: Any,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    state: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": (str(id) if id is not None else None),
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
    cursor: Optional[str] = Query(None, description="Opaque paging cursor/token"),
):
    """
    HubSpot / GHL -> contacts
    Monday -> user's leads from their selected board (per-user privacy).
    """
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

        elif crm == "ghl":
            contacts_url = _cfg()["ghl"]["contacts_url"].rstrip("/")
            url = contacts_url
            params = {"limit": limit}
            if cursor:
                params.update({"cursor": cursor, "nextPageToken": cursor, "page": cursor})

            r = await client.get(
                url,
                headers={"Authorization": f"Bearer {acc.access_token}", "Accept": "application/json"},
                params=params,
            )
            if not r.is_success:
                raise HTTPException(r.status_code, f"GHL contacts fetch failed: {r.text[:300]}")
            j = r.json() if r.text else {}

            data_list = None
            for key in ("contacts", "data", "items", "results"):
                if isinstance(j.get(key), list):
                    data_list = j.get(key)
                    break
            if data_list is None and isinstance(j, list):
                data_list = j

            for c in (data_list or []):
                cid = c.get("id") or c.get("_id") or c.get("contactId")
                first = c.get("firstName") or c.get("first_name")
                last = c.get("lastName") or c.get("last_name")
                full = c.get("name") or " ".join(x for x in [first, last] if x)
                email = c.get("email")
                phone = c.get("phone") or c.get("phoneNumber") or c.get("phone_number")
                state = (
                    c.get("state")
                    or (c.get("address", {}) or {}).get("state")
                    or c.get("region")
                    or None
                )
                items.append(_norm(cid, full or None, email, phone, state, c))

            if isinstance(j.get("meta"), dict):
                meta = j["meta"]
                raw_paging["meta"] = meta
                next_cursor = (
                    meta.get("nextPageToken")
                    or meta.get("next_token")
                    or meta.get("next")
                    or None
                )
            if not next_cursor:
                for k in ("next", "nextPageToken", "nextCursor", "next_page_token"):
                    if j.get(k):
                        next_cursor = str(j.get(k))
                        break

        else:  # MONDAY -> per-user board leads
            cfgm = _cfg()["monday"]
            api_url = cfgm["api_url"]
            headers = _monday_headers(acc)

            # selected board (per-user)
            board_id = _get_selected_monday_board(acc)
            if not board_id:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "monday: Leads board not selected yet.",
                            "needs_board_selection": True}
                )

            # me.id for filtering
            q_me = "query { me { id } }"
            r_me = await client.post(api_url, headers=headers, json={"query": q_me})
            if not r_me.is_success:
                raise HTTPException(r_me.status_code, f"monday me() failed: {r_me.text[:300]}")
            me_id = str(((r_me.json() or {}).get("data") or {}).get("me", {}).get("id") or "")

            q_items = """
            query($board_id: [ID!], $limit: Int!, $cursor: String) {
              boards(ids: $board_id) {
                items_page(limit: $limit, cursor: $cursor) {
                  cursor
                  items {
                    id
                    name
                    creator_id
                    column_values {
                      id
                      text
                      value
                      column { id type title }
                    }
                  }
                }
              }
            }
            """
            vars_ = {
                "board_id": [int(board_id)],
                "limit": int(limit),
                "cursor": cursor if cursor not in (None, "", "null") else None,
            }
            ri = await client.post(api_url, headers=headers, json={"query": q_items, "variables": vars_})
            if not ri.is_success:
                raise HTTPException(ri.status_code, f"monday items_page failed: {ri.text[:300]}")
            ji = ri.json() or {}
            boards = ((ji.get("data") or {}).get("boards")) or []
            page = (boards[0].get("items_page") if boards else None) or {}
            next_cursor = page.get("cursor")
            raw_paging["cursor"] = next_cursor

            email_col = (cfgm.get("email_col") or "").strip()
            phone_col = (cfgm.get("phone_col") or "").strip()
            state_col = (cfgm.get("state_col") or "").strip()
            owner_col = (cfgm.get("owner_col") or "").strip()

            def _owned_by_me(cv_list: List[Dict[str, Any]]) -> bool:
                """True if owner_col contains me_id (people column)."""
                if not owner_col:
                    return False
                for cv in cv_list or []:
                    if str(cv.get("id") or "") == owner_col:
                        try:
                            v = cv.get("value")
                            data = json.loads(v) if isinstance(v, str) and v else (v if isinstance(v, dict) else {})
                            persons = (data.get("personsAndTeams") or []) or data.get("persons") or []
                            for p in persons:
                                if str(p.get("id")) == me_id and (p.get("kind") in (None, "person")):
                                    return True
                        except Exception:
                            return False
                return False

            for it in (page.get("items") or []):
                cv_list = it.get("column_values") or []

                # privacy: each user sees only their leads
                if owner_col:
                    if not _owned_by_me(cv_list):
                        continue
                else:
                    if str(it.get("creator_id")) != me_id:
                        continue

                name = it.get("name")
                email = None
                phone = None
                state = None
                for cv in cv_list:
                    cid = str(cv.get("id") or "")
                    ctype = ((cv.get("column") or {}).get("type") or "").lower()
                    text = cv.get("text")
                    if email is None and (email_col and cid == email_col or (not email_col and ctype == "email")):
                        email = text or email
                    if phone is None and (phone_col and cid == phone_col or (not phone_col and ctype == "phone")):
                        phone = text or phone
                    if state is None and (state_col and cid == state_col):
                        state = text or state

                items.append(_norm(it.get("id"), name, email, phone, state, it))

    logger.info("contacts/leads fetched crm=%s items=%s next=%s", crm, len(items), bool(next_cursor))
    return {"items": items, "next_cursor": next_cursor, "raw_paging": raw_paging}

# ─────────────────────────────────────────────────────────────────────────────
# Treat Contacts as Leads -> auto-create "<CRM> Leads" file and upsert
# ─────────────────────────────────────────────────────────────────────────────

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
        logger.info("created file '%s' (id=%s) for user=%s", name, file.id, user.id)
    return file

async def _upsert_lead_from_contact(file: FileModel, item: Dict[str, Any], crm: str) -> Tuple[bool, bool]:
    full_name = item.get("name")
    first, last = _split_name(full_name)
    email = item.get("email")
    phone = _clean_phone(item.get("phone"))
    external_id = item.get("id")
    state = item.get("state")
    raw = item.get("raw") or {}
    company = (
        raw.get("company")
        or raw.get("organization")
        or raw.get("companyName")
        or raw.get("account")
        or ""
    )

    existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
    payload = {
        "first_name": first or "",
        "last_name": last or "",
        "email": email,
        "mobile": phone,
        "state": state,
        "salesforce_id": external_id,
        "add_date": datetime.utcnow(),
        "other_data": {
            "Custom_0": company,
            "Custom_1": f"source:{crm}"
        }
    }

    if existing:
        changed = False
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

# ─────────────────────────────────────────────────────────────────────────────
# Sync endpoints
# ─────────────────────────────────────────────────────────────────────────────

async def _sync_one_crm(user: User, crm: str) -> Dict[str, Any]:
    crm = crm.lower()
    if crm not in SUPPORTED:
        raise HTTPException(400, "Unsupported CRM")
    acc = await IntegrationAccount.get_or_none(user_id=user.id, crm=crm, is_active=True)
    if not acc:
        raise HTTPException(404, f"Not connected to {crm}.")

    label_map = {"hubspot": "HubSpot", "ghl": "GHL", "monday": "Monday"}
    label = label_map.get(crm, crm)
    file_name = f"{label} Leads"

    # Monday: ensure board selected before sync
    if crm == "monday" and not _get_selected_monday_board(acc):
        return {"crm": crm, "error": "monday: board not selected", "needs_board_selection": True}

    file = await _ensure_file(user, file_name)

    try:
        items = await _fetch_all_contacts(user, crm)
        created = 0
        updated = 0
        for it in items:
            c, u = await _upsert_lead_from_contact(file, it, crm)
            created += int(c)
            updated += int(u)

        logger.info("sync ok crm=%s file=%s fetched=%s created=%s updated=%s",
                    crm, file.id, len(items), created, updated)

        return {
            "crm": crm,
            "file_id": file.id,
            "file_name": file.name,
            "fetched_contacts": len(items),
            "created_leads": created,
            "updated_leads": updated,
        }
    except HTTPException as e:
        logger.exception("sync http error crm=%s: %s", crm, e.detail)
        return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e.detail)}
    except Exception as e:
        logger.exception("sync error crm=%s", crm)
        return {"crm": crm, "file_id": file.id, "file_name": file.name, "error": str(e)}

@router.post("/crm/ingest/hubspot")
async def ingest_hubspot(user: User = Depends(get_current_user)):
    out = await _sync_one_crm(user, "hubspot")
    return {"success": True, "details": [out]}

@router.post("/crm/ingest/ghl")
async def ingest_ghl(user: User = Depends(get_current_user)):
    out = await _sync_one_crm(user, "ghl")
    return {"success": True, "details": [out]}

@router.post("/crm/ingest/monday")
async def ingest_monday(user: User = Depends(get_current_user)):
    """Create/Update 'Monday Leads' and pull the *current user's* leads from the selected board."""
    out = await _sync_one_crm(user, "monday")
    return {"success": True, "details": [out]}

@router.post("/crm/sync-to-files")
async def sync_connected_crms_to_files(
    user: User = Depends(get_current_user),
    crm: Optional[str] = Query(None, description="Optional: 'hubspot' or 'ghl' or 'monday'"),
):
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
        results.append(await _sync_one_crm(user, acc.crm))

    return {"success": True, "ran": len(connected), "details": results}
    