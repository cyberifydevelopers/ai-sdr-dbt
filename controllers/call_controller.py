

# import asyncio
# from datetime import date, datetime, timedelta
# from typing import Annotated, List, Optional, Tuple

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
# from tortoise.expressions import Q
# from tortoise.functions import Avg, Count

# from helpers.token_helper import get_current_user
# from helpers.vapi_helper import get_headers, generate_token
# from helpers.billing_helper import (
#     per_minute_cost_cents,
#     compute_call_charge_cents,
#     apply_transaction,
# )
# from models.auth import User
# from models.call_log import CallLog
# from models.assistant import Assistant
# from models.call_blocklist import CallBlocklist  # auto-flag

# router = APIRouter()

# # ------------------ Utilities ------------------

# def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
#     if not s:
#         return None
#     try:
#         return datetime.fromisoformat(s.replace("Z", "+00:00"))
#     except Exception:
#         return None


# async def _auto_flag_spam(customer_number: Optional[str]) -> None:
#     """
#     Post-call heuristic:
#       - If caller makes >= 8 calls 'today' and the average duration < 8 seconds,
#         put them on a 24h temporary blocklist.
#     """
#     if not customer_number:
#         return

#     now = datetime.utcnow()
#     start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
#     end_day = start_day + timedelta(days=1)

#     stats = await CallLog.filter(
#         customer_number=customer_number,
#         call_started_at__gte=start_day,
#         call_started_at__lt=end_day,
#     ).annotate(
#         c=Count("id"),
#         avgdur=Avg("call_duration"),
#     ).values("c", "avgdur")

#     if not stats:
#         return

#     c = int(stats[0].get("c") or 0)
#     avgdur = float(stats[0].get("avgdur") or 0.0)

#     if c >= 8 and avgdur < 8.0:
#         until = now + timedelta(hours=24)
#         existing = await CallBlocklist.get_or_none(phone_number=customer_number)
#         await CallBlocklist.update_or_create(
#             defaults={
#                 "reason": f"Auto-spam: {c} calls today with avg {avgdur:.2f}s",
#                 "blocked_until": until,
#                 "hit_count": (existing.hit_count + 1) if existing else 1,
#             },
#             phone_number=customer_number,
#         )


# async def _bill_call_if_needed(
#     *,
#     call_id: str,
#     user_id: Optional[int],
#     duration_seconds: Optional[float],
#     currency_hint: Optional[str] = None,
# ) -> Tuple[bool, Optional[int], Optional[str]]:
#     """
#     Idempotently debit the user's wallet for a finished call.

#     Returns:
#       (debited, charge_cents, error_msg_if_any)
#     """
#     try:
#         if not user_id or not duration_seconds or duration_seconds <= 0:
#             return (False, None, None)

#         # Idempotency key reusing the existing column used for Stripe PI
#         idempotency_key = f"call_{call_id}"

#         from models.billing import AccountTransaction  # local import to avoid cycles
#         already = await AccountTransaction.filter(
#             stripe_payment_intent_id=idempotency_key
#         ).exists()
#         if already:
#             return (False, None, None)  # already charged

#         user = await User.get_or_none(id=user_id)
#         if not user:
#             return (False, None, "user_not_found")

#         rate = per_minute_cost_cents(user)  # e.g., 10¢/min default
#         charge_cents = compute_call_charge_cents(
#             duration_seconds=int(duration_seconds),
#             rate_per_min_cents=rate,
#             round_mode="ceil",
#         )
#         if charge_cents <= 0:
#             return (False, 0, None)

#         # Attempt debit
#         try:
#             await apply_transaction(
#                 user_id=user.id,
#                 amount_cents=-charge_cents,
#                 kind="debit_call",
#                 description=f"Call charge (call_id={call_id})",
#                 currency=(user.currency or "USD").upper(),
#                 stripe_pi=idempotency_key,  # store our call id here for idempotency
#                 metadata={"call_id": call_id, "computed_rate_cents": rate},
#             )
#             return (True, charge_cents, None)
#         except ValueError as ve:
#             # Likely "Insufficient balance" -> skip but report gracefully
#             return (False, charge_cents, str(ve))
#     except Exception as e:
#         return (False, None, f"internal_error: {e!s}")


# # ------------------ Endpoints ------------------

# # All call logs (admin-ish)
# @router.get("/all_call_logs")
# async def get_logs(user: Annotated[User, Depends(get_current_user)]):
#     # (Optional: gate by admin role if needed)
#     return await CallLog.all()

# # User-specific call logs (short info)
# @router.get("/user/call-logs")
# async def get_user_call_logs(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         call_logs = await CallLog.filter(user=user).all()
#         if not call_logs:
#             return []
#         return [
#             {
#                 "id": log.id,
#                 "call_id": log.call_id,
#                 "call_started_at": log.call_started_at.isoformat() if log.call_started_at else None,
#                 "call_ended_at": log.call_ended_at.isoformat() if log.call_ended_at else None,
#                 "cost": str(log.cost) if log.cost is not None else None,
#                 "customer_number": log.customer_number,
#                 "customer_name": log.customer_name,
#                 "call_ended_reason": log.call_ended_reason,
#                 "lead_id": log.lead_id,
#             }
#             for log in call_logs
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# # User-specific call logs (full list)
# @router.get("/user/call-logs-detail")
# async def get_user_call_logs_detail(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         call_logs = await CallLog.filter(user=user).order_by("-id").all()
#         return call_logs or []
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# # Call logs for a specific number
# @router.get("/specific-number-call-logs/{phoneNumber}")
# async def call_details(phoneNumber: str, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         details = await CallLog.filter(user=user, customer_number=phoneNumber).all()
#         return details or []
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# # Call cost list (kept as-is)
# @router.get("/user/call-cost")
# async def get_user_call_cost(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         call_logs = await CallLog.filter(user=user).all()
#         return call_logs or []
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")

# # Fetch a call directly from Vapi and return important fields (+ billing preview)
# @router.get("/call/{call_id}")
# async def get_call(call_id: str, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         call_detail_url = f"https://api.vapi.ai/call/{call_id}"
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             resp = await client.get(call_detail_url, headers=get_headers())
#         if resp.status_code != 200:
#             raise HTTPException(status_code=resp.status_code, detail="Failed to retrieve call details")

#         call_data = resp.json()
#         started_at = call_data.get("startedAt")
#         ended_at = call_data.get("endedAt")
#         start_dt = _iso_to_dt(started_at)
#         end_dt = _iso_to_dt(ended_at)
#         duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None

#         # Billing preview for the authenticated user
#         rate = per_minute_cost_cents(user)
#         est_cents = compute_call_charge_cents(
#             duration_seconds=int(duration or 0),
#             rate_per_min_cents=rate,
#             round_mode="ceil",
#         ) if duration else 0
#         rounded_minutes = int(((duration or 0) + 59) // 60) if duration else 0

#         important = {
#             "recording_url": call_data.get("artifact", {}).get("recordingUrl", "N/A"),
#             "transcript": call_data.get("artifact", {}).get("transcript", "No transcript available"),
#             "ended_reason": call_data.get("endedReason", "Unknown"),
#             "status": call_data.get("status", "Unknown"),
#             "call_ended_at": ended_at,
#             "call_started_at": started_at,
#             "cost": call_data.get("cost", 0),
#             "created_at": call_data.get("createdAt", "Unknown"),
#             "updated_at": call_data.get("updatedAt", "Unknown"),
#             "call_duration": duration,
#             "assistant": {
#                 "id": call_data.get("assistantId", "Unknown"),
#                 "name": call_data.get("assistant", {}).get("name", "Unknown assistant"),
#             },
#             "variableValues": {
#                 "name": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("name", "Unknown"),
#                 "email": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("email", "Unknown"),
#                 "mobile_no": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("mobile_no", "Unknown"),
#                 "add_date": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("add_date", "Unknown"),
#                 "custom_field_01": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_01", "Unknown"),
#                 "custom_field_02": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_02", "Unknown"),
#             },
#             "summary": call_data.get("analysis", {}).get("summary", "N/A"),

#             # Billing preview
#             "billing": {
#                 "rate_cents_per_min": rate,
#                 "estimated_cents": est_cents,
#                 "rounded_minutes": rounded_minutes,
#                 "policy": "per-started-minute (ceil)",
#             },
#         }
#         return important
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# # Delete call both in Vapi and locally
# @router.delete("/call_log/{id}")
# async def delete_calls(id: str):
#     try:
#         url = f"https://api.vapi.ai/call/{id}"
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             r = await client.delete(url, headers=get_headers())
#         if r.status_code not in (200, 204):
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Vapi call deletion failed with status {r.status_code}: {r.text}"
#             )
#         await CallLog.filter(call_id=id).delete()
#         return {"success": True, "detail": "Call log deleted successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting call logs: {str(e)}")

# # Backfill missing details by polling Vapi (also applies billing idempotently)
# @router.get("/update_calls")
# async def update_call_logs_for_missing_details():
#     try:
#         calls_to_update = await CallLog.filter(
#             Q(call_ended_reason__isnull=True) | Q(call_duration__isnull=True)
#         ).all()
#         if not calls_to_update:
#             return {"message": "No calls need to be updated."}

#         updated = 0
#         billed = 0
#         insufficient = 0

#         async with httpx.AsyncClient(timeout=30.0) as client:
#             for call in calls_to_update:
#                 url = f"https://api.vapi.ai/call/{call.call_id}"
#                 r = await client.get(url, headers=get_headers())
#                 if r.status_code != 200:
#                     continue
#                 data = r.json()

#                 started_at = data.get("startedAt")
#                 ended_at = data.get("endedAt")
#                 start_dt = _iso_to_dt(started_at)
#                 end_dt = _iso_to_dt(ended_at)
#                 duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else 0

#                 call.call_ended_reason = data.get("endedReason", "Unknown")
#                 call.cost = data.get("cost", 0)
#                 call.status = data.get("status", "Unknown")
#                 call.call_duration = duration or 0
#                 call.call_ended_at = end_dt
#                 await call.save()
#                 updated += 1

#                 # Try billing (idempotent)
#                 uid = None
#                 try:
#                     uid = call.user_id  # FK id available in Tortoise
#                 except Exception:
#                     try:
#                         await call.fetch_related("user")
#                         uid = call.user.id if call.user else None
#                     except Exception:
#                         uid = None

#                 debited, cents, err = await _bill_call_if_needed(
#                     call_id=call.call_id, user_id=uid, duration_seconds=duration
#                 )
#                 if debited:
#                     billed += 1
#                 elif err and "Insufficient balance" in err:
#                     insufficient += 1

#         return {
#             "message": f"Updated {updated} calls",
#             "billed_calls": billed,
#             "insufficient_balance_calls": insufficient,
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# # Sync inbound calls from Vapi (for assistants that missed webhook).
# # We schedule a background poll that will also do the billing.
# @router.post("/sync-inbound-calls")
# async def sync_inbound_calls(user: Annotated[User, Depends(get_current_user)], background_tasks: BackgroundTasks):
#     try:
#         user_assistants = await Assistant.filter(user=user).all()
#         assistant_ids = [a.vapi_assistant_id for a in user_assistants if a.vapi_assistant_id]

#         synced_count = 0
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             for assistant_id in assistant_ids:
#                 params = {"assistantId": assistant_id}
#                 r = await client.get("https://api.vapi.ai/call", headers=get_headers(), params=params)
#                 if r.status_code != 200:
#                     continue
#                 for call in r.json():
#                     call_id = call.get("id")
#                     if not call_id:
#                         continue
#                     exists = await CallLog.filter(call_id=call_id).exists()
#                     if exists:
#                         continue

#                     customer = call.get("customer", {}) or {}
#                     overrides = call.get("assistantOverrides", {}) or {}
#                     vars_ = overrides.get("variableValues", {}) or {}
#                     first_name = vars_.get("first_name", "")
#                     last_name = vars_.get("last_name", "")
#                     customer_name = f"{first_name} {last_name}".strip() or "Inbound Call"

#                     call_started_at = _iso_to_dt(call.get("createdAt")) or datetime.utcnow()
#                     call_ended_at = _iso_to_dt(call.get("endedAt"))

#                     await CallLog.create(
#                         user=user,
#                         call_id=call_id,
#                         call_started_at=call_started_at,
#                         call_ended_at=call_ended_at,
#                         customer_number=customer.get("number"),
#                         customer_name=customer_name,
#                         status=call.get("status", "Unknown"),
#                         call_ended_reason=call.get("endedReason"),
#                         cost=call.get("cost", 0),
#                         call_duration=call.get("duration", 0),
#                         is_transferred=False,
#                         criteria_satisfied=False,
#                         lead_id=None,
#                     )

#                     # Schedule background poll -> will also apply debit idempotently
#                     background_tasks.add_task(get_call_details, call_id=call_id, delay=300, user_id=user.id)
#                     synced_count += 1

#         return {"success": True, "detail": f"Successfully synced {synced_count} inbound calls"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")

# # Inbound/outbound counts
# @router.get("/user/call-counts")
# async def get_user_call_counts(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         call_logs = await CallLog.filter(user=user).all()
#         inbound = sum(1 for c in call_logs if c.customer_name == "Inbound Call")
#         outbound = len(call_logs) - inbound
#         today = date.today()
#         today_calls = sum(1 for c in call_logs if c.call_started_at and c.call_started_at.date() == today)
#         return {
#             "inbound_calls": inbound,
#             "outbound_calls": outbound,
#             "total_calls": inbound + outbound,
#             "today_calls": today_calls,
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# # Check call processing status (long calls)
# @router.get("/call-status/{call_id}")
# async def get_call_processing_status(call_id: str, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             r = await client.get(f"https://api.vapi.ai/call/{call_id}", headers=get_headers())
#         if r.status_code != 200:
#             raise HTTPException(status_code=r.status_code, detail="Failed to retrieve call details")

#         data = r.json()
#         started_at = data.get("startedAt")
#         ended_at = data.get("endedAt")
#         status_text = data.get("status", "Unknown")

#         start_dt = _iso_to_dt(started_at)
#         end_dt = _iso_to_dt(ended_at)
#         duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None

#         transcript = data.get("artifact", {}).get("transcript", "No transcript available")
#         transcript_status = "not_available"
#         if transcript and transcript != "No transcript available":
#             words = len(transcript.split())
#             sents = len(transcript.split("."))
#             if duration and duration > 1800:
#                 min_words = int(duration / 60 * 10)
#                 min_sents = int(duration / 60 * 2)
#             else:
#                 min_words = 50
#                 min_sents = 10
#             transcript_status = "complete" if words >= min_words and sents >= min_sents else "partial"

#         is_processing = status_text in {"in-progress", "queued", "connecting"}
#         progress = None
#         if duration and duration > 1800:
#             progress = 100 if transcript_status == "complete" else 50 if transcript_status == "partial" else 25

#         return {
#             "call_id": call_id,
#             "status": status_text,
#             "is_processing": is_processing,
#             "call_duration": duration,
#             "call_duration_minutes": (duration / 60) if duration else None,
#             "transcript_status": transcript_status,
#             "transcript_available": transcript != "No transcript available",
#             "recording_available": data.get("artifact", {}).get("recordingUrl", "N/A") != "N/A",
#             "processing_progress": progress,
#             "started_at": started_at,
#             "ended_at": ended_at,
#             "cost": data.get("cost", 0),
#             "ended_reason": data.get("endedReason", "Unknown"),
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error checking call status: {str(e)}")

# # ------------------ Background task used above ------------------
# async def get_call_details(call_id: str, delay: int, user_id: Optional[int], lead_id: Optional[int] = None):
#     """
#     After delay, re-fetch a call from Vapi (timestamps stabilize), update local CallLog,
#     run spam heuristic, and (idempotently) apply the billing debit.
#     """
#     try:
#         await asyncio.sleep(delay)
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             r = await client.get(f"https://api.vapi.ai/call/{call_id}", headers=get_headers())
#         if r.status_code != 200:
#             return

#         call_data = r.json()
#         started_at = call_data.get("startedAt")
#         ended_at = call_data.get("EndedAt") or call_data.get("endedAt")  # tolerate casing variants
#         start_dt = _iso_to_dt(started_at)
#         end_dt = _iso_to_dt(ended_at)
#         duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else 0

#         transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
#         transcript_quality = "not_available"
#         if transcript and transcript != "No transcript available":
#             words = len(transcript.split())
#             sents = len(transcript.split("."))
#             if duration > 1800:
#                 min_words = int(duration / 60 * 10)
#                 min_sents = int(duration / 60 * 2)
#             else:
#                 min_words = 50
#                 min_sents = 10
#             transcript_quality = "complete" if words >= min_words and sents >= min_sents else "partial"

#         call = await CallLog.get_or_none(call_id=call_id)

#         # Extract number from payload or fallback to saved call
#         customer_number = None
#         try:
#             customer_number = (call_data.get("customer") or {}).get("number")
#         except Exception:
#             customer_number = None
#         if not customer_number and call:
#             customer_number = call.customer_number

#         if call:
#             call.is_transferred = False
#             call.call_ended_reason = call_data.get("endedReason", "Unknown")
#             call.cost = call_data.get("cost", 0)
#             call.status = call_data.get("status", "Unknown")
#             call.call_duration = duration or 0
#             call.criteria_satisfied = False
#             call.call_ended_at = end_dt
#             await call.save()
#         else:
#             await CallLog.create(
#                 is_transferred=False,
#                 call_id=call_id,
#                 call_ended_reason=call_data.get("endedReason", "Unknown"),
#                 cost=call_data.get("cost", 0),
#                 status=call_data.get("status", "Unknown"),
#                 call_ended_at=end_dt,
#                 call_duration=duration,
#                 criteria_satisfied=False,
#                 customer_number=customer_number,
#             )

#         # --- Post-call auto-flag heuristic (spam) ---
#         await _auto_flag_spam(customer_number)

#         # --- Apply billing (idempotent) ---
#         uid = user_id
#         if not uid and call:
#             try:
#                 uid = call.user_id  # FK id if present
#             except Exception:
#                 try:
#                     await call.fetch_related("user")
#                     uid = call.user.id if call.user else None
#                 except Exception:
#                     uid = None

#         debited, cents, err = await _bill_call_if_needed(
#             call_id=call_id, user_id=uid, duration_seconds=duration
#         )
#         if err and "Insufficient balance" in err:
#             # Optionally: log or emit an internal event/notification here
#             print(f"[billing] Insufficient balance for call {call_id} (charge_cents={cents})")

#         # Optional: trigger downstream appointment extraction (internal service)
#         try:
#             async with httpx.AsyncClient(timeout=15.0) as client:
#                 await client.post(
#                     # IMPORTANT: live base must be reachable if called externally.
#                     f"https://app.thedbt.ai/api/appointments/from-call/{call_id}",
#                     headers={"Authorization": f"Bearer {generate_token()}"},
#                 )
#         except Exception as _e:
#             print("appointment extract failed:", _e)
#     except Exception as e:
#         print(f"Error in get_call_details: {e}")





import asyncio
from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from tortoise.expressions import Q
from tortoise.functions import Avg, Count

from helpers.token_helper import get_current_user
from helpers.vapi_helper import get_headers, generate_token
from helpers.billing_helper import (
    per_minute_cost_cents,
    compute_call_charge_cents,
    apply_transaction,
)
from models.auth import User
from models.call_log import CallLog
from models.assistant import Assistant
from models.call_blocklist import CallBlocklist  # auto-flag
from models.call_detail import CallDetail  # <-- added

router = APIRouter()

# ------------------ Utilities ------------------

def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def _auto_flag_spam(customer_number: Optional[str]) -> None:
    """
    Post-call heuristic:
      - If caller makes >= 8 calls 'today' and the average duration < 8 seconds,
        put them on a 24h temporary blocklist.
    """
    if not customer_number:
        return

    now = datetime.utcnow()
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = start_day + timedelta(days=1)

    stats = await CallLog.filter(
        customer_number=customer_number,
        call_started_at__gte=start_day,
        call_started_at__lt=end_day,
    ).annotate(
        c=Count("id"),
        avgdur=Avg("call_duration"),
    ).values("c", "avgdur")

    if not stats:
        return

    c = int(stats[0].get("c") or 0)
    avgdur = float(stats[0].get("avgdur") or 0.0)

    if c >= 8 and avgdur < 8.0:
        until = now + timedelta(hours=24)
        existing = await CallBlocklist.get_or_none(phone_number=customer_number)
        await CallBlocklist.update_or_create(
            defaults={
                "reason": f"Auto-spam: {c} calls today with avg {avgdur:.2f}s",
                "blocked_until": until,
                "hit_count": (existing.hit_count + 1) if existing else 1,
            },
            phone_number=customer_number,
        )


async def _bill_call_if_needed(
    *,
    call_id: str,
    user_id: Optional[int],
    duration_seconds: Optional[float],
    currency_hint: Optional[str] = None,
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Idempotently debit the user's wallet for a finished call.

    Returns:
      (debited, charge_cents, error_msg_if_any)
    """
    try:
        if not user_id or not duration_seconds or duration_seconds <= 0:
            return (False, None, None)

        # Idempotency key reusing the existing column used for Stripe PI
        idempotency_key = f"call_{call_id}"

        from models.billing import AccountTransaction  # local import to avoid cycles
        already = await AccountTransaction.filter(
            stripe_payment_intent_id=idempotency_key
        ).exists()
        if already:
            return (False, None, None)  # already charged

        user = await User.get_or_none(id=user_id)
        if not user:
            return (False, None, "user_not_found")

        rate = per_minute_cost_cents(user)  # e.g., 10¢/min default
        charge_cents = compute_call_charge_cents(
            duration_seconds=int(duration_seconds),
            rate_per_min_cents=rate,
            round_mode="ceil",
        )
        if charge_cents <= 0:
            return (False, 0, None)

        # Attempt debit
        try:
            await apply_transaction(
                user_id=user.id,
                amount_cents=-charge_cents,
                kind="debit_call",
                description=f"Call charge (call_id={call_id})",
                currency=(user.currency or "USD").upper(),
                stripe_pi=idempotency_key,  # store our call id here for idempotency
                metadata={"call_id": call_id, "computed_rate_cents": rate},
            )
            return (True, charge_cents, None)
        except ValueError as ve:
            # Likely "Insufficient balance" -> skip but report gracefully
            return (False, charge_cents, str(ve))
    except Exception as e:
        return (False, None, f"internal_error: {e!s}")


# ------------------ NEW: interest inference + tool push ------------------

def _infer_interest_from_transcript(txt: Optional[str]) -> str:
    """
    Return one of: 'interested' | 'not_interested' | 'unclear'
    Very lightweight heuristic; you can swap with LLM/Vapi function-calling later.
    """
    if not txt:
        return "unclear"
    t = txt.lower()

    positive = [
        "yes i'm interested", "yes i am interested", "i'm interested",
        "interested", "let's proceed", "go ahead", "sounds good",
        "send me details", "book the appointment", "sign me up", "let’s do it",
        "proceed", "move forward", "i want this", "i like this",
    ]
    negative = [
        "not interested", "no thanks", "no thank you", "stop calling",
        "do not call", "remove me", "not now", "maybe later", "no interest",
        "i'm fine", "i am fine", "don't want", "don’t want", "no, i'm not",
    ]

    for p in positive:
        if p in t:
            return "interested"
    for n in negative:
        if n in t:
            return "not_interested"
    return "unclear"


async def _push_interest_status_tool(
    *,
    call_id: str,
    interested: bool,
    user_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Call your Vapi API Request tool endpoint (as configured):
    - Tool name: Interest-status
    - GET https://app.thedbt.ai
    Since GET bodies are atypical, we'll send **query params**:
      ?tool=Interest-status&call_id=...&interest_status=true|false

    Uses the same internal token generator you already rely on.
    """
    try:
        params = {
            "tool": "Interest-status",
            "call_id": call_id,
            "interest_status": "true" if interested else "false",
        }
        headers = {
            "Authorization": f"Bearer {generate_token()}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("https://app.thedbt.ai", headers=headers, params=params)
        ok = 200 <= r.status_code < 300
        return (ok, None if ok else f"status={r.status_code}, body={r.text[:300]}")
    except Exception as e:
        return (False, str(e))


async def _upsert_call_detail_from_payload(
    *,
    user_id: Optional[int],
    call: Optional[CallLog],
    call_data: dict,
    transcript_text: Optional[str],
    duration_seconds: int,
    interest_status: str,
) -> CallDetail:
    """
    Upsert a CallDetail snapshot with success_evaluation_status = interest_status.
    """
    # Map basics
    started_at = _iso_to_dt(call_data.get("startedAt"))
    ended_at = _iso_to_dt(call_data.get("EndedAt") or call_data.get("endedAt"))
    assistant_id = call_data.get("assistantId")
    phone_number_id = (call_data.get("phoneNumber") or {}).get("id")
    customer = call_data.get("customer") or {}
    recording_url = (call_data.get("artifact") or {}).get("recordingUrl")
    analysis = call_data.get("analysis")
    summary = (call_data.get("analysis") or {}).get("summary")
    status_text = call_data.get("status", "Unknown")
    ended_reason = call_data.get("endedReason", "Unknown")

    # Build defaults
    defaults = {
        "assistant_id": assistant_id,
        "phone_number_id": phone_number_id,
        "customer_number": customer.get("number"),
        "customer_name": (call.customer_name if call else None) or customer.get("name"),
        "status": status_text,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration": int(duration_seconds or 0),
        "cost": call_data.get("cost", 0) or 0,
        "ended_reason": ended_reason,
        "is_transferred": False,
        "criteria_satisfied": False,
        "success_evaluation_status": interest_status,   # <-- save interest here
        "summary": summary,
        "transcript": transcript_text,
        "analysis": analysis,
        "recording_url": recording_url,
        "vapi_created_at": _iso_to_dt(call_data.get("createdAt")),
        "vapi_updated_at": _iso_to_dt(call_data.get("updatedAt")),
        "last_synced_at": datetime.utcnow(),
    }

    # Upsert by (user_id, call_id)
    cd, _created = await CallDetail.update_or_create(
        defaults={
            **defaults,
            "user_id": user_id or (call.user_id if call else None),
            "call_log_id": call.id if call else None,
        },
        user_id=user_id or (call.user_id if call else None),
        call_id=call_data.get("id"),
    )
    return cd


# ------------------ Endpoints ------------------

# All call logs (admin-ish)
@router.get("/all_call_logs")
async def get_logs(user: Annotated[User, Depends(get_current_user)]):
    # (Optional: gate by admin role if needed)
    return await CallLog.all()

# User-specific call logs (short info)
@router.get("/user/call-logs")
async def get_user_call_logs(user: Annotated[User, Depends(get_current_user)]):
    try:
        call_logs = await CallLog.filter(user=user).all()
        if not call_logs:
            return []
        return [
            {
                "id": log.id,
                "call_id": log.call_id,
                "call_started_at": log.call_started_at.isoformat() if log.call_started_at else None,
                "call_ended_at": log.call_ended_at.isoformat() if log.call_ended_at else None,
                "cost": str(log.cost) if log.cost is not None else None,
                "customer_number": log.customer_number,
                "customer_name": log.customer_name,
                "call_ended_reason": log.call_ended_reason,
                "lead_id": log.lead_id,
            }
            for log in call_logs
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# User-specific call logs (full list)
@router.get("/user/call-logs-detail")
async def get_user_call_logs_detail(user: Annotated[User, Depends(get_current_user)]):
    try:
        call_logs = await CallLog.filter(user=user).order_by("-id").all()
        return call_logs or []
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Call logs for a specific number
@router.get("/specific-number-call-logs/{phoneNumber}")
async def call_details(phoneNumber: str, user: Annotated[User, Depends(get_current_user)]):
    try:
        details = await CallLog.filter(user=user, customer_number=phoneNumber).all()
        return details or []
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Call cost list (kept as-is)
@router.get("/user/call-cost")
async def get_user_call_cost(user: Annotated[User, Depends(get_current_user)]):
    try:
        call_logs = await CallLog.filter(user=user).all()
        return call_logs or []
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")

# Fetch a call directly from Vapi and return important fields (+ billing preview + interest preview)
@router.get("/call/{call_id}")
async def get_call(call_id: str, user: Annotated[User, Depends(get_current_user)]):
    try:
        call_detail_url = f"https://api.vapi.ai/call/{call_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(call_detail_url, headers=get_headers())
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to retrieve call details")

        call_data = resp.json()
        started_at = call_data.get("startedAt")
        ended_at = call_data.get("endedAt")
        start_dt = _iso_to_dt(started_at)
        end_dt = _iso_to_dt(ended_at)
        duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None

        # Billing preview for the authenticated user
        rate = per_minute_cost_cents(user)
        est_cents = compute_call_charge_cents(
            duration_seconds=int(duration or 0),
            rate_per_min_cents=rate,
            round_mode="ceil",
        ) if duration else 0
        rounded_minutes = int(((duration or 0) + 59) // 60) if duration else 0

        transcript_text = call_data.get("artifact", {}).get("transcript", "No transcript available")
        transcript_text_for_eval = None if transcript_text == "No transcript available" else transcript_text
        interest_preview = _infer_interest_from_transcript(transcript_text_for_eval)

        important = {
            "recording_url": call_data.get("artifact", {}).get("recordingUrl", "N/A"),
            "transcript": transcript_text,
            "ended_reason": call_data.get("endedReason", "Unknown"),
            "status": call_data.get("status", "Unknown"),
            "call_ended_at": ended_at,
            "call_started_at": started_at,
            "cost": call_data.get("cost", 0),
            "created_at": call_data.get("createdAt", "Unknown"),
            "updated_at": call_data.get("updatedAt", "Unknown"),
            "call_duration": duration,
            "assistant": {
                "id": call_data.get("assistantId", "Unknown"),
                "name": call_data.get("assistant", {}).get("name", "Unknown assistant"),
            },
            "variableValues": {
                "name": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("name", "Unknown"),
                "email": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("email", "Unknown"),
                "mobile_no": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("mobile_no", "Unknown"),
                "add_date": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("add_date", "Unknown"),
                "custom_field_01": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_01", "Unknown"),
                "custom_field_02": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_02", "Unknown"),
            },
            "summary": call_data.get("analysis", {}).get("summary", "N/A"),

            # Billing preview
            "billing": {
                "rate_cents_per_min": rate,
                "estimated_cents": est_cents,
                "rounded_minutes": rounded_minutes,
                "policy": "per-started-minute (ceil)",
            },

            # Interest (preview only here; persisted in background sync flow)
            "interest_status_preview": interest_preview,
        }
        return important
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Delete call both in Vapi and locally
@router.delete("/call_log/{id}")
async def delete_calls(id: str):
    try:
        url = f"https://api.vapi.ai/call/{id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(url, headers=get_headers())
        if r.status_code not in (200, 204):
            raise HTTPException(
                status_code=400,
                detail=f"Vapi call deletion failed with status {r.status_code}: {r.text}"
            )
        await CallLog.filter(call_id=id).delete()
        return {"success": True, "detail": "Call log deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting call logs: {str(e)}")

# Backfill missing details by polling Vapi (also applies billing idempotently)
@router.get("/update_calls")
async def update_call_logs_for_missing_details():
    try:
        calls_to_update = await CallLog.filter(
            Q(call_ended_reason__isnull=True) | Q(call_duration__isnull=True)
        ).all()
        if not calls_to_update:
            return {"message": "No calls need to be updated."}

        updated = 0
        billed = 0
        insufficient = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for call in calls_to_update:
                url = f"https://api.vapi.ai/call/{call.call_id}"
                r = await client.get(url, headers=get_headers())
                if r.status_code != 200:
                    continue
                data = r.json()

                started_at = data.get("startedAt")
                ended_at = data.get("endedAt")
                start_dt = _iso_to_dt(started_at)
                end_dt = _iso_to_dt(ended_at)
                duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else 0

                call.call_ended_reason = data.get("endedReason", "Unknown")
                call.cost = data.get("cost", 0)
                call.status = data.get("status", "Unknown")
                call.call_duration = duration or 0
                call.call_ended_at = end_dt
                await call.save()
                updated += 1

                # Try billing (idempotent)
                uid = None
                try:
                    uid = call.user_id  # FK id available in Tortoise
                except Exception:
                    try:
                        await call.fetch_related("user")
                        uid = call.user.id if call.user else None
                    except Exception:
                        uid = None

                debited, cents, err = await _bill_call_if_needed(
                    call_id=call.call_id, user_id=uid, duration_seconds=duration
                )
                if debited:
                    billed += 1
                elif err and "Insufficient balance" in err:
                    insufficient += 1

        return {
            "message": f"Updated {updated} calls",
            "billed_calls": billed,
            "insufficient_balance_calls": insufficient,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Sync inbound calls from Vapi (for assistants that missed webhook).
# We schedule a background poll that will also do the billing.
@router.post("/sync-inbound-calls")
async def sync_inbound_calls(user: Annotated[User, Depends(get_current_user)], background_tasks: BackgroundTasks):
    try:
        user_assistants = await Assistant.filter(user=user).all()
        assistant_ids = [a.vapi_assistant_id for a in user_assistants if a.vapi_assistant_id]

        synced_count = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            for assistant_id in assistant_ids:
                params = {"assistantId": assistant_id}
                r = await client.get("https://api.vapi.ai/call", headers=get_headers(), params=params)
                if r.status_code != 200:
                    continue
                for call in r.json():
                    call_id = call.get("id")
                    if not call_id:
                        continue
                    exists = await CallLog.filter(call_id=call_id).exists()
                    if exists:
                        continue

                    customer = call.get("customer", {}) or {}
                    overrides = call.get("assistantOverrides", {}) or {}
                    vars_ = overrides.get("variableValues", {}) or {}
                    first_name = vars_.get("first_name", "")
                    last_name = vars_.get("last_name", "")
                    customer_name = f"{first_name} {last_name}".strip() or "Inbound Call"

                    call_started_at = _iso_to_dt(call.get("createdAt")) or datetime.utcnow()
                    call_ended_at = _iso_to_dt(call.get("endedAt"))

                    await CallLog.create(
                        user=user,
                        call_id=call_id,
                        call_started_at=call_started_at,
                        call_ended_at=call_ended_at,
                        customer_number=customer.get("number"),
                        customer_name=customer_name,
                        status=call.get("status", "Unknown"),
                        call_ended_reason=call.get("endedReason"),
                        cost=call.get("cost", 0),
                        call_duration=call.get("duration", 0),
                        is_transferred=False,
                        criteria_satisfied=False,
                        lead_id=None,
                    )

                    # Schedule background poll -> will also apply debit & interest push
                    background_tasks.add_task(get_call_details, call_id=call_id, delay=300, user_id=user.id)
                    synced_count += 1

        return {"success": True, "detail": f"Successfully synced {synced_count} inbound calls"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")

# Inbound/outbound counts
@router.get("/user/call-counts")
async def get_user_call_counts(user: Annotated[User, Depends(get_current_user)]):
    try:
        call_logs = await CallLog.filter(user=user).all()
        inbound = sum(1 for c in call_logs if c.customer_name == "Inbound Call")
        outbound = len(call_logs) - inbound
        today = date.today()
        today_calls = sum(1 for c in call_logs if c.call_started_at and c.call_started_at.date() == today)
        return {
            "inbound_calls": inbound,
            "outbound_calls": outbound,
            "total_calls": inbound + outbound,
            "today_calls": today_calls,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Check call processing status (long calls)
@router.get("/call-status/{call_id}")
async def get_call_processing_status(call_id: str, user: Annotated[User, Depends(get_current_user)]):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"https://api.vapi.ai/call/{call_id}", headers=get_headers())
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Failed to retrieve call details")

        data = r.json()
        started_at = data.get("startedAt")
        ended_at = data.get("endedAt")
        status_text = data.get("status", "Unknown")

        start_dt = _iso_to_dt(started_at)
        end_dt = _iso_to_dt(ended_at)
        duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None

        transcript = data.get("artifact", {}).get("transcript", "No transcript available")
        transcript_status = "not_available"
        if transcript and transcript != "No transcript available":
            words = len(transcript.split())
            sents = len(transcript.split("."))
            if duration and duration > 1800:
                min_words = int(duration / 60 * 10)
                min_sents = int(duration / 60 * 2)
            else:
                min_words = 50
                min_sents = 10
            transcript_status = "complete" if words >= min_words and sents >= min_sents else "partial"

        is_processing = status_text in {"in-progress", "queued", "connecting"}
        progress = None
        if duration and duration > 1800:
            progress = 100 if transcript_status == "complete" else 50 if transcript_status == "partial" else 25

        return {
            "call_id": call_id,
            "status": status_text,
            "is_processing": is_processing,
            "call_duration": duration,
            "call_duration_minutes": (duration / 60) if duration else None,
            "transcript_status": transcript_status,
            "transcript_available": transcript != "No transcript available",
            "recording_available": data.get("artifact", {}).get("recordingUrl", "N/A") != "N/A",
            "processing_progress": progress,
            "started_at": started_at,
            "ended_at": ended_at,
            "cost": data.get("cost", 0),
            "ended_reason": data.get("endedReason", "Unknown"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking call status: {str(e)}")

# ------------------ Background task used above ------------------
async def get_call_details(call_id: str, delay: int, user_id: Optional[int], lead_id: Optional[int] = None):
    """
    After delay, re-fetch a call from Vapi (timestamps stabilize), update local CallLog,
    run spam heuristic, (idempotently) apply the billing debit,
    **infer interest**, **push Interest-status tool**, and **upsert CallDetail**.
    """
    try:
        await asyncio.sleep(delay)
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"https://api.vapi.ai/call/{call_id}", headers=get_headers())
        if r.status_code != 200:
            return

        call_data = r.json()
        started_at = call_data.get("startedAt")
        ended_at = call_data.get("EndedAt") or call_data.get("endedAt")  # tolerate casing variants
        start_dt = _iso_to_dt(started_at)
        end_dt = _iso_to_dt(ended_at)
        duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else 0

        transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
        transcript_text = None if transcript == "No transcript available" else transcript

        transcript_quality = "not_available"
        if transcript_text:
            words = len(transcript_text.split())
            sents = len(transcript_text.split("."))
            if duration > 1800:
                min_words = int(duration / 60 * 10)
                min_sents = int(duration / 60 * 2)
            else:
                min_words = 50
                min_sents = 10
            transcript_quality = "complete" if words >= min_words and sents >= min_sents else "partial"

        call = await CallLog.get_or_none(call_id=call_id)

        # Extract number from payload or fallback to saved call
        customer_number = None
        try:
            customer_number = (call_data.get("customer") or {}).get("number")
        except Exception:
            customer_number = None
        if not customer_number and call:
            customer_number = call.customer_number

        if call:
            call.is_transferred = False
            call.call_ended_reason = call_data.get("endedReason", "Unknown")
            call.cost = call_data.get("cost", 0)
            call.status = call_data.get("status", "Unknown")
            call.call_duration = duration or 0
            call.criteria_satisfied = False
            call.call_ended_at = end_dt
            await call.save()
        else:
            call = await CallLog.create(
                is_transferred=False,
                call_id=call_id,
                call_ended_reason=call_data.get("endedReason", "Unknown"),
                cost=call_data.get("cost", 0),
                status=call_data.get("status", "Unknown"),
                call_ended_at=end_dt,
                call_duration=duration,
                criteria_satisfied=False,
                customer_number=customer_number,
            )

        # --- Post-call auto-flag heuristic (spam) ---
        await _auto_flag_spam(customer_number)

        # --- Apply billing (idempotent) ---
        uid = user_id
        if not uid and call:
            try:
                uid = call.user_id  # FK id if present
            except Exception:
                try:
                    await call.fetch_related("user")
                    uid = call.user.id if call.user else None
                except Exception:
                    uid = None

        debited, cents, err = await _bill_call_if_needed(
            call_id=call_id, user_id=uid, duration_seconds=duration
        )
        if err and "Insufficient balance" in err:
            # Optionally: log or emit an internal event/notification here
            print(f"[billing] Insufficient balance for call {call_id} (charge_cents={cents})")

        # --- NEW: infer interest + push to your Interest-status tool ---
        interest_status = _infer_interest_from_transcript(transcript_text)  # 'interested'|'not_interested'|'unclear'
        if interest_status != "unclear":
            pushed, perr = await _push_interest_status_tool(
                call_id=call_id,
                interested=(interest_status == "interested"),
                user_id=uid,
            )
            if not pushed and perr:
                print(f"[interest] push failed for {call_id}: {perr}")

        # --- NEW: Upsert CallDetail snapshot with success_evaluation_status ---
        try:
            await _upsert_call_detail_from_payload(
                user_id=uid,
                call=call,
                call_data=call_data,
                transcript_text=transcript_text,
                duration_seconds=int(duration or 0),
                interest_status=interest_status,
            )
        except Exception as e:
            print(f"[calldetail] upsert failed for {call_id}: {e}")

        # Optional: trigger downstream appointment extraction (internal service)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    # IMPORTANT: live base must be reachable if called externally.
                    f"https://app.thedbt.ai/api/appointments/from-call/{call_id}",
                    headers={"Authorization": f"Bearer {generate_token()}"},
                )
        except Exception as _e:
            print("appointment extract failed:", _e)
    except Exception as e:
        print(f"Error in get_call_details: {e}")
