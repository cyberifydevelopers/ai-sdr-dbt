



# controllers/form_controller.py
from __future__ import annotations

from datetime import datetime, time, date
from zoneinfo import ZoneInfo
from typing import Annotated, Dict, Optional, Any

from fastapi import APIRouter, Request, HTTPException, Depends, Query, BackgroundTasks, UploadFile
from pydantic import BaseModel, EmailStr
from starlette.datastructures import FormData

from models.form_submission import FormSubmission, SubmissionStatus
from models.auth import User
from helpers.token_helper import get_current_user
from helpers.ai_structurer import process_submission_to_appointment  # adjust path as needed
import textwrap
# --------- CONFIG ---------
DEFAULT_TZ = ZoneInfo("UTC")

# --------- HELPERS ---------
async def read_any_payload(request: Request) -> dict:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        return await request.json()
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        form: FormData = await request.form()
        data: Dict[str, Any] = {}
        for k, v in form.multi_items():
            if isinstance(v, UploadFile):
                continue
            if k in data:
                if isinstance(data[k], list):
                    data[k].append(v)
                else:
                    data[k] = [data[k], v]
            else:
                data[k] = v
        return {"form": data}
    try:
        raw = await request.body()
        return {"raw_text": raw.decode("utf-8", errors="ignore")}
    except Exception:
        return {}

def parse_any_datetime(value: object, default_tz: ZoneInfo = DEFAULT_TZ) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=default_tz)
    if isinstance(value, date):
        return datetime.combine(value, time(9, 0), tzinfo=default_tz)
    if isinstance(value, str):
        v = value.strip()
        try:
            if v.endswith("Z"):
                v = v[:-1] + "+00:00"
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)
        except Exception:
            pass
        try:
            d = date.fromisoformat(v)
            return datetime.combine(d, time(9, 0), tzinfo=default_tz)
        except Exception:
            return None
    return None

def deep_get(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = k.lower()
            if lk in keys and not isinstance(v, (dict, list)):
                return v
            got = deep_get(v, keys)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for item in obj:
            got = deep_get(item, keys)
            if got is not None:
                return got
    return None

EMAIL_KEYS = {"email", "email_address", "e-mail"}
PHONE_KEYS = {"phone", "phone_number", "mobile", "contact_number"}
DATE_KEYS  = {"start_at", "start", "start_time", "appointment", "booking_time", "date", "datetime", "date_time"}
NAME_KEYS  = {"first_name", "firstname", "given_name", "name"}

def best_effort_extract(payload: dict) -> dict:
    extracted: Dict[str, Any] = {}
    email = deep_get(payload, EMAIL_KEYS)
    phone = deep_get(payload, PHONE_KEYS)
    when  = deep_get(payload, DATE_KEYS)
    name  = deep_get(payload, NAME_KEYS)

    if email: extracted["email"] = email
    if phone: extracted["phone"] = phone
    if when:  extracted["booking_time"] = when

    if isinstance(name, str):
        parts = name.strip().split()
        if parts:
            extracted["first_name"] = parts[0]
            if len(parts) > 1:
                extracted["last_name"] = " ".join(parts[1:])
    return extracted

def combine_date_time_fields(payload: dict) -> Optional[str]:
    d = deep_get(payload, {"date"})
    t = deep_get(payload, {"time", "start_time"})
    if isinstance(d, str) and isinstance(t, str):
        return f"{d.strip()} {t.strip()}"
    return None

# --------- SCHEMAS ---------
class Step1Payload(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str

class Step2Payload(BaseModel):
    booking_time: datetime

class Step3Payload(BaseModel):
    additional_details: Optional[Dict[str, Any]] = None

# --------- ROUTER ---------
router = APIRouter()

# --------- WEBHOOK ----------
@router.post("/form/webhook")
async def form_webhook(
    request: Request,
    token: str = Query(..., description="Per-user webhook token"),
    bg: BackgroundTasks = None
):
    user = await User.get_or_none(webhook_token=token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await read_any_payload(request)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Unsupported payload")

    extracted: Dict[str, Any] = best_effort_extract(payload)

    form_response = payload.get("form_response", {}) if isinstance(payload, dict) else {}
    answers = form_response.get("answers", []) or []
    for ans in answers:
        t = ans.get("type")
        if t == "text":
            if "first_name" not in extracted:
                extracted["first_name"] = ans.get("text")
            elif "last_name" not in extracted:
                extracted["last_name"] = ans.get("text")
        elif t == "email":
            extracted.setdefault("email", ans.get("email"))
        elif t == "phone_number":
            extracted.setdefault("phone", ans.get("phone_number"))
        elif t in ("date", "datetime", "date_time"):
            extracted.setdefault(
                "booking_time",
                ans.get("datetime") or ans.get("date_time") or ans.get("date")
            )
        elif t == "choice":
            choice = ans.get("choice", {})
            details = extracted.get("additional_details") or {}
            details["choice"] = choice.get("label")
            extracted["additional_details"] = details

    combo = combine_date_time_fields(payload)
    if combo and not extracted.get("booking_time"):
        extracted["booking_time"] = combo

    booking_dt = parse_any_datetime(extracted.get("booking_time"))

    submission = None
    if extracted.get("email"):
        submission = await FormSubmission.get_or_none(email=extracted["email"], user_id=user.id)
    if (not submission) and extracted.get("phone"):
        submission = await FormSubmission.get_or_none(phone=extracted["phone"], user_id=user.id)

    minimal_ok = extracted.get("first_name") and (extracted.get("phone") or extracted.get("email"))

    if not submission:
        if minimal_ok:
            submission = await FormSubmission.create(
                user_id=user.id,
                first_name=extracted.get("first_name"),
                last_name=extracted.get("last_name"),
                email=extracted.get("email"),
                phone=extracted.get("phone"),
                booking_time=booking_dt,
                additional_details=extracted.get("additional_details"),
                raw_data=payload,
                status=SubmissionStatus.BOOKED if booking_dt else SubmissionStatus.UNBOOKED,
            )
        else:
            return {
                "success": False,
                "message": "Minimal info not found (need first_name + phone/email). Skipping save."
            }
    else:
        if booking_dt:
            submission.booking_time = booking_dt
            submission.status = SubmissionStatus.BOOKED
        for key in ("first_name", "last_name", "email", "phone", "additional_details"):
            val = extracted.get(key)
            if val:
                setattr(submission, key, val)
        submission.raw_data = payload
        await submission.save()

    if bg is not None:
        bg.add_task(process_submission_to_appointment, submission.id)

    return {
        "success": True,
        "user_id": user.id,
        "form_id": submission.id,
        "status": submission.status,
        "extracted": {
            **{k: v for k, v in extracted.items() if k != "booking_time"},
            "booking_time": booking_dt.isoformat() if booking_dt else None,
        },
        "ai_enqueued": True,
    }

# --------- STEP APIs ----------
@router.post("/form/step1")
async def form_step1(data: Step1Payload, user: Annotated[User, Depends(get_current_user)]):
    submission = await FormSubmission.create(
        user_id=user.id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        status=SubmissionStatus.UNBOOKED,
    )
    return {"success": True, "form_id": submission.id, "status": submission.status}

@router.put("/form/{form_id}/step2")
async def form_step2(form_id: int, data: Step2Payload, user: Annotated[User, Depends(get_current_user)]):
    submission = await FormSubmission.get_or_none(id=form_id, user_id=user.id)
    if not submission:
        raise HTTPException(status_code=404, detail="Form submission not found")
    submission.booking_time = data.booking_time if data.booking_time.tzinfo else data.booking_time.replace(tzinfo=DEFAULT_TZ)
    submission.status = SubmissionStatus.BOOKED
    await submission.save()
    return {"success": True, "form_id": submission.id, "status": submission.status}

@router.put("/form/{form_id}/step3")
async def form_step3(form_id: int, data: Step3Payload, user: Annotated[User, Depends(get_current_user)]):
    submission = await FormSubmission.get_or_none(id=form_id, user_id=user.id)
    if not submission:
        raise HTTPException(status_code=404, detail="Form submission not found")
    submission.additional_details = data.additional_details
    await submission.save()
    return {"success": True, "form_id": submission.id, "status": submission.status}

# --------- COPY/GENERATE UTILITIES ----------
@router.get("/form/copy-token")
async def copy_token(user: Annotated[User, Depends(get_current_user)]):
    return {"success": True, "token": user.webhook_token}

@router.get("/form/copy-webhook-url")
async def copy_webhook_url(user: Annotated[User, Depends(get_current_user)]):
    url = f"https://aisdr-dbt.ddns.net/api/form/webhook?token={user.webhook_token}"
    return {"success": True, "webhook_url": url}

@router.get("/form/copy-script")
async def copy_script(user: Annotated[User, Depends(get_current_user)]):
    script = textwrap.dedent(f"""
        <script>
        document.addEventListener("submit", async function(e) {{
            if (e.target.matches("form")) {{
                let formData = new FormData(e.target);
                let json = {{}};
                formData.forEach((v, k) => json[k] = v);
                try {{
                    await fetch("https://aisdr-dbt.ddns.net/api/form/webhook?token={user.webhook_token}", {{
                        method: "POST",
                        headers: {{"Content-Type": "application/json"}},
                        body: JSON.stringify(json)
                    }});
                }} catch(err) {{
                    console.error("Webhook push failed:", err);
                }}
            }}
        }}, true);
        </script>
    """).strip()
    return {"success": True, "script": script}


@router.get("/form/copy-wordpress-plugin")
async def copy_wordpress_plugin(user: Annotated[User, Depends(get_current_user)]):
    plugin = textwrap.dedent(f"""\
        <?php
        /*
        Plugin Name: Auto Form Forwarder
        Description: Automatically forwards all form submissions to your API webhook.
        Version: 1.0
        Author: Your Company
        */
        add_action('wp_head', function() {{
            ?>
            <script>
            document.addEventListener("submit", async function(e) {{
                if (e.target.matches("form")) {{
                    let formData = new FormData(e.target);
                    let json = {{}};
                    formData.forEach((v, k) => json[k] = v);
                    try {{
                        await fetch("https://aisdr-dbt.ddns.net/webhook?token={user.webhook_token}", {{
                            method: "POST",
                            headers: {{"Content-Type": "application/json"}},
                            body: JSON.stringify(json)
                        }});
                    }} catch(err) {{
                        console.error("Webhook push failed:", err);
                    }}
                }}
            }}, true);
            </script>
            <?php
        }});
        ?>
    """).strip()
    return {"success": True, "wordpress_plugin": plugin}








