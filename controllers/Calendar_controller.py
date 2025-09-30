# # controllers/calendar_controller.py
# import os
# import hmac
# import base64
# import json
# import hashlib
# import secrets
# from typing import Annotated, Dict, Any, List, Optional, Tuple
# from datetime import datetime, timedelta, timezone, date

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Header
# from fastapi.responses import HTMLResponse, JSONResponse
# from pydantic import BaseModel, Field, validator

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.appointment import Appointment, AppointmentStatus

# # Token/account + link mapping
# from models.calendar_account import CalendarAccount
# from models.appointment_link import AppointmentExternalLink

# router = APIRouter()

# # ──────────────────────────────────────────────────────────────────────────────
# # Config (env)
# # ──────────────────────────────────────────────────────────────────────────────

# PUBLIC_BASE = os.getenv("CAL_PUBLIC_BASE", "http://localhost:8000").rstrip("/")
# STATE_SECRET = os.getenv("CAL_OAUTH_STATE_SECRET", "dev-state-secret-change-me")

# # ===== Google =====
# GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
# GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/google/callback")

# GOOGLE_AUTH_URL  = os.getenv("GOOGLE_AUTH_URL",  "https://accounts.google.com/o/oauth2/v2/auth")
# GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
# GOOGLE_API_BASE  = os.getenv("GOOGLE_API_BASE",  "https://www.googleapis.com/calendar/v3")

# GOOGLE_SCOPES = os.getenv(
#     "GOOGLE_SCOPES",
#     "https://www.googleapis.com/auth/calendar"
# )
# GOOGLE_SEND_UPDATES = os.getenv("GOOGLE_SEND_UPDATES", "none")  # all | externalOnly | none

# # ===== Cal.com =====
# # You may use OAuth OR Personal Access Token (PAT) per user.
# CALCOM_CLIENT_ID     = os.getenv("CALCOM_CLIENT_ID", "")
# CALCOM_CLIENT_SECRET = os.getenv("CALCOM_CLIENT_SECRET", "")
# CALCOM_REDIRECT_URI  = os.getenv("CALCOM_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/calcom/callback")
# CALCOM_AUTH_URL      = os.getenv("CALCOM_AUTH_URL", "https://api.cal.com/oauth/authorize")   # verify
# CALCOM_TOKEN_URL     = os.getenv("CALCOM_TOKEN_URL", "https://api.cal.com/oauth/token")       # verify
# CALCOM_API_BASE      = os.getenv("CALCOM_API_BASE", "https://api.cal.com/v1")                  # /v1 is common
# # Webhook signature (HMAC SHA256 hex of raw body). Header often: `x-cal-signature-256`
# CALCOM_WEBHOOK_SECRET = os.getenv("CALCOM_WEBHOOK_SECRET", "")

# # ===== Calendly =====
# # OAuth OR Personal Access Token (PAT) per user.
# CALENDLY_CLIENT_ID     = os.getenv("CALENDLY_CLIENT_ID", "")
# CALENDLY_CLIENT_SECRET = os.getenv("CALENDLY_CLIENT_SECRET", "")
# CALENDLY_REDIRECT_URI  = os.getenv("CALENDLY_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/calendly/callback")
# CALENDLY_AUTH_URL      = os.getenv("CALENDLY_AUTH_URL", "https://auth.calendly.com/oauth/authorize")
# CALENDLY_TOKEN_URL     = os.getenv("CALENDLY_TOKEN_URL", "https://auth.calendly.com/oauth/token")
# CALENDLY_API_BASE      = os.getenv("CALENDLY_API_BASE", "https://api.calendly.com")
# # Webhook signature header is typically `Calendly-Webhook-Signature` -> "t=...,v1=..."
# CALENDLY_WEBHOOK_SIGNING_KEY = os.getenv("CALENDLY_WEBHOOK_SIGNING_KEY", "")

# # ──────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ──────────────────────────────────────────────────────────────────────────────

# class ConnectUrl(BaseModel):
#     provider: str
#     auth_url: str

# class TokenConnectBody(BaseModel):
#     api_key: str = Field(..., min_length=8, max_length=4096)  # PAT

# class CreateEventBody(BaseModel):
#     title: str = Field(..., max_length=200)
#     start_at: datetime
#     end_at: datetime
#     phone: str = Field(..., max_length=32)
#     timezone: str = Field(..., max_length=64)
#     location: Optional[str] = Field(None, max_length=200)
#     notes: Optional[str] = None
#     account_id: Optional[str] = None          # CalendarAccount.id
#     calendar_id: Optional[str] = None         # override default/primary

#     # Optional attendee info (useful for Cal.com booking)
#     attendee_name: Optional[str] = None
#     attendee_email: Optional[str] = None
#     # Optional Cal.com event type (slug) or Calendly event type URI when creating links
#     event_type: Optional[str] = None

#     @validator("end_at")
#     def _range(cls, v, values):
#         s = values.get("start_at")
#         if s and v <= s:
#             raise ValueError("end_at must be after start_at")
#         return v

# class UpdateEventBody(BaseModel):
#     title: Optional[str] = Field(None, max_length=200)
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None
#     phone: Optional[str] = Field(None, max_length=32)
#     timezone: Optional[str] = Field(None, max_length=64)
#     location: Optional[str] = Field(None, max_length=200)
#     notes: Optional[str] = None
#     calendar_id: Optional[str] = None  # allow move across calendars

# class SyncBody(BaseModel):
#     start_at: Optional[datetime] = None
#     end_at: Optional[datetime] = None
#     account_ids: Optional[List[str]] = None

# class FreeBusyBody(BaseModel):
#     start_at: datetime
#     end_at: datetime
#     account_id: Optional[str] = None
#     calendar_ids: Optional[List[str]] = None

# class SchedulingLinkBody(BaseModel):
#     account_id: Optional[str] = None
#     # For Cal.com: event type slug (required). For Calendly: event_type URI (required).
#     event_type: str
#     max_event_count: int = 1
#     owner: Optional[str] = None  # Calendly owner URI override

# # ──────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ──────────────────────────────────────────────────────────────────────────────

# def _ok(data: Dict[str, Any]) -> JSONResponse:
#     return JSONResponse(data)

# def _err(code: int, msg: str) -> None:
#     raise HTTPException(status_code=code, detail=msg)

# def _now_utc() -> datetime:
#     return datetime.now(tz=timezone.utc)

# def _mk_state(user_id: int, provider: str) -> str:
#     ts = str(int(_now_utc().timestamp()))
#     payload = f"{user_id}:{provider}:{ts}"
#     mac = hmac.new(STATE_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
#     return base64.urlsafe_b64encode(f"{payload}:{mac.hex()}".encode()).decode()

# def _parse_state(state: str) -> Tuple[int, str]:
#     try:
#         raw = base64.urlsafe_b64decode(state.encode()).decode()
#         parts = raw.split(":")
#         if len(parts) != 4:
#             raise ValueError("bad state format")
#         uid_s, provider, ts, mac_hex = parts
#         payload = f"{uid_s}:{provider}:{ts}"
#         exp_mac = hmac.new(STATE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
#         if not hmac.compare_digest(mac_hex, exp_mac):
#             raise ValueError("bad state mac")
#         if (int(_now_utc().timestamp()) - int(ts)) > 900:
#             raise ValueError("state expired")
#         return int(uid_s), provider
#     except Exception as e:
#         _err(status.HTTP_400_BAD_REQUEST, f"Invalid state: {e}")

# def _bearer_headers(token: str) -> Dict[str, str]:
#     return {
#         "Authorization": f"Bearer {token}",
#         "Accept": "application/json",
#         "Content-Type": "application/json",
#     }

# def _iso(dt: datetime) -> str:
#     if dt.tzinfo is None:
#         dt = dt.replace(tzinfo=timezone.utc)
#     return dt.astimezone(timezone.utc).isoformat()

# def _is_all_day(start_at: datetime, end_at: datetime) -> bool:
#     s = start_at.astimezone(timezone.utc)
#     e = end_at.astimezone(timezone.utc)
#     return (
#         s.hour == s.minute == s.second == 0
#         and e.hour == e.minute == e.second == 0
#         and (e - s).total_seconds() >= 86400
#         and ((e - s).total_seconds() % 86400 == 0)
#     )

# def _google_time_block(start_at: datetime, end_at: datetime, tz: str) -> Dict[str, Any]:
#     if _is_all_day(start_at, end_at):
#         return {
#             "start": {"date": start_at.date().isoformat()},
#             "end": {"date": end_at.date().isoformat()},
#         }
#     return {
#         "start": {"dateTime": _iso(start_at), "timeZone": tz},
#         "end": {"dateTime": _iso(end_at), "timeZone": tz},
#     }

# def _event_status_to_appt_status(ev_status: str, start_at: datetime, end_at: datetime) -> AppointmentStatus:
#     s = (ev_status or "").lower()
#     if "cancel" in s or s == "cancelled":
#         return AppointmentStatus.CANCELLED
#     return AppointmentStatus.COMPLETED if end_at <= _now_utc() else AppointmentStatus.SCHEDULED

# def _parse_dt_guess(v: Any) -> Optional[datetime]:
#     # Supports google/caldav-ish 'date' and 'dateTime', and plain ISO strings
#     if not v:
#         return None
#     if isinstance(v, dict):
#         if "dateTime" in v: return _parse_dt_guess(v["dateTime"])
#         if "date" in v:
#             try:
#                 d = date.fromisoformat(v["date"])
#                 return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
#             except Exception:
#                 return None
#     if isinstance(v, (int, float)): return datetime.fromtimestamp(v, tz=timezone.utc)
#     if isinstance(v, str):
#         s = v.replace("Z", "+00:00")
#         try:
#             return datetime.fromisoformat(s)
#         except Exception:
#             try:
#                 return datetime.fromisoformat(s[:19] + "+00:00")
#             except Exception:
#                 return None
#     return None

# # ──────────────────────────────────────────────────────────────────────────────
# # Google mappers (kept from your version)
# # ──────────────────────────────────────────────────────────────────────────────

# def _map_google_event_to_appt(ev: Dict[str, Any]) -> Dict[str, Any]:
#     external_id = ev.get("id") or secrets.token_hex(8)
#     calendar_id = ev.get("organizer", {}).get("email") or ev.get("calendarId") or ev.get("creator", {}).get("email")

#     title = ev.get("summary") or "Appointment"
#     description = ev.get("description") or ""
#     location = ev.get("location") or ""
#     status_s = ev.get("status") or "confirmed"

#     start_at = _parse_dt_guess(ev.get("start"))
#     end_at = _parse_dt_guess(ev.get("end"))
#     if not (start_at and end_at):
#         raise ValueError("missing times")

#     tz = "UTC"
#     if isinstance(ev.get("start"), dict) and ev["start"].get("timeZone"):
#         tz = ev["start"]["timeZone"]

#     duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))
#     status = _event_status_to_appt_status(status_s, start_at, end_at)

#     return {
#         "external_event_id": str(external_id),
#         "external_calendar_id": calendar_id,
#         "appt_fields": {
#             "title": title[:200],
#             "notes": description or None,
#             "location": (location or None),
#             "phone": "unknown",
#             "timezone": tz[:64],
#             "start_at": start_at,
#             "end_at": end_at,
#             "duration_minutes": duration_minutes,
#             "status": status,
#         },
#     }

# # ──────────────────────────────────────────────────────────────────────────────
# # Cal.com mappers
# # ──────────────────────────────────────────────────────────────────────────────

# def _map_calcom_booking_to_appt(b: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Cal.com webhook/booking shape can vary; we handle common fields:
#       id/uid, title, description/notes, startTime/endTime (ISO), timezone, location/videoCallUrl, status
#     """
#     ext_id = str(b.get("id") or b.get("uid") or b.get("bookingUid") or secrets.token_hex(8))
#     title = (b.get("title") or "Cal.com booking")[:200]
#     description = b.get("description") or b.get("notes") or ""
#     location = b.get("location") or b.get("videoCallUrl") or ""
#     tz = b.get("timezone") or "UTC"
#     start_at = _parse_dt_guess(b.get("startTime") or b.get("start") or b.get("start_time"))
#     end_at   = _parse_dt_guess(b.get("endTime")   or b.get("end")   or b.get("end_time"))
#     status_s = (b.get("status") or "confirmed").lower()
#     if not (start_at and end_at):
#         raise ValueError("missing times")
#     duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))
#     status = _event_status_to_appt_status(status_s, start_at, end_at)
#     return {
#         "external_event_id": ext_id,
#         "external_calendar_id": b.get("calendarId") or b.get("eventType") or None,
#         "appt_fields": {
#             "title": title,
#             "notes": description or None,
#             "location": (location or None),
#             "phone": "unknown",
#             "timezone": tz[:64],
#             "start_at": start_at,
#             "end_at": end_at,
#             "duration_minutes": duration_minutes,
#             "status": status,
#         },
#     }

# # ──────────────────────────────────────────────────────────────────────────────
# # Calendly mappers
# # ──────────────────────────────────────────────────────────────────────────────

# def _map_calendly_event_to_appt(payload: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Calendly webhook `invitee.created` / `invitee.canceled` provides:
#       payload["event"] (scheduled_event), payload["invitee"], status derived from action.
#     """
#     ev = payload.get("event") or {}
#     invitee = payload.get("invitee") or {}
#     ext_id = ev.get("uuid") or (ev.get("uri") or "").split("/")[-1] or secrets.token_hex(8)
#     title = (ev.get("name") or "Calendly booking")[:200]
#     description = invitee.get("text_reminder_number") or invitee.get("questions_and_answers") or ""
#     location = ev.get("location", {}).get("location") if isinstance(ev.get("location"), dict) else (ev.get("location") or "")

#     start_at = _parse_dt_guess(ev.get("start_time"))
#     end_at   = _parse_dt_guess(ev.get("end_time"))
#     tz = invitee.get("timezone") or "UTC"
#     if not (start_at and end_at):
#         raise ValueError("missing times")
#     duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))

#     # Webhook topic decides status
#     status_s = payload.get("status") or payload.get("event_type") or "confirmed"
#     status = _event_status_to_appt_status(status_s, start_at, end_at)

#     return {
#         "external_event_id": str(ext_id),
#         "external_calendar_id": ev.get("event_type") or None,
#         "appt_fields": {
#             "title": title,
#             "notes": description or None,
#             "location": (location or None),
#             "phone": invitee.get("sms_number") or "unknown",
#             "timezone": tz[:64],
#             "start_at": start_at,
#             "end_at": end_at,
#             "duration_minutes": duration_minutes,
#             "status": status,
#         },
#     }

# # ──────────────────────────────────────────────────────────────────────────────
# # Providers / Accounts
# # ──────────────────────────────────────────────────────────────────────────────

# @router.get("/calendar/providers")
# async def list_calendar_providers(user: Annotated[User, Depends(get_current_user)]):
#     return {
#         "providers": [
#             {
#                 "key": "google",
#                 "name": "Google Calendar",
#                 "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
#                 "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/google",
#                 "supports": ["oauth", "crud", "sync", "freebusy"],
#             },
#             {
#                 "key": "calcom",
#                 "name": "Cal.com",
#                 "configured": bool(CALCOM_CLIENT_ID and CALCOM_CLIENT_SECRET) or True,  # PAT path allowed
#                 "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calcom",
#                 "connect_token_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calcom/token",
#                 "webhook_url": f"{PUBLIC_BASE}/api/calendar/webhook/calcom",
#                 "supports": ["oauth", "token", "webhooks", "scheduling_links", "sync"],
#             },
#             {
#                 "key": "calendly",
#                 "name": "Calendly",
#                 "configured": bool(CALENDLY_CLIENT_ID and CALENDLY_CLIENT_SECRET) or True,  # PAT path allowed
#                 "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calendly",
#                 "connect_token_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calendly/token",
#                 "webhook_url": f"{PUBLIC_BASE}/api/calendar/webhook/calendly",
#                 "supports": ["oauth", "token", "webhooks", "scheduling_links", "sync"],
#             },
#         ]
#     }

# @router.get("/calendar/accounts")
# async def list_calendar_accounts(user: Annotated[User, Depends(get_current_user)]):
#     rows = await CalendarAccount.filter(user=user).order_by("-created_at").values()
#     return rows

# @router.delete("/calendar/accounts/{account_id}")
# async def disconnect_calendar_account(account_id: str, user: Annotated[User, Depends(get_current_user)]):
#     acc = await CalendarAccount.get_or_none(id=account_id, user=user)
#     if not acc:
#         _err(404, "Account not found")
#     await AppointmentExternalLink.filter(account=acc).delete()
#     await acc.delete()
#     return {"ok": True}

# # ──────────────────────────────────────────────────────────────────────────────
# # Google OAuth – unchanged
# # ──────────────────────────────────────────────────────────────────────────────

# @router.get("/calendar/connect/google")
# async def calendar_connect_google(user: Annotated[User, Depends(get_current_user)]):
#     if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
#         _err(400, "Google not configured")
#     state = _mk_state(user.id, "google")

#     from urllib.parse import urlencode
#     params = {
#         "client_id": GOOGLE_CLIENT_ID,
#         "redirect_uri": GOOGLE_REDIRECT_URI,
#         "response_type": "code",
#         "scope": GOOGLE_SCOPES,
#         "state": state,
#         "access_type": "offline",
#         "include_granted_scopes": "true",
#         "prompt": "consent",
#     }
#     return ConnectUrl(provider="google", auth_url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")

# async def _google_exchange_code_for_token(code: str) -> Dict[str, Any]:
#     data = {
#         "grant_type": "authorization_code",
#         "client_id": GOOGLE_CLIENT_ID,
#         "client_secret": GOOGLE_CLIENT_SECRET,
#         "redirect_uri": GOOGLE_REDIRECT_URI,
#         "code": code,
#     }
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(GOOGLE_TOKEN_URL, data=data)
#     if r.status_code != 200:
#         _err(400, f"Token exchange failed: {r.text}")
#     return r.json()

# async def _google_refresh_token(refresh_token: str) -> Dict[str, Any]:
#     data = {
#         "grant_type": "refresh_token",
#         "client_id": GOOGLE_CLIENT_ID,
#         "client_secret": GOOGLE_CLIENT_SECRET,
#         "refresh_token": refresh_token,
#     }
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         r = await client.post(GOOGLE_TOKEN_URL, data=data)
#     if r.status_code != 200:
#         _err(400, f"Refresh failed: {r.text}")
#     return r.json()

# async def _ensure_access_token(account: CalendarAccount) -> CalendarAccount:
#     if account.expires_at and account.expires_at > _now_utc() + timedelta(seconds=60):
#         return account
#     if account.provider == "google" and account.refresh_token:
#         tok = await _google_refresh_token(account.refresh_token)
#         account.access_token = tok.get("access_token", account.access_token)
#         account.refresh_token = tok.get("refresh_token", account.refresh_token)
#         account.expires_at = _now_utc() + timedelta(seconds=int(tok.get("expires_in") or 3600))
#         await account.save()
#     return account

# @router.get("/calendar/oauth/google/callback", response_class=HTMLResponse)
# async def calendar_oauth_callback_google(request: Request):
#     q = request.query_params
#     code = q.get("code")
#     state = q.get("state")
#     if not (code and state):
#         _err(400, "Missing code/state")

#     user_id, provider = _parse_state(state)
#     if provider != "google":
#         _err(400, "Provider mismatch")

#     token = await _google_exchange_code_for_token(code)
#     access_token = token.get("access_token")
#     refresh_token = token.get("refresh_token")
#     expires_in = int(token.get("expires_in") or 3600)
#     scope = token.get("scope") or GOOGLE_SCOPES

#     if not access_token:
#         _err(400, "Google did not return access_token")

#     # Fetch calendar list → pick primary calendar + email identity
#     primary_calendar_id = None
#     external_email = None
#     external_account_id = None
#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             url = f"{GOOGLE_API_BASE}/users/me/calendarList"
#             r = await client.get(url, headers=_bearer_headers(access_token))
#         if r.status_code == 200:
#             data = r.json() or {}
#             for item in data.get("items", []):
#                 if item.get("primary"):
#                     primary_calendar_id = item.get("id")
#                     external_email = item.get("id")
#                     external_account_id = external_email
#                     break
#             if not primary_calendar_id and data.get("items"):
#                 primary_calendar_id = data["items"][0].get("id")
#                 external_email = data["items"][0].get("id")
#                 external_account_id = external_email
#     except Exception:
#         pass

#     acc = await CalendarAccount.get_or_none(
#         user_id=user_id, provider="google", external_account_id=external_account_id or external_email
#     )
#     if not acc:
#         acc = await CalendarAccount.create(
#             user_id=user_id,
#             provider="google",
#             external_account_id=external_account_id or "google",
#             external_email=external_email,
#             access_token=access_token,
#             refresh_token=refresh_token,
#             scope=scope,
#             expires_at=_now_utc() + timedelta(seconds=expires_in),
#             primary_calendar_id=primary_calendar_id,
#         )
#     else:
#         acc.external_email = external_email
#         acc.access_token = access_token
#         acc.refresh_token = refresh_token or acc.refresh_token
#         acc.scope = scope
#         acc.expires_at = _now_utc() + timedelta(seconds=expires_in)
#         acc.primary_calendar_id = primary_calendar_id or acc.primary_calendar_id
#         await acc.save()

#     return HTMLResponse("<h3>Google Calendar connected ✅</h3>You can close this window.", status_code=200)

# # ──────────────────────────────────────────────────────────────────────────────
# # Cal.com: OAuth connect (optional) + Token connect (PAT)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.get("/calendar/connect/calcom")
# async def calendar_connect_calcom(user: Annotated[User, Depends(get_current_user)]):
#     if not (CALCOM_CLIENT_ID and CALCOM_CLIENT_SECRET):
#         _err(400, "Cal.com OAuth not configured (use /calendar/connect/calcom/token instead)")
#     from urllib.parse import urlencode
#     state = _mk_state(user.id, "calcom")
#     params = {
#         "client_id": CALCOM_CLIENT_ID,
#         "redirect_uri": CALCOM_REDIRECT_URI,
#         "response_type": "code",
#         "scope": "booking:read booking:write",  # adjust per app scopes
#         "state": state,
#         "prompt": "consent",
#     }
#     return ConnectUrl(provider="calcom", auth_url=f"{CALCOM_AUTH_URL}?{urlencode(params)}")

# @router.post("/calendar/connect/calcom/token")
# async def calendar_connect_calcom_token(body: TokenConnectBody, user: Annotated[User, Depends(get_current_user)]):
#     # Verify token by calling /me (adjust if your API differs)
#     async with httpx.AsyncClient(timeout=20.0) as client:
#         r = await client.get(f"{CALCOM_API_BASE}/me", headers=_bearer_headers(body.api_key))
#     if r.status_code != 200:
#         _err(400, f"Cal.com token invalid: {r.text}")
#     me = r.json() or {}
#     external_email = me.get("email") or me.get("username") or "calcom"
#     external_account_id = str(me.get("id") or external_email)

#     acc = await CalendarAccount.get_or_none(user=user, provider="calcom", external_account_id=external_account_id)
#     if not acc:
#         acc = await CalendarAccount.create(
#             user=user,
#             provider="calcom",
#             external_account_id=external_account_id,
#             external_email=external_email,
#             access_token=body.api_key,
#             scope="token",
#             primary_calendar_id=None,
#         )
#     else:
#         acc.external_email = external_email
#         acc.access_token = body.api_key
#         await acc.save()
#     return {"ok": True, "account_id": str(acc.id)}

# # ──────────────────────────────────────────────────────────────────────────────
# # Calendly: OAuth connect (optional) + Token connect (PAT)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.get("/calendar/connect/calendly")
# async def calendar_connect_calendly(user: Annotated[User, Depends(get_current_user)]):
#     if not (CALENDLY_CLIENT_ID and CALENDLY_CLIENT_SECRET):
#         _err(400, "Calendly OAuth not configured (use /calendar/connect/calendly/token instead)")
#     from urllib.parse import urlencode
#     state = _mk_state(user.id, "calendly")
#     params = {
#         "client_id": CALENDLY_CLIENT_ID,
#         "redirect_uri": CALENDLY_REDIRECT_URI,
#         "response_type": "code",
#         "scope": "default",  # Calendly scopes are managed at app-level
#         "state": state,
#         "prompt": "consent",
#     }
#     return ConnectUrl(provider="calendly", auth_url=f"{CALENDLY_AUTH_URL}?{urlencode(params)}")

# @router.post("/calendar/connect/calendly/token")
# async def calendar_connect_calendly_token(body: TokenConnectBody, user: Annotated[User, Depends(get_current_user)]):
#     # Verify token with /users/me
#     async with httpx.AsyncClient(timeout=20.0) as client:
#         r = await client.get(f"{CALENDLY_API_BASE}/users/me", headers=_bearer_headers(body.api_key))
#     if r.status_code != 200:
#         _err(400, f"Calendly token invalid: {r.text}")
#     me = r.json() or {}
#     res_user = me.get("resource") or me.get("data") or {}
#     external_email = res_user.get("email") or "calendly"
#     external_account_id = res_user.get("uri") or external_email

#     acc = await CalendarAccount.get_or_none(user=user, provider="calendly", external_account_id=external_account_id)
#     if not acc:
#         acc = await CalendarAccount.create(
#             user=user,
#             provider="calendly",
#             external_account_id=external_account_id,
#             external_email=external_email,
#             access_token=body.api_key,
#             scope="token",
#             primary_calendar_id=None,
#         )
#     else:
#         acc.external_email = external_email
#         acc.access_token = body.api_key
#         await acc.save()
#     return {"ok": True, "account_id": str(acc.id)}

# # ──────────────────────────────────────────────────────────────────────────────
# # Pick account helper
# # ──────────────────────────────────────────────────────────────────────────────

# async def _pick_account(user: User, account_id: Optional[str], provider: Optional[str] = None) -> CalendarAccount:
#     q = CalendarAccount.filter(user=user)
#     if provider:
#         q = q.filter(provider=provider)
#     if account_id:
#         q = q.filter(id=account_id)
#     acc = await q.order_by("-created_at").first()
#     if not acc:
#         _err(400, f"No connected {provider or 'calendar'} account")
#     return acc

# # ──────────────────────────────────────────────────────────────────────────────
# # Events: Create / Update / Cancel
# # Google = direct CRUD; Cal.com = direct booking if details provided else return scheduling link
# # Calendly = return scheduling link (programmatic booking is limited)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.post("/calendar/events")
# async def create_event(body: CreateEventBody, user: Annotated[User, Depends(get_current_user)]):
#     acc = await _pick_account(user, body.account_id)
#     if acc.provider == "google":
#         await _ensure_access_token(acc)
#         calendar_id = body.calendar_id or acc.primary_calendar_id or "primary"
#         time_block = _google_time_block(body.start_at, body.end_at, body.timezone)
#         payload = {
#             "summary": body.title,
#             "description": body.notes or "",
#             "location": body.location or "",
#             **time_block,
#             "status": "confirmed",
#             "reminders": {"useDefault": True},
#         }
#         params = {"sendUpdates": GOOGLE_SEND_UPDATES}
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events"
#             r = await client.post(url, headers=_bearer_headers(acc.access_token), params=params, content=json.dumps(payload))
#         if r.status_code not in (200, 201):
#             _err(400, f"Google create failed: {r.text}")
#         ev = r.json() or {}
#         external_event_id = ev.get("id") or secrets.token_hex(8)
#         appt = await Appointment.create(
#             user=user,
#             title=body.title, notes=body.notes, location=body.location,
#             phone=body.phone or "unknown", timezone=body.timezone,
#             start_at=body.start_at, end_at=body.end_at,
#             duration_minutes=int((body.end_at - body.start_at).total_seconds() // 60),
#             status=_event_status_to_appt_status(ev.get("status", "confirmed"), body.start_at, body.end_at),
#         )
#         await AppointmentExternalLink.create(
#             appointment=appt, account=acc, provider="google",
#             external_event_id=external_event_id, external_calendar_id=calendar_id,
#         )
#         return {"ok": True, "appointment_id": str(appt.id), "provider": "google", "external_event_id": external_event_id}

#     if acc.provider == "calcom":
#         # If you pass all details + event_type, try to book directly:
#         if body.event_type and body.attendee_email and body.attendee_name:
#             payload = {
#                 "eventType": body.event_type,                  # usually slug
#                 "startTime": _iso(body.start_at),
#                 "endTime": _iso(body.end_at),
#                 "title": body.title,
#                 "description": body.notes or "",
#                 "timezone": body.timezone,
#                 "location": body.location or "",
#                 "attendees": [{"name": body.attendee_name, "email": body.attendee_email}],
#             }
#             async with httpx.AsyncClient(timeout=30.0) as client:
#                 r = await client.post(f"{CALCOM_API_BASE}/bookings", headers=_bearer_headers(acc.access_token), content=json.dumps(payload))
#             if r.status_code not in (200, 201):
#                 _err(400, f"Cal.com booking failed: {r.text}")
#             b = r.json() or {}
#             mapped = _map_calcom_booking_to_appt(b if isinstance(b, dict) else (b.get("data") or {}))
#             appt = await Appointment.create(user=user, **mapped["appt_fields"])
#             await AppointmentExternalLink.create(
#                 appointment=appt, account=acc, provider="calcom",
#                 external_event_id=mapped["external_event_id"],
#                 external_calendar_id=mapped.get("external_calendar_id"),
#             )
#             return {"ok": True, "appointment_id": str(appt.id), "provider": "calcom", "external_event_id": mapped["external_event_id"]}

#         # Otherwise: generate a single-use scheduling link (user-friendly)
#         _err(400, "Missing attendee/event_type for direct Cal.com booking. Use /calendar/calcom/scheduling-link to get a booking URL.")

#     if acc.provider == "calendly":
#         _err(400, "Calendly programmatic booking is limited. Use /calendar/calendly/scheduling-link to create a link; webhook will mirror booking.")

#     _err(400, f"Unsupported provider: {acc.provider}")

# @router.patch("/calendar/events/{appointment_id}")
# async def update_event(appointment_id: str, body: UpdateEventBody, user: Annotated[User, Depends(get_current_user)]):
#     appt = await Appointment.get_or_none(id=appointment_id, user=user)
#     if not appt:
#         _err(404, "Appointment not found")

#     link = await AppointmentExternalLink.get_or_none(appointment=appt)
#     if not link:
#         _err(400, "No linked provider event for this appointment")

#     acc = await CalendarAccount.get_or_none(id=link.account_id, user=user)
#     if not acc:
#         _err(400, "Linked account not found")

#     # Google update
#     if acc.provider == "google":
#         await _ensure_access_token(acc)
#         new_title = body.title or appt.title
#         new_location = body.location if body.location is not None else appt.location
#         new_notes = body.notes if body.notes is not None else appt.notes
#         new_phone = body.phone or appt.phone
#         new_tz = body.timezone or appt.timezone
#         new_start = body.start_at or appt.start_at
#         new_end = body.end_at or appt.end_at
#         new_calendar = body.calendar_id or link.external_calendar_id or acc.primary_calendar_id or "primary"

#         time_block = _google_time_block(new_start, new_end, new_tz)
#         payload = {
#             "summary": new_title,
#             "description": new_notes or "",
#             "location": new_location or "",
#             **time_block,
#             "status": "confirmed",
#             "reminders": {"useDefault": True},
#         }
#         params = {"sendUpdates": GOOGLE_SEND_UPDATES}
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             url = f"{GOOGLE_API_BASE}/calendars/{new_calendar}/events/{link.external_event_id}"
#             r = await client.patch(url, headers=_bearer_headers(acc.access_token), params=params, content=json.dumps(payload))
#         if r.status_code not in (200, 201):
#             _err(400, f"Google update failed: {r.text}")

#         # mirror locally
#         appt.title = new_title
#         appt.location = new_location
#         appt.notes = new_notes
#         appt.phone = new_phone
#         appt.timezone = new_tz
#         appt.start_at = new_start
#         appt.end_at = new_end
#         appt.duration_minutes = int((new_end - new_start).total_seconds() // 60)
#         appt.status = _event_status_to_appt_status("confirmed", new_start, new_end)
#         await appt.save()

#         if new_calendar != link.external_calendar_id:
#             link.external_calendar_id = new_calendar
#             await link.save()

#         return {"ok": True}

#     # Cal.com / Calendly: updates should be done by the attendee/host in the provider;
#     # your DB will reflect changes via webhooks or /sync.
#     _err(400, f"Update via API not supported for provider: {acc.provider}. Edit on provider or rebook; webhook will sync it.")

# @router.delete("/calendar/events/{appointment_id}")
# async def cancel_event(appointment_id: str, user: Annotated[User, Depends(get_current_user)]):
#     appt = await Appointment.get_or_none(id=appointment_id, user=user)
#     if not appt:
#         _err(404, "Appointment not found")

#     link = await AppointmentExternalLink.get_or_none(appointment=appt)
#     if link:
#         acc = await CalendarAccount.get_or_none(id=link.account_id, user=user)
#         if acc and acc.provider == "google":
#             await _ensure_access_token(acc)
#             params = {"sendUpdates": GOOGLE_SEND_UPDATES}
#             async with httpx.AsyncClient(timeout=30.0) as client:
#                 url = f"{GOOGLE_API_BASE}/calendars/{link.external_calendar_id or 'primary'}/events/{link.external_event_id}"
#                 r = await client.delete(url, headers=_bearer_headers(acc.access_token), params=params)
#             if r.status_code not in (200, 204):
#                 _err(400, f"Google cancel failed: {r.text}")
#         # For Cal.com/Calendly, the canonical cancel is done in provider,
#         # and webhook will mark it cancelled here.
#         await link.delete()

#     appt.status = AppointmentStatus.CANCELLED
#     await appt.save()
#     return {"ok": True}

# # ──────────────────────────────────────────────────────────────────────────────
# # Scheduling Links (Cal.com & Calendly)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.post("/calendar/calcom/scheduling-link")
# async def calcom_scheduling_link(body: SchedulingLinkBody, user: Annotated[User, Depends(get_current_user)]):
#     acc = await _pick_account(user, body.account_id, provider="calcom")
#     if not body.event_type:
#         _err(400, "event_type (Cal.com event type slug) is required")
#     payload = {
#         "eventType": body.event_type,
#         "maxEvents": body.max_event_count,
#     }
#     # verify endpoint; Cal.com has /scheduling-link or /links/schedule depending on version
#     async with httpx.AsyncClient(timeout=20.0) as client:
#         r = await client.post(f"{CALCOM_API_BASE}/scheduling-link", headers=_bearer_headers(acc.access_token), content=json.dumps(payload))
#     if r.status_code not in (200, 201):
#         _err(400, f"Cal.com link failed: {r.text}")
#     data = r.json() or {}
#     url = data.get("url") or data.get("bookingLink") or data.get("link")
#     return {"ok": True, "url": url}

# @router.post("/calendar/calendly/scheduling-link")
# async def calendly_scheduling_link(body: SchedulingLinkBody, user: Annotated[User, Depends(get_current_user)]):
#     acc = await _pick_account(user, body.account_id, provider="calendly")
#     if not body.event_type:
#         _err(400, "event_type (Calendly event type URI) is required")
#     payload = {
#         "owner": body.owner or (await _calendly_user_uri(acc.access_token)),
#         "max_event_count": body.max_event_count,
#         "owner_type": "User",  # or "Organization" if using org-level event types
#         "event_type": body.event_type,
#     }
#     async with httpx.AsyncClient(timeout=20.0) as client:
#         r = await client.post(f"{CALENDLY_API_BASE}/scheduling_links", headers=_bearer_headers(acc.access_token), content=json.dumps(payload))
#     if r.status_code not in (200, 201):
#         _err(400, f"Calendly link failed: {r.text}")
#     data = r.json() or {}
#     resource = data.get("resource") or data.get("data") or {}
#     return {"ok": True, "url": resource.get("booking_url")}

# async def _calendly_user_uri(token: str) -> str:
#     async with httpx.AsyncClient(timeout=15.0) as client:
#         r = await client.get(f"{CALENDLY_API_BASE}/users/me", headers=_bearer_headers(token))
#     if r.status_code == 200:
#         me = r.json() or {}
#         res = me.get("resource") or me.get("data") or {}
#         return res.get("uri") or ""
#     return ""

# # ──────────────────────────────────────────────────────────────────────────────
# # Sync (Google + Cal.com + Calendly)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.post("/calendar/sync")
# async def sync_calendar(body: SyncBody, user: Annotated[User, Depends(get_current_user)]):
#     start = body.start_at or (_now_utc() - timedelta(days=30))
#     end   = body.end_at   or (_now_utc() + timedelta(days=60))

#     q = CalendarAccount.filter(user=user)
#     if body.account_ids:
#         q = q.filter(id__in=body.account_ids)
#     accounts = await q.all()
#     if not accounts:
#         return {"synced": 0, "created": 0, "updated": 0}

#     total_synced = 0
#     created = 0
#     updated = 0

#     for acc in accounts:
#         provider = acc.provider
#         try:
#             if provider == "google":
#                 await _ensure_access_token(acc)
#                 calendar_id = acc.primary_calendar_id or "primary"
#                 params = {
#                     "timeMin": _iso(start),
#                     "timeMax": _iso(end),
#                     "singleEvents": "true",
#                     "orderBy": "startTime",
#                     "showDeleted": "false",
#                     "maxResults": 2500,
#                 }
#                 async with httpx.AsyncClient(timeout=45.0) as client:
#                     url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events"
#                     r = await client.get(url, headers=_bearer_headers(acc.access_token), params=params)
#                 if r.status_code != 200:
#                     continue
#                 events = (r.json() or {}).get("items", [])
#                 for ev in events:
#                     total_synced += 1
#                     try:
#                         mapped = _map_google_event_to_appt(ev)
#                         created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
#                     except Exception:
#                         continue

#             elif provider == "calcom":
#                 params = {"startTime": _iso(start), "endTime": _iso(end)}
#                 async with httpx.AsyncClient(timeout=45.0) as client:
#                     r = await client.get(f"{CALCOM_API_BASE}/bookings", headers=_bearer_headers(acc.access_token), params=params)
#                 if r.status_code != 200:
#                     continue
#                 items = r.json() or {}
#                 bookings = items.get("data") if isinstance(items, dict) else items
#                 bookings = bookings or []
#                 for b in bookings:
#                     total_synced += 1
#                     try:
#                         mapped = _map_calcom_booking_to_appt(b)
#                         created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
#                     except Exception:
#                         continue

#             elif provider == "calendly":
#                 params = {"min_start_time": _iso(start), "max_start_time": _iso(end)}
#                 async with httpx.AsyncClient(timeout=45.0) as client:
#                     r = await client.get(f"{CALENDLY_API_BASE}/scheduled_events", headers=_bearer_headers(acc.access_token), params=params)
#                 if r.status_code != 200:
#                     continue
#                 items = r.json() or {}
#                 events = items.get("collection") or items.get("data") or []
#                 for ev in events:
#                     total_synced += 1
#                     # We need invitee to get per-attendee info; fetch one invitee (first)
#                     ev_uri = ev.get("uri")
#                     try:
#                         inv = {}
#                         if ev_uri:
#                             async with httpx.AsyncClient(timeout=20.0) as client:
#                                 r2 = await client.get(f"{CALENDLY_API_BASE}/scheduled_events/{ev.get('uuid')}/invitees", headers=_bearer_headers(acc.access_token))
#                             if r2.status_code == 200:
#                                 invs = r2.json() or {}
#                                 coll = invs.get("collection") or []
#                                 inv = coll[0] if coll else {}
#                         payload = {"event": ev, "invitee": inv, "status": ev.get("status")}
#                         mapped = _map_calendly_event_to_appt(payload)
#                         created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
#                     except Exception:
#                         continue

#         except Exception:
#             continue

#     return {"synced": total_synced, "created": created, "updated": updated}

# async def _upsert_from_mapped(user: User, acc: CalendarAccount, mapped: Dict[str, Any], created: int, updated: int):
#     ext_id = mapped["external_event_id"]
#     link = await AppointmentExternalLink.get_or_none(provider=acc.provider, external_event_id=ext_id)
#     if link:
#         appt = await Appointment.get_or_none(id=link.appointment_id, user=user)
#         if not appt:
#             appt = await Appointment.create(user=user, **mapped["appt_fields"])
#             link.appointment = appt
#             link.external_calendar_id = mapped.get("external_calendar_id") or link.external_calendar_id
#             await link.save()
#             created += 1
#         else:
#             for k, v in mapped["appt_fields"].items():
#                 setattr(appt, k, v)
#             await appt.save()
#             updated += 1
#     else:
#         appt = await Appointment.create(user=user, **mapped["appt_fields"])
#         await AppointmentExternalLink.create(
#             appointment=appt, account=acc, provider=acc.provider,
#             external_event_id=ext_id, external_calendar_id=mapped.get("external_calendar_id")
#         )
#         created += 1
#     return created, updated

# # ──────────────────────────────────────────────────────────────────────────────
# # Free/Busy (Google only)
# # ──────────────────────────────────────────────────────────────────────────────

# @router.post("/calendar/freebusy")
# async def freebusy(body: FreeBusyBody, user: Annotated[User, Depends(get_current_user)]):
#     acc = await _pick_account(user, body.account_id, provider="google")
#     await _ensure_access_token(acc)
#     calendars = body.calendar_ids or [acc.primary_calendar_id or "primary"]
#     req = {"timeMin": _iso(body.start_at), "timeMax": _iso(body.end_at), "items": [{"id": cid} for cid in calendars]}
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         url = f"{GOOGLE_API_BASE}/freeBusy"
#         r = await client.post(url, headers=_bearer_headers(acc.access_token), content=json.dumps(req))
#     if r.status_code != 200:
#         _err(400, f"freeBusy failed: {r.text}")
#     fb = r.json() or {}
#     return {"ok": True, "freebusy": fb.get("calendars", {}), "start_at": _iso(body.start_at), "end_at": _iso(body.end_at)}

# # ──────────────────────────────────────────────────────────────────────────────
# # Webhooks (Cal.com + Calendly) → Upsert into appointments
# # ──────────────────────────────────────────────────────────────────────────────

# def _verify_calcom_signature(raw_body: bytes, signature_hex: str) -> bool:
#     if not CALCOM_WEBHOOK_SECRET:
#         return True
#     try:
#         mac = hmac.new(CALCOM_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
#         return hmac.compare_digest(mac, (signature_hex or "").lower())
#     except Exception:
#         return False

# def _verify_calendly_signature(raw_body: bytes, signature_header: str) -> bool:
#     # Header format: "t=timestamp,v1=signature"
#     if not CALENDLY_WEBHOOK_SIGNING_KEY:
#         return True
#     try:
#         parts = dict(
#             x.split("=", 1) for x in (signature_header or "").split(",") if "=" in x
#         )
#         t = parts.get("t")
#         v1 = parts.get("v1")
#         base = f"{t}.{raw_body.decode()}".encode()
#         mac = hmac.new(CALENDLY_WEBHOOK_SIGNING_KEY.encode(), base, hashlib.sha256).hexdigest()
#         return hmac.compare_digest(mac, v1 or "")
#     except Exception:
#         return False

# @router.post("/calendar/webhook/calcom")
# async def calcom_webhook(
#     request: Request,
#     x_cal_signature_256: Optional[str] = Header(None)  # typical header name (verify in dashboard)
# ):
#     raw = await request.body()
#     if not _verify_calcom_signature(raw, x_cal_signature_256 or ""):
#         _err(401, "Invalid Cal.com signature")

#     payload = json.loads(raw.decode() or "{}")
#     event = (payload.get("type") or payload.get("event") or "").lower()
#     data = payload.get("data") or payload.get("payload") or payload

#     # Identify which account this belongs to (if webhook is per-user, include account_id in URL or metadata)
#     # Fallback: pick any Cal.com account; ideally store webhook → account mapping
#     acc = await CalendarAccount.filter(provider="calcom").first()
#     if not acc:
#         return {"ok": True}

#     # Map booking to appointment
#     try:
#         b = data.get("booking") if isinstance(data, dict) and "booking" in data else data
#         mapped = _map_calcom_booking_to_appt(b)
#         # cancel semantics
#         if "cancel" in event:
#             mapped["appt_fields"]["status"] = AppointmentStatus.CANCELLED
#         # Link to a user (multi-tenant): if you store user_id in webhook secret/id, map here.
#         # Fallback: use the account's user
#         user = await User.get(id=acc.user_id)
#         created, updated = 0, 0
#         created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
#     except Exception:
#         pass

#     return {"ok": True}

# @router.post("/calendar/webhook/calendly")
# async def calendly_webhook(
#     request: Request,
#     calendly_webhook_signature: Optional[str] = Header(None, alias="Calendly-Webhook-Signature")
# ):
#     raw = await request.body()
#     if not _verify_calendly_signature(raw, calendly_webhook_signature or ""):
#         _err(401, "Invalid Calendly signature")

#     payload = json.loads(raw.decode() or "{}")
#     topic = (payload.get("event") or payload.get("event_type") or "").lower()
#     data = payload.get("payload") or payload.get("data") or {}

#     # Fallback account (ideally map webhook → account)
#     acc = await CalendarAccount.filter(provider="calendly").first()
#     if not acc:
#         return {"ok": True}

#     # Normalize and upsert
#     try:
#         status_str = "cancelled" if "cancel" in topic else "confirmed"
#         data["status"] = status_str
#         mapped = _map_calendly_event_to_appt(data)
#         user = await User.get(id=acc.user_id)
#         created, updated = 0, 0
#         created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
#     except Exception:
#         pass

#     return {"ok": True}
# -*- coding: utf-8 -*-
import os
import hmac
import base64
import json
import hashlib
import secrets
from typing import Annotated, Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone, date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, validator
from tortoise.expressions import Q

from helpers.token_helper import get_current_user
from models.auth import User
from models.appointment import Appointment, AppointmentStatus
from models.calendar_account import CalendarAccount
from models.appointment_link import AppointmentExternalLink

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Config (env)
# ──────────────────────────────────────────────────────────────────────────────

PUBLIC_BASE = os.getenv("CAL_PUBLIC_BASE", "http://localhost:8000").rstrip("/")
STATE_SECRET = os.getenv("CAL_OAUTH_STATE_SECRET", "dev-state-secret-change-me")

# ===== Google =====
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/google/callback")

GOOGLE_AUTH_URL  = os.getenv("GOOGLE_AUTH_URL",  "https://accounts.google.com/o/oauth2/v2/auth")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
GOOGLE_API_BASE  = os.getenv("GOOGLE_API_BASE",  "https://www.googleapis.com/calendar/v3")

GOOGLE_SCOPES = os.getenv("GOOGLE_SCOPES", "https://www.googleapis.com/auth/calendar")
GOOGLE_SEND_UPDATES = os.getenv("GOOGLE_SEND_UPDATES", "none")  # all | externalOnly | none

# ===== Cal.com (v2) =====
CALCOM_CLIENT_ID     = os.getenv("CALCOM_CLIENT_ID", "")
CALCOM_CLIENT_SECRET = os.getenv("CALCOM_CLIENT_SECRET", "")
CALCOM_REDIRECT_URI  = os.getenv("CALCOM_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/calcom/callback")
CALCOM_AUTH_URL      = os.getenv("CALCOM_AUTH_URL", "https://api.cal.com/oauth/authorize")
CALCOM_TOKEN_URL     = os.getenv("CALCOM_TOKEN_URL", "https://api.cal.com/oauth/token")
CALCOM_API_BASE      = os.getenv("CALCOM_API_BASE", "https://api.cal.com/v2")
CALCOM_API_VERSION   = os.getenv("CALCOM_API_VERSION", "2024-06-14")
# Global fallback secret (prefer per-account secret)
CALCOM_WEBHOOK_SECRET = os.getenv("CALCOM_WEBHOOK_SECRET", "")

# ===== Calendly =====
CALENDLY_CLIENT_ID     = os.getenv("CALENDLY_CLIENT_ID", "")
CALENDLY_CLIENT_SECRET = os.getenv("CALENDLY_CLIENT_SECRET", "")
CALENDLY_REDIRECT_URI  = os.getenv("CALENDLY_REDIRECT_URI", f"{PUBLIC_BASE}/api/calendar/oauth/calendly/callback")
CALENDLY_AUTH_URL      = os.getenv("CALENDLY_AUTH_URL", "https://auth.calendly.com/oauth/authorize")
CALENDLY_TOKEN_URL     = os.getenv("CALENDLY_TOKEN_URL", "https://auth.calendly.com/oauth/token")
CALENDLY_API_BASE      = os.getenv("CALENDLY_API_BASE", "https://api.calendly.com")
# Global fallback signing key (prefer per-account signing key)
CALENDLY_WEBHOOK_SIGNING_KEY = os.getenv("CALENDLY_WEBHOOK_SIGNING_KEY", "")

# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ConnectUrl(BaseModel):
    provider: str
    auth_url: str

class TokenConnectBody(BaseModel):
    api_key: str = Field(..., min_length=8, max_length=4096)  # PAT

class CreateEventBody(BaseModel):
    title: str = Field(..., max_length=200)
    start_at: datetime
    end_at: datetime
    phone: str = Field(..., max_length=32)
    timezone: str = Field(..., max_length=64)
    location: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    account_id: Optional[str] = None          # CalendarAccount.id
    calendar_id: Optional[str] = None         # override default/primary

    # Optional attendee info (Cal.com / Calendly style)
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    # Optional Cal.com event type (slug) or Calendly event type URI
    event_type: Optional[str] = None

    @validator("end_at")
    def _range(cls, v, values):
        s = values.get("start_at")
        if s and v <= s:
            raise ValueError("end_at must be after start_at")
        return v

class UpdateEventBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    phone: Optional[str] = Field(None, max_length=32)
    timezone: Optional[str] = Field(None, max_length=64)
    location: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    calendar_id: Optional[str] = None  # allow move across calendars

class SyncBody(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    account_ids: Optional[List[str]] = None

class FreeBusyBody(BaseModel):
    start_at: datetime
    end_at: datetime
    account_id: Optional[str] = None
    calendar_ids: Optional[List[str]] = None

class SchedulingLinkBody(BaseModel):
    account_id: Optional[str] = None
    event_type: str
    max_event_count: int = 1
    owner: Optional[str] = None

class GoogleImportBody(BaseModel):
    account_id: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    calendar_ids: Optional[List[str]] = None

class CalendlyWebhookRegisterBody(BaseModel):
    account_id: Optional[str] = None
    # usually these two events are enough to mirror bookings
    events: List[str] = Field(default_factory=lambda: ["invitee.created", "invitee.canceled"])
    scope: str = "organization"  # or "user"

class CalcomWebhookRegisterBody(BaseModel):
    account_id: Optional[str] = None
    # if empty, we will generate & store a secret and return it for UI setup
    secret: Optional[str] = None

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(data)

def _err(code: int, msg: str) -> None:
    raise HTTPException(status_code=code, detail=msg)

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)

def _mk_state(user_id: int, provider: str) -> str:
    ts = str(int(_now_utc().timestamp()))
    payload = f"{user_id}:{provider}:{ts}"
    mac = hmac.new(STATE_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(f"{payload}:{mac.hex()}".encode()).decode()

def _parse_state(state: str) -> Tuple[int, str]:
    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 4:
            raise ValueError("bad state format")
        uid_s, provider, ts, mac_hex = parts
        payload = f"{uid_s}:{provider}:{ts}"
        exp_mac = hmac.new(STATE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac_hex, exp_mac):
            raise ValueError("bad state mac")
        if (int(_now_utc().timestamp()) - int(ts)) > 900:
            raise ValueError("state expired")
        return int(uid_s), provider
    except Exception as e:
        _err(status.HTTP_400_BAD_REQUEST, f"Invalid state: {e}")

def _headers_json() -> Dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json"}

def _headers_google(token: str) -> Dict[str, str]:
    return {**_headers_json(), "Authorization": f"Bearer {token}"}

def _headers_calcom(token: str) -> Dict[str, str]:
    h = {**_headers_json(), "Authorization": f"Bearer {token}"}
    if CALCOM_API_VERSION:
        h["cal-api-version"] = CALCOM_API_VERSION
    # some gateways still accept x-api-key
    h["x-api-key"] = token
    return h

def _headers_calendly(token: str) -> Dict[str, str]:
    return {**_headers_json(), "Authorization": f"Bearer {token}"}

def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def _is_all_day(start_at: datetime, end_at: datetime) -> bool:
    s = start_at.astimezone(timezone.utc)
    e = end_at.astimezone(timezone.utc)
    return (
        s.hour == s.minute == s.second == 0
        and e.hour == e.minute == e.second == 0
        and (e - s).total_seconds() >= 86400
        and ((e - s).total_seconds() % 86400 == 0)
    )

def _google_time_block(start_at: datetime, end_at: datetime, tz: str) -> Dict[str, Any]:
    if _is_all_day(start_at, end_at):
        return {"start": {"date": start_at.date().isoformat()}, "end": {"date": end_at.date().isoformat()}}
    return {"start": {"dateTime": _iso(start_at), "timeZone": tz}, "end": {"dateTime": _iso(end_at), "timeZone": tz}}

def _event_status_to_appt_status(ev_status: str, start_at: datetime, end_at: datetime) -> AppointmentStatus:
    s = (ev_status or "").lower()
    if "cancel" in s or s == "cancelled":
        return AppointmentStatus.CANCELLED
    return AppointmentStatus.COMPLETED if end_at <= _now_utc() else AppointmentStatus.SCHEDULED

def _parse_dt_guess(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, dict):
        if "dateTime" in v: return _parse_dt_guess(v["dateTime"])
        if "date" in v:
            try:
                d = date.fromisoformat(v["date"])
                return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            except Exception:
                return None
    if isinstance(v, (int, float)): return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str):
        s = v.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except Exception:
            try:
                return datetime.fromisoformat(s[:19] + "+00:00")
            except Exception:
                return None
    return None

# ──────────────────────────────────────────────────────────────────────────────
# Google mappers
# ──────────────────────────────────────────────────────────────────────────────

def _map_google_event_to_appt(ev: Dict[str, Any]) -> Dict[str, Any]:
    external_id = ev.get("id") or secrets.token_hex(8)
    calendar_id = ev.get("organizer", {}).get("email") or ev.get("calendarId") or ev.get("creator", {}).get("email")
    title = ev.get("summary") or "Appointment"
    description = ev.get("description") or ""
    location = ev.get("location") or ""
    status_s = ev.get("status") or "confirmed"
    start_at = _parse_dt_guess(ev.get("start"))
    end_at = _parse_dt_guess(ev.get("end"))
    if not (start_at and end_at):
        raise ValueError("missing times")
    tz = "UTC"
    if isinstance(ev.get("start"), dict) and ev["start"].get("timeZone"):
        tz = ev["start"]["timeZone"]
    duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))
    status = _event_status_to_appt_status(status_s, start_at, end_at)
    return {
        "external_event_id": str(external_id),
        "external_calendar_id": calendar_id,
        "appt_fields": {
            "title": title[:200],
            "notes": description or None,
            "location": (location or None),
            "phone": "unknown",
            "timezone": tz[:64],
            "start_at": start_at,
            "end_at": end_at,
            "duration_minutes": duration_minutes,
            "status": status,
        },
    }

# ──────────────────────────────────────────────────────────────────────────────
# Cal.com mappers
# ──────────────────────────────────────────────────────────────────────────────

def _map_calcom_booking_to_appt(b: Dict[str, Any]) -> Dict[str, Any]:
    ext_id = str(b.get("id") or b.get("uid") or b.get("bookingUid") or secrets.token_hex(8))
    title = (b.get("title") or "Cal.com booking")[:200]
    description = b.get("description") or b.get("notes") or ""
    location = b.get("location") or b.get("videoCallUrl") or ""
    tz = b.get("timezone") or "UTC"
    start_at = _parse_dt_guess(b.get("startTime") or b.get("start") or b.get("start_time"))
    end_at   = _parse_dt_guess(b.get("endTime")   or b.get("end")   or b.get("end_time"))
    status_s = (b.get("status") or "confirmed").lower()
    if not (start_at and end_at):
        raise ValueError("missing times")
    duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))
    status = _event_status_to_appt_status(status_s, start_at, end_at)
    return {
        "external_event_id": ext_id,
        "external_calendar_id": b.get("calendarId") or b.get("eventType") or None,
        "appt_fields": {
            "title": title,
            "notes": description or None,
            "location": (location or None),
            "phone": "unknown",
            "timezone": tz[:64],
            "start_at": start_at,
            "end_at": end_at,
            "duration_minutes": duration_minutes,
            "status": status,
        },
    }

# ──────────────────────────────────────────────────────────────────────────────
# Calendly mappers
# ──────────────────────────────────────────────────────────────────────────────

def _map_calendly_event_to_appt(payload: Dict[str, Any]) -> Dict[str, Any]:
    ev = payload.get("event") or {}
    invitee = payload.get("invitee") or {}
    # ev may be wrapped as {"resource":{...}}
    if isinstance(ev, dict) and "resource" in ev and isinstance(ev["resource"], dict):
        ev = ev["resource"]
    if isinstance(invitee, dict) and "resource" in invitee and isinstance(invitee["resource"], dict):
        invitee = invitee["resource"]

    ext_id = ev.get("uuid") or (ev.get("uri") or "").split("/")[-1] or secrets.token_hex(8)
    title = (ev.get("name") or ev.get("event_type") or "Calendly booking")[:200]
    description = invitee.get("text_reminder_number") or invitee.get("questions_and_answers") or ""
    location = ev.get("location", {}).get("location") if isinstance(ev.get("location"), dict) else (ev.get("location") or "")

    start_at = _parse_dt_guess(ev.get("start_time"))
    end_at   = _parse_dt_guess(ev.get("end_time"))
    tz = invitee.get("timezone") or "UTC"
    if not (start_at and end_at):
        raise ValueError("missing times")
    duration_minutes = max(1, int((end_at - start_at).total_seconds() // 60))

    status_s = payload.get("status") or payload.get("event_type") or "confirmed"
    status = _event_status_to_appt_status(status_s, start_at, end_at)

    return {
        "external_event_id": str(ext_id),
        "external_calendar_id": ev.get("event_type") or None,
        "appt_fields": {
            "title": title,
            "notes": description or None,
            "location": (location or None),
            "phone": invitee.get("sms_number") or "unknown",
            "timezone": tz[:64],
            "start_at": start_at,
            "end_at": end_at,
            "duration_minutes": duration_minutes,
            "status": status,
        },
    }

# ──────────────────────────────────────────────────────────────────────────────
# Providers / Accounts
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/calendar/providers")
async def list_calendar_providers(user: Annotated[User, Depends(get_current_user)]):
    return {
        "providers": [
            {
                "key": "google",
                "name": "Google Calendar",
                "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
                "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/google",
                "supports": ["oauth", "crud", "sync", "freebusy", "list"],
            },
            {
                "key": "calcom",
                "name": "Cal.com",
                "configured": True,
                "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calcom",
                "connect_token_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calcom/token",
                "webhook_register_endpoint": f"{PUBLIC_BASE}/api/calendar/calcom/webhook/register",
                "webhook_url": f"{PUBLIC_BASE}/api/calendar/webhook/calcom",
                "supports": ["token", "webhooks", "scheduling_links", "sync", "list"],
            },
            {
                "key": "calendly",
                "name": "Calendly",
                "configured": True,
                "connect_url_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calendly",
                "connect_token_endpoint": f"{PUBLIC_BASE}/api/calendar/connect/calendly/token",
                "webhook_register_endpoint": f"{PUBLIC_BASE}/api/calendar/calendly/webhook/register",
                "webhook_url": f"{PUBLIC_BASE}/api/calendar/webhook/calendly",
                "supports": ["token", "webhooks", "scheduling_links", "sync", "list"],
            },
        ]
    }

@router.get("/calendar/accounts")
async def list_calendar_accounts(user: Annotated[User, Depends(get_current_user)]):
    rows = await CalendarAccount.filter(user=user).order_by("-created_at").values()
    return rows

@router.delete("/calendar/accounts/{account_id}")
async def disconnect_calendar_account(account_id: str, user: Annotated[User, Depends(get_current_user)]):
    acc = await CalendarAccount.get_or_none(id=account_id, user=user)
    if not acc:
        _err(404, "Account not found")
    await AppointmentExternalLink.filter(account=acc).delete()
    await acc.delete()
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# Google OAuth – unchanged
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/calendar/connect/google")
async def calendar_connect_google(user: Annotated[User, Depends(get_current_user)]):
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        _err(400, "Google not configured")
    state = _mk_state(user.id, "google")
    from urllib.parse import urlencode
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    return ConnectUrl(provider="google", auth_url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")

async def _google_exchange_code_for_token(code: str) -> Dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GOOGLE_TOKEN_URL, data=data)
    if r.status_code != 200:
        _err(400, f"Token exchange failed: {r.text}")
    return r.json()

async def _google_refresh_token(refresh_token: str) -> Dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GOOGLE_TOKEN_URL, data=data)
    if r.status_code != 200:
        _err(400, f"Refresh failed: {r.text}")
    return r.json()

async def _ensure_access_token(account: CalendarAccount) -> CalendarAccount:
    if account.expires_at and account.expires_at > _now_utc() + timedelta(seconds=60):
        return account
    if account.provider == "google" and account.refresh_token:
        tok = await _google_refresh_token(account.refresh_token)
        account.access_token = tok.get("access_token", account.access_token)
        account.refresh_token = tok.get("refresh_token", account.refresh_token)
        account.expires_at = _now_utc() + timedelta(seconds=int(tok.get("expires_in") or 3600))
        await account.save()
    return account

@router.get("/calendar/oauth/google/callback", response_class=HTMLResponse)
async def calendar_oauth_callback_google(request: Request):
    q = request.query_params
    code = q.get("code")
    state = q.get("state")
    if not (code and state):
        _err(400, "Missing code/state")

    user_id, provider = _parse_state(state)
    if provider != "google":
        _err(400, "Provider mismatch")

    token = await _google_exchange_code_for_token(code)
    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    expires_in = int(token.get("expires_in") or 3600)
    scope = token.get("scope") or GOOGLE_SCOPES

    if not access_token:
        _err(400, "Google did not return access_token")

    primary_calendar_id = None
    external_email = None
    external_account_id = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{GOOGLE_API_BASE}/users/me/calendarList"
            r = await client.get(url, headers=_headers_google(access_token))
        if r.status_code == 200:
            data = r.json() or {}
            for item in data.get("items", []):
                if item.get("primary"):
                    primary_calendar_id = item.get("id")
                    external_email = item.get("id")
                    external_account_id = external_email
                    break
            if not primary_calendar_id and data.get("items"):
                primary_calendar_id = data["items"][0].get("id")
                external_email = data["items"][0].get("id")
                external_account_id = external_email
    except Exception:
        pass

    acc = await CalendarAccount.get_or_none(
        user_id=user_id, provider="google", external_account_id=external_account_id or external_email
    )
    if not acc:
        acc = await CalendarAccount.create(
            user_id=user_id,
            provider="google",
            external_account_id=external_account_id or "google",
            external_email=external_email,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=_now_utc() + timedelta(seconds=expires_in),
            primary_calendar_id=primary_calendar_id,
        )
    else:
        acc.external_email = external_email
        acc.access_token = access_token
        acc.refresh_token = refresh_token or acc.refresh_token
        acc.scope = scope
        acc.expires_at = _now_utc() + timedelta(seconds=expires_in)
        acc.primary_calendar_id = primary_calendar_id or acc.primary_calendar_id
        await acc.save()

    return HTMLResponse("<h3>Google Calendar connected ✅</h3>You can close this window.", status_code=200)

# ──────────────────────────────────────────────────────────────────────────────
# Cal.com & Calendly connect (token)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/calendar/connect/calcom")
async def calendar_connect_calcom(user: Annotated[User, Depends(get_current_user)]):
    if not (CALCOM_CLIENT_ID and CALCOM_CLIENT_SECRET):
        _err(400, "Cal.com OAuth not configured (use /calendar/connect/calcom/token for PAT)")
    from urllib.parse import urlencode
    state = _mk_state(user.id, "calcom")
    params = {
        "client_id": CALCOM_CLIENT_ID,
        "redirect_uri": CALCOM_REDIRECT_URI,
        "response_type": "code",
        "scope": "booking:read booking:write",
        "state": state,
        "prompt": "consent",
    }
    return ConnectUrl(provider="calcom", auth_url=f"{CALCOM_AUTH_URL}?{urlencode(params)}")

@router.post("/calendar/connect/calcom/token")
async def calendar_connect_calcom_token(body: TokenConnectBody, user: Annotated[User, Depends(get_current_user)]):
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{CALCOM_API_BASE}/me", headers=_headers_calcom(body.api_key))
    if r.status_code != 200:
        # Legacy fallback: try v1 + x-api-key
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r_legacy = await client.get("https://api.cal.com/v1/me", headers={"x-api-key": body.api_key, "Accept": "application/json"})
            if r_legacy.status_code == 200:
                me = r_legacy.json() or {}
            else:
                _err(400, f"Cal.com token invalid: {r.text}")
        except Exception:
            _err(400, f"Cal.com token invalid: {r.text}")
    else:
        me = r.json() or {}

    external_email = me.get("email") or me.get("username") or "calcom"
    external_account_id = str(me.get("id") or external_email)

    acc = await CalendarAccount.get_or_none(user=user, provider="calcom", external_account_id=external_account_id)
    if not acc:
        acc = await CalendarAccount.create(
            user=user,
            provider="calcom",
            external_account_id=external_account_id,
            external_email=external_email,
            access_token=body.api_key,
            scope="token",
            api_version=CALCOM_API_VERSION,
            primary_calendar_id=None,
        )
    else:
        acc.external_email = external_email
        acc.access_token = body.api_key
        acc.api_version = CALCOM_API_VERSION
        await acc.save()
    return {"ok": True, "account_id": str(acc.id)}

@router.get("/calendar/connect/calendly")
async def calendar_connect_calendly(user: Annotated[User, Depends(get_current_user)]):
    if not (CALENDLY_CLIENT_ID and CALENDLY_CLIENT_SECRET):
        _err(400, "Calendly OAuth not configured (use /calendar/connect/calendly/token instead)")
    from urllib.parse import urlencode
    state = _mk_state(user.id, "calendly")
    params = {
        "client_id": CALENDLY_CLIENT_ID,
        "redirect_uri": CALENDLY_REDIRECT_URI,
        "response_type": "code",
        "scope": "default",
        "state": state,
        "prompt": "consent",
    }
    return ConnectUrl(provider="calendly", auth_url=f"{CALENDLY_AUTH_URL}?{urlencode(params)}")

@router.post("/calendar/connect/calendly/token")
async def calendar_connect_calendly_token(body: TokenConnectBody, user: Annotated[User, Depends(get_current_user)]):
    # get user + org
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{CALENDLY_API_BASE}/users/me", headers=_headers_calendly(body.api_key))
    if r.status_code != 200:
        _err(400, f"Calendly token invalid: {r.text}")
    me = r.json() or {}
    res_user = me.get("resource") or me.get("data") or {}
    external_email = res_user.get("email") or "calendly"
    external_account_id = res_user.get("uri") or external_email
    external_org = res_user.get("current_organization") or res_user.get("organization") or None

    acc = await CalendarAccount.get_or_none(user=user, provider="calendly", external_account_id=external_account_id)
    if not acc:
        acc = await CalendarAccount.create(
            user=user,
            provider="calendly",
            external_account_id=external_account_id,
            external_email=external_email,
            external_org_id=external_org,
            access_token=body.api_key,
            scope="token",
            primary_calendar_id=None,
        )
    else:
        acc.external_email = external_email
        acc.external_org_id = external_org or acc.external_org_id
        acc.access_token = body.api_key
        await acc.save()

    # Optional: auto-register webhook (safe to call later via dedicated endpoint)
    # return await calendly_register_webhook(CalendlyWebhookRegisterBody(account_id=str(acc.id)), user)
    return {"ok": True, "account_id": str(acc.id)}

# ──────────────────────────────────────────────────────────────────────────────
# Pick account helper
# ──────────────────────────────────────────────────────────────────────────────

async def _pick_account(user: User, account_id: Optional[str], provider: Optional[str] = None) -> CalendarAccount:
    q = CalendarAccount.filter(user=user)
    if provider:
        q = q.filter(provider=provider)
    if account_id:
        q = q.filter(id=account_id)
    acc = await q.order_by("-created_at").first()
    if not acc:
        _err(400, f"No connected {provider or 'calendar'} account")
    return acc

# ──────────────────────────────────────────────────────────────────────────────
# Google list calendars (for frontend)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/calendar/google/calendars")
async def google_list_calendars(
    user: Annotated[User, Depends(get_current_user)],
    account_id: Optional[str] = Query(None, description="CalendarAccount id (google). Defaults to latest."),
):
    acc = await _pick_account(user, account_id, provider="google")
    await _ensure_access_token(acc)
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{GOOGLE_API_BASE}/users/me/calendarList", headers=_headers_google(acc.access_token))
    if r.status_code != 200:
        _err(400, f"Google calendarList failed: {r.text}")
    data = r.json() or {}
    return {"items": data.get("items", [])}

# ──────────────────────────────────────────────────────────────────────────────
# Events: Create / Update / Cancel
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/events")
async def create_event(body: CreateEventBody, user: Annotated[User, Depends(get_current_user)]):
    acc = await _pick_account(user, body.account_id)
    if acc.provider == "google":
        await _ensure_access_token(acc)
        calendar_id = body.calendar_id or acc.primary_calendar_id or "primary"
        time_block = _google_time_block(body.start_at, body.end_at, body.timezone)
        payload = {
            "summary": body.title,
            "description": body.notes or "",
            "location": body.location or "",
            **time_block,
            "status": "confirmed",
            "reminders": {"useDefault": True},
        }
        params = {"sendUpdates": GOOGLE_SEND_UPDATES}
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events"
            r = await client.post(url, headers=_headers_google(acc.access_token), params=params, content=json.dumps(payload))
        if r.status_code not in (200, 201):
            _err(400, f"Google create failed: {r.text}")
        ev = r.json() or {}
        external_event_id = ev.get("id") or secrets.token_hex(8)
        appt = await Appointment.create(
            user=user,
            title=body.title, notes=body.notes, location=body.location,
            phone=body.phone or "unknown", timezone=body.timezone,
            start_at=body.start_at, end_at=body.end_at,
            duration_minutes=int((body.end_at - body.start_at).total_seconds() // 60),
            status=_event_status_to_appt_status(ev.get("status", "confirmed"), body.start_at, body.end_at),
        )
        await AppointmentExternalLink.create(
            appointment=appt, account=acc, provider="google",
            external_event_id=external_event_id, external_calendar_id=calendar_id,
        )
        return {"ok": True, "appointment_id": str(appt.id), "provider": "google", "external_event_id": external_event_id}

    if acc.provider == "calcom":
        if body.event_type and body.attendee_email and body.attendee_name:
            payload = {
                "eventType": body.event_type,
                "startTime": _iso(body.start_at),
                "endTime": _iso(body.end_at),
                "title": body.title,
                "description": body.notes or "",
                "timezone": body.timezone,
                "location": body.location or "",
                "attendees": [{"name": body.attendee_name, "email": body.attendee_email}],
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{CALCOM_API_BASE}/bookings", headers=_headers_calcom(acc.access_token), content=json.dumps(payload))
            if r.status_code not in (200, 201):
                _err(400, f"Cal.com booking failed: {r.text}")
            b = r.json() or {}
            mapped = _map_calcom_booking_to_appt(b if isinstance(b, dict) else (b.get("data") or {}))
            appt = await Appointment.create(user=user, **mapped["appt_fields"])
            await AppointmentExternalLink.create(
                appointment=appt, account=acc, provider="calcom",
                external_event_id=mapped["external_event_id"],
                external_calendar_id=mapped.get("external_calendar_id"),
            )
            return {"ok": True, "appointment_id": str(appt.id), "provider": "calcom", "external_event_id": mapped["external_event_id"]}
        _err(400, "Cal.com direct booking needs event_type + attendee_name + attendee_email. Or use a scheduling link.")

    if acc.provider == "calendly":
        _err(400, "Calendly programmatic booking is limited. Use a scheduling link; webhook will mirror the booking.")

    _err(400, f"Unsupported provider: {acc.provider}")

@router.patch("/calendar/events/{appointment_id}")
async def update_event(appointment_id: str, body: UpdateEventBody, user: Annotated[User, Depends(get_current_user)]):
    appt = await Appointment.get_or_none(id=appointment_id, user=user)
    if not appt:
        _err(404, "Appointment not found")

    link = await AppointmentExternalLink.get_or_none(appointment=appt)
    if not link:
        _err(400, "No linked provider event for this appointment")

    acc = await CalendarAccount.get_or_none(id=link.account_id, user=user)
    if not acc:
        _err(400, "Linked account not found")

    if acc.provider == "google":
        await _ensure_access_token(acc)
        new_title = body.title or appt.title
        new_location = body.location if body.location is not None else appt.location
        new_notes = body.notes if body.notes is not None else appt.notes
        new_phone = body.phone or appt.phone
        new_tz = body.timezone or appt.timezone
        new_start = body.start_at or appt.start_at
        new_end = body.end_at or appt.end_at
        new_calendar = body.calendar_id or link.external_calendar_id or acc.primary_calendar_id or "primary"

        time_block = _google_time_block(new_start, new_end, new_tz)
        payload = {"summary": new_title, "description": new_notes or "", "location": new_location or "", **time_block, "status": "confirmed", "reminders": {"useDefault": True}}
        params = {"sendUpdates": GOOGLE_SEND_UPDATES}
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{GOOGLE_API_BASE}/calendars/{new_calendar}/events/{link.external_event_id}"
            r = await client.patch(url, headers=_headers_google(acc.access_token), params=params, content=json.dumps(payload))
        if r.status_code not in (200, 201):
            _err(400, f"Google update failed: {r.text}")

        appt.title = new_title
        appt.location = new_location
        appt.notes = new_notes
        appt.phone = new_phone
        appt.timezone = new_tz
        appt.start_at = new_start
        appt.end_at = new_end
        appt.duration_minutes = int((new_end - new_start).total_seconds() // 60)
        appt.status = _event_status_to_appt_status("confirmed", new_start, new_end)
        await appt.save()

        if new_calendar != link.external_calendar_id:
            link.external_calendar_id = new_calendar
            await link.save()

        return {"ok": True}

    _err(400, f"Update via API not supported for provider: {acc.provider}. Edit on provider or rebook; webhook will sync it.")

@router.delete("/calendar/events/{appointment_id}")
async def cancel_event(appointment_id: str, user: Annotated[User, Depends(get_current_user)]):
    appt = await Appointment.get_or_none(id=appointment_id, user=user)
    if not appt:
        _err(404, "Appointment not found")

    link = await AppointmentExternalLink.get_or_none(appointment=appt)
    if link:
        acc = await CalendarAccount.get_or_none(id=link.account_id, user=user)
        if acc and acc.provider == "google":
            await _ensure_access_token(acc)
            params = {"sendUpdates": GOOGLE_SEND_UPDATES}
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{GOOGLE_API_BASE}/calendars/{link.external_calendar_id or 'primary'}/events/{link.external_event_id}"
                r = await client.delete(url, headers=_headers_google(acc.access_token), params=params)
            if r.status_code not in (200, 204):
                _err(400, f"Google cancel failed: {r.text}")
        await link.delete()

    appt.status = AppointmentStatus.CANCELLED
    await appt.save()
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# List events (DB) + fetch one
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/calendar/events")
async def list_events(
    user: Annotated[User, Depends(get_current_user)],
    start_at: Optional[datetime] = Query(None),
    end_at: Optional[datetime] = Query(None),
    status: Optional[str] = Query(None, description="scheduled/completed/cancelled"),
    provider: Optional[str] = Query(None, description="google|calcom|calendly (filter via link)"),
    account_id: Optional[str] = Query(None, description="Filter by account id (via link)"),
    calendar_id: Optional[str] = Query(None, description="Filter by external calendar id (via link)"),
    q: Optional[str] = Query(None, description="Search title/notes/location"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    qry = Appointment.filter(user=user)
    if start_at:
        qry = qry.filter(end_at__gte=start_at)
    if end_at:
        qry = qry.filter(start_at__lte=end_at)
    if status:
        s = status.lower()
        if s in ("scheduled", "completed", "cancelled"):
            qry = qry.filter(status=getattr(AppointmentStatus, s.upper()))
    if q:
        qry = qry.filter(Q(title__icontains=q) | Q(notes__icontains=q) | Q(location__icontains=q))

    total = await qry.count()
    appts = await qry.order_by("start_at").offset(offset).limit(limit)
    ids = [a.id for a in appts]

    links_q = AppointmentExternalLink.filter(appointment_id__in=ids)
    if provider:
        links_q = links_q.filter(provider=provider)
    if account_id:
        links_q = links_q.filter(account_id=account_id)
    if calendar_id:
        links_q = links_q.filter(external_calendar_id=calendar_id)
    links = await links_q.all()
    by_appt = {}
    for l in links:
        by_appt.setdefault(l.appointment_id, []).append({
            "provider": l.provider,
            "account_id": str(l.account_id),
            "external_event_id": l.external_event_id,
            "external_calendar_id": l.external_calendar_id,
        })

    items = []
    for a in appts:
        li = by_appt.get(a.id, [])
        if (provider or account_id or calendar_id) and not li:
            continue
        items.append({
            "id": str(a.id),
            "title": a.title,
            "notes": a.notes,
            "location": a.location,
            "phone": a.phone,
            "timezone": a.timezone,
            "start_at": _iso(a.start_at),
            "end_at": _iso(a.end_at),
            "duration_minutes": a.duration_minutes,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "links": li,
        })

    return {"total": total, "count": len(items), "offset": offset, "items": items}

@router.get("/calendar/events/{appointment_id}")
async def get_event(appointment_id: str, user: Annotated[User, Depends(get_current_user)]):
    a = await Appointment.get_or_none(id=appointment_id, user=user)
    if not a:
        _err(404, "Appointment not found")
    links = await AppointmentExternalLink.filter(appointment=a).values(
        "provider", "account_id", "external_event_id", "external_calendar_id"
    )
    return {
        "id": str(a.id),
        "title": a.title,
        "notes": a.notes,
        "location": a.location,
        "phone": a.phone,
        "timezone": a.timezone,
        "start_at": _iso(a.start_at),
        "end_at": _iso(a.end_at),
        "duration_minutes": a.duration_minutes,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "links": links,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Sync (Google + Cal.com + Calendly)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/sync")
async def sync_calendar(body: SyncBody, user: Annotated[User, Depends(get_current_user)]):
    start = body.start_at or (_now_utc() - timedelta(days=30))
    end   = body.end_at   or (_now_utc() + timedelta(days=60))

    q = CalendarAccount.filter(user=user)
    if body.account_ids:
        q = q.filter(id__in=body.account_ids)
    accounts = await q.all()
    if not accounts:
        return {"synced": 0, "created": 0, "updated": 0}

    total_synced = 0
    created = 0
    updated = 0

    for acc in accounts:
        provider = acc.provider
        try:
            if provider == "google":
                await _ensure_access_token(acc)
                calendar_id = acc.primary_calendar_id or "primary"
                params = {"timeMin": _iso(start), "timeMax": _iso(end), "singleEvents": "true", "orderBy": "startTime", "showDeleted": "false", "maxResults": 2500}
                async with httpx.AsyncClient(timeout=45.0) as client:
                    url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events"
                    r = await client.get(url, headers=_headers_google(acc.access_token), params=params)
                if r.status_code != 200:
                    continue
                events = (r.json() or {}).get("items", [])
                for ev in events:
                    total_synced += 1
                    try:
                        mapped = _map_google_event_to_appt(ev)
                        created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
                    except Exception:
                        continue

            elif provider == "calcom":
                params = {"startTime": _iso(start), "endTime": _iso(end)}
                async with httpx.AsyncClient(timeout=45.0) as client:
                    r = await client.get(f"{CALCOM_API_BASE}/bookings", headers=_headers_calcom(acc.access_token), params=params)
                if r.status_code != 200:
                    continue
                items = r.json() or {}
                bookings = items.get("data") if isinstance(items, dict) else items
                bookings = bookings or []
                for b in bookings:
                    total_synced += 1
                    try:
                        mapped = _map_calcom_booking_to_appt(b)
                        created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
                    except Exception:
                        continue

            elif provider == "calendly":
                params = {"min_start_time": _iso(start), "max_start_time": _iso(end)}
                async with httpx.AsyncClient(timeout=45.0) as client:
                    r = await client.get(f"{CALENDLY_API_BASE}/scheduled_events", headers=_headers_calendly(acc.access_token), params=params)
                if r.status_code != 200:
                    continue
                items = r.json() or {}
                events = items.get("collection") or items.get("data") or []
                for ev in events:
                    total_synced += 1
                    try:
                        inv = {}
                        if ev.get("uuid"):
                            async with httpx.AsyncClient(timeout=20.0) as client:
                                r2 = await client.get(f"{CALENDLY_API_BASE}/scheduled_events/{ev.get('uuid')}/invitees", headers=_headers_calendly(acc.access_token))
                            if r2.status_code == 200:
                                invs = r2.json() or {}
                                coll = invs.get("collection") or []
                                inv = coll[0] if coll else {}
                        payload = {"event": ev, "invitee": inv, "status": ev.get("status")}
                        mapped = _map_calendly_event_to_appt(payload)
                        created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
                    except Exception:
                        continue
        except Exception:
            continue

    return {"synced": total_synced, "created": created, "updated": updated}

async def _upsert_from_mapped(user: User, acc: CalendarAccount, mapped: Dict[str, Any], created: int, updated: int):
    ext_id = mapped["external_event_id"]
    link = await AppointmentExternalLink.get_or_none(provider=acc.provider, external_event_id=ext_id)
    if link:
        appt = await Appointment.get_or_none(id=link.appointment_id, user=user)
        if not appt:
            appt = await Appointment.create(user=user, **mapped["appt_fields"])
            link.appointment = appt
            link.external_calendar_id = mapped.get("external_calendar_id") or link.external_calendar_id
            await link.save()
            created += 1
        else:
            for k, v in mapped["appt_fields"].items():
                setattr(appt, k, v)
            await appt.save()
            updated += 1
    else:
        appt = await Appointment.create(user=user, **mapped["appt_fields"])
        await AppointmentExternalLink.create(
            appointment=appt, account=acc, provider=acc.provider,
            external_event_id=ext_id, external_calendar_id=mapped.get("external_calendar_id")
        )
        created += 1
    return created, updated

# ──────────────────────────────────────────────────────────────────────────────
# Focused Google import (saves to DB)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/google/import")
async def google_import(body: GoogleImportBody, user: Annotated[User, Depends(get_current_user)]):
    acc = await _pick_account(user, body.account_id, provider="google")
    await _ensure_access_token(acc)

    start = body.start_at or (_now_utc() - timedelta(days=30))
    end = body.end_at or (_now_utc() + timedelta(days=60))
    calendars = body.calendar_ids or [acc.primary_calendar_id or "primary"]

    created = 0
    updated = 0
    synced = 0

    async with httpx.AsyncClient(timeout=45.0) as client:
        for cid in calendars:
            params = {"timeMin": _iso(start), "timeMax": _iso(end), "singleEvents": "true", "orderBy": "startTime", "showDeleted": "false", "maxResults": 2500}
            url = f"{GOOGLE_API_BASE}/calendars/{cid}/events"
            r = await client.get(url, headers=_headers_google(acc.access_token), params=params)
            if r.status_code != 200:
                continue
            events = (r.json() or {}).get("items", [])
            for ev in events:
                synced += 1
                try:
                    mapped = _map_google_event_to_appt(ev)
                    c, u = await _upsert_from_mapped(user, acc, mapped, 0, 0)
                    created += c
                    updated += u
                except Exception:
                    continue

    return {"ok": True, "synced": synced, "created": created, "updated": updated}

# ──────────────────────────────────────────────────────────────────────────────
# Free/Busy (Google only)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/freebusy")
async def freebusy(body: FreeBusyBody, user: Annotated[User, Depends(get_current_user)]):
    acc = await _pick_account(user, body.account_id, provider="google")
    await _ensure_access_token(acc)
    calendars = body.calendar_ids or [acc.primary_calendar_id or "primary"]
    req = {"timeMin": _iso(body.start_at), "timeMax": _iso(body.end_at), "items": [{"id": cid} for cid in calendars]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{GOOGLE_API_BASE}/freeBusy"
        r = await client.post(url, headers=_headers_google(acc.access_token), content=json.dumps(req))
    if r.status_code != 200:
        _err(400, f"freeBusy failed: {r.text}")
    fb = r.json() or {}
    return {"ok": True, "freebusy": fb.get("calendars", {}), "start_at": _iso(body.start_at), "end_at": _iso(body.end_at)}

# ──────────────────────────────────────────────────────────────────────────────
# Webhook registration helpers (Calendly / Cal.com)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/calendly/webhook/register")
async def calendly_register_webhook(body: CalendlyWebhookRegisterBody, user: Annotated[User, Depends(get_current_user)]):
    acc = await _pick_account(user, body.account_id, provider="calendly")

    # fetch org if missing
    if not acc.external_org_id:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r_me = await client.get(f"{CALENDLY_API_BASE}/users/me", headers=_headers_calendly(acc.access_token))
        if r_me.status_code == 200:
            me = r_me.json() or {}
            res_user = me.get("resource") or me.get("data") or {}
            acc.external_org_id = res_user.get("current_organization") or res_user.get("organization") or acc.external_org_id
            await acc.save()
        if not acc.external_org_id and body.scope == "organization":
            _err(400, "Calendly organization not found; try scope='user'.")

    payload = {
        "url": f"{PUBLIC_BASE}/api/calendar/webhook/calendly",
        "events": body.events,
        "scope": body.scope,  # "organization" or "user"
    }
    if body.scope == "organization" and acc.external_org_id:
        payload["organization"] = acc.external_org_id
    else:
        payload["user"] = acc.external_account_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{CALENDLY_API_BASE}/webhook_subscriptions", headers=_headers_calendly(acc.access_token), content=json.dumps(payload))
    if r.status_code not in (200, 201):
        _err(400, f"Calendly webhook create failed: {r.text}")

    res = r.json() or {}
    res_rc = res.get("resource") or res.get("data") or res
    webhook_id = res_rc.get("uri") or res_rc.get("id") or None
    signing_key = res_rc.get("signing_key") or res_rc.get("signingKey") or None  # Calendly returns signing_key on create

    if webhook_id:
        acc.webhook_id = webhook_id
    if signing_key:
        acc.webhook_signing_key = signing_key
    await acc.save()

    return {"ok": True, "account_id": str(acc.id), "webhook_id": webhook_id, "signing_key_saved": bool(signing_key)}

@router.post("/calendar/calcom/webhook/register")
async def calcom_register_webhook(body: CalcomWebhookRegisterBody, user: Annotated[User, Depends(get_current_user)]):
    acc = await _pick_account(user, body.account_id, provider="calcom")
    secret = body.secret or secrets.token_hex(32)
    acc.webhook_signing_key = secret
    await acc.save()

    # If your Cal.com plan/API allows programmatic webhook creation, you can uncomment this and adapt:
    # payload = {
    #     "url": f"{PUBLIC_BASE}/api/calendar/webhook/calcom",
    #     "secret": secret,
    #     "events": ["BOOKING_CREATED", "BOOKING_RESCHEDULED", "BOOKING_CANCELLED"],
    # }
    # async with httpx.AsyncClient(timeout=30.0) as client:
    #     r = await client.post(f"{CALCOM_API_BASE}/webhooks", headers=_headers_calcom(acc.access_token), content=json.dumps(payload))
    # if r.status_code not in (200, 201):
    #     _err(400, f"Cal.com webhook create failed: {r.text}")
    # data = r.json() or {}
    # acc.webhook_id = data.get("id") or data.get("uid") or acc.webhook_id
    # await acc.save()

    return {
        "ok": True,
        "account_id": str(acc.id),
        "webhook_url": f"{PUBLIC_BASE}/api/calendar/webhook/calcom",
        "secret": secret,
        "note": "Set this secret while creating webhook in Cal.com dashboard; request header x-cal-signature-256 will be verified."
    }

# ──────────────────────────────────────────────────────────────────────────────
# Webhooks (Cal.com + Calendly) — multi-tenant, per-account key verification
# ──────────────────────────────────────────────────────────────────────────────

def _verify_calcom_signature_raw(raw_body: bytes, signature_hex: str, secret: str) -> bool:
    try:
        mac = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, (signature_hex or "").lower())
    except Exception:
        return False

async def _find_calcom_account_for_signature(raw_body: bytes, signature_hex: str) -> Optional[CalendarAccount]:
    # Try per-account secrets first
    accounts = await CalendarAccount.filter(provider="calcom").all()
    for acc in accounts:
        if acc.webhook_signing_key and _verify_calcom_signature_raw(raw_body, signature_hex, acc.webhook_signing_key):
            return acc
    # Fallback to global secret if configured (not ideal for multi-tenant)
    if CALCOM_WEBHOOK_SECRET and _verify_calcom_signature_raw(raw_body, signature_hex, CALCOM_WEBHOOK_SECRET):
        return await CalendarAccount.filter(provider="calcom").first()
    return None

def _verify_calendly_signature_raw(raw_body: bytes, signature_header: str, signing_key: str) -> bool:
    try:
        parts = dict(x.split("=", 1) for x in (signature_header or "").split(",") if "=" in x)
        t = parts.get("t")
        v1 = parts.get("v1")
        base = f"{t}.{raw_body.decode()}".encode()
        mac = hmac.new(signing_key.encode(), base, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, v1 or "")
    except Exception:
        return False

async def _find_calendly_account_for_signature(raw_body: bytes, signature_header: str) -> Optional[CalendarAccount]:
    # Try each account's signing_key
    accounts = await CalendarAccount.filter(provider="calendly").all()
    for acc in accounts:
        if acc.webhook_signing_key and _verify_calendly_signature_raw(raw_body, signature_header, acc.webhook_signing_key):
            return acc
    # Fallback global
    if CALENDLY_WEBHOOK_SIGNING_KEY and _verify_calendly_signature_raw(raw_body, signature_header, CALENDLY_WEBHOOK_SIGNING_KEY):
        return await CalendarAccount.filter(provider="calendly").first()
    return None

async def _resolve_calendly_account_from_payload(payload: Dict[str, Any]) -> Optional[CalendarAccount]:
    # Prefer org URI
    org = None
    p = payload.get("payload") or payload.get("data") or {}
    if isinstance(p, dict):
        org = p.get("organization")
        if not org:
            ev = p.get("event")
            if isinstance(ev, dict) and "organization" in ev:
                org = ev.get("organization")
            if isinstance(ev, str) and ev.startswith("https://"):
                # event URI: /scheduled_events/{uuid}
                pass
    if org:
        acc = await CalendarAccount.get_or_none(provider="calendly", external_org_id=org)
        if acc:
            return acc
    # Fallback by account id if present in payload
    user_uri = None
    if isinstance(p, dict):
        user_uri = p.get("user") or p.get("owner") or None
    if user_uri:
        acc = await CalendarAccount.get_or_none(provider="calendly", external_account_id=user_uri)
        if acc:
            return acc
    return await CalendarAccount.filter(provider="calendly").first()

async def _calendly_fetch_if_uri(obj: Any, token: str) -> Any:
    """Calendly webhooks often send 'event'/'invitee' as URI strings; fetch them to get full details."""
    if isinstance(obj, str) and obj.startswith("http"):
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(obj, headers=_headers_calendly(token))
        if r.status_code == 200:
            return r.json()
    return obj

@router.post("/calendar/webhook/calcom")
async def calcom_webhook(request: Request, x_cal_signature_256: Optional[str] = Header(None)):
    raw = await request.body()
    acc = await _find_calcom_account_for_signature(raw, x_cal_signature_256 or "")
    if not acc:
        _err(401, "Invalid Cal.com signature")

    payload = json.loads(raw.decode() or "{}")
    event = (payload.get("type") or payload.get("event") or "").lower()
    data = payload.get("data") or payload.get("payload") or payload

    try:
        b = data.get("booking") if isinstance(data, dict) and "booking" in data else data
        mapped = _map_calcom_booking_to_appt(b)
        if "cancel" in event:
            mapped["appt_fields"]["status"] = AppointmentStatus.CANCELLED
        user = await User.get(id=acc.user_id)
        created, updated = 0, 0
        created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
    except Exception:
        pass

    return {"ok": True}

@router.post("/calendar/webhook/calendly")
async def calendly_webhook(
    request: Request,
    calendly_webhook_signature: Optional[str] = Header(None, alias="Calendly-Webhook-Signature")
):
    raw = await request.body()
    # First: find which account's key matches the signature
    acc = await _find_calendly_account_for_signature(raw, calendly_webhook_signature or "")
    if not acc:
        _err(401, "Invalid Calendly signature")

    payload = json.loads(raw.decode() or "{}")
    topic = (payload.get("event") or payload.get("event_type") or "").lower()
    data = payload.get("payload") or payload.get("data") or {}

    # If signature did not identify account uniquely, resolve by org/user in payload
    if not acc or not acc.id:
        acc2 = await _resolve_calendly_account_from_payload(payload)
        if acc2:
            acc = acc2

    # Normalize: fetch event/invitee if URIs
    try:
        ev = data.get("event")
        inv = data.get("invitee")
        ev = await _calendly_fetch_if_uri(ev, acc.access_token)
        inv = await _calendly_fetch_if_uri(inv, acc.access_token)
        data_norm = {"event": ev, "invitee": inv, "status": "cancelled" if "cancel" in topic else "confirmed"}
        mapped = _map_calendly_event_to_appt(data_norm)
        user = await User.get(id=acc.user_id)
        created, updated = 0, 0
        created, updated = await _upsert_from_mapped(user, acc, mapped, created, updated)
    except Exception:
        # best-effort: ignore malformed payloads
        pass

    return {"ok": True}
