from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Dict, Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tortoise.functions import Sum, Count, Avg

from helpers.token_helper import get_current_user

# ── Your models ───────────────────────────────────────────────────────────────
from models.auth import User
from models.file import File
from models.lead import Lead
from models.assistant import Assistant
from models.purchased_numbers import PurchasedNumber
from models.documents import Documents
from models.call_log import CallLog
from models.billing import AccountTransaction
from models.calendar_account import CalendarAccount
from models.campaign import Campaign, CampaignLeadProgress
from models.appointment import Appointment, AppointmentStatus
from models.form_submission import FormSubmission, SubmissionStatus
from models.call_detail import CallDetail
from models.message import MessageRecord

router = APIRouter()

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _to_int(x) -> int:
    if x is None:
        return 0
    if isinstance(x, Decimal):
        return int(x)
    if isinstance(x, (int, float)):
        return int(x)
    try:
        return int(x)
    except Exception:
        return 0

def _to_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(x)
    except Exception:
        return 0.0

def _safe_pct(numer: int, denom: int) -> float:
    return 0.0 if denom <= 0 else round((numer / denom) * 100.0, 2)

def _day_key(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")

def _zero_fill_timeseries(days: int, end: datetime, prefilled: Dict[str, Any], fill_value=0):
    out = {}
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        out[d] = prefilled.get(d, fill_value)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Basic endpoint (unchanged contract)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/statistics")
async def get_statistics_basic(user: Annotated[User, Depends(get_current_user)]):
    return {
        "leads": await Lead.filter(file__user_id=user.id).count(),
        "files": await File.filter(user_id=user.id).count(),
        "assistants": await Assistant.filter(user_id=user.id).count(),
        "phone_numbers": await PurchasedNumber.filter(user_id=user.id).count(),
        "knowledge_base": await Documents.filter(user_id=user.id).count(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Optional request model for docs
# ──────────────────────────────────────────────────────────────────────────────
class StatsWindow(BaseModel):
    days: int = 30


# ──────────────────────────────────────────────────────────────────────────────
# Advanced endpoint (no ORM date truncation — safe grouping in Python)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/advanced-statistics")
async def get_statistics_advanced(
    user: Annotated[User, Depends(get_current_user)],
    days: int = Query(30, ge=1, le=365, description="Rolling window for most time-series (days)"),
    days_long: int = Query(90, ge=7, le=730, description="Longer rolling window (e.g., wallet)"),
    recent_limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    now = _utcnow()
    since = now - timedelta(days=days)
    since_long = now - timedelta(days=days_long)

    # ── Core totals ───────────────────────────────────────────────────────────
    total_leads = await Lead.filter(file__user_id=user.id).count()
    total_files = await File.filter(user_id=user.id).count()
    total_assistants = await Assistant.filter(user_id=user.id).count()
    total_phone_numbers = await PurchasedNumber.filter(user_id=user.id).count()
    total_kb_docs = await Documents.filter(user_id=user.id).count()

    balance_cents = user.balance_cents or 0
    bonus_cents = user.bonus_cents or 0

    # ── Calls (CallLog) ──────────────────────────────────────────────────────
    call_q = CallLog.filter(user_id=user.id)
    total_calls = await call_q.count()

    status_rows = await call_q.annotate(c=Count("id")).group_by("status").values("status", "c")
    status_breakdown = { (row["status"] or "unknown"): row["c"] for row in status_rows }

    reason_rows = await call_q.annotate(c=Count("id")).group_by("call_ended_reason").values("call_ended_reason", "c")
    ended_reason_breakdown = { (row["call_ended_reason"] or "unknown"): row["c"] for row in reason_rows }

    sums = await call_q.annotate(
        total_duration=Sum("call_duration"),
        total_cost=Sum("cost"),
        avg_duration=Avg("call_duration"),
    ).values("total_duration", "total_cost", "avg_duration")
    total_duration_sec = _to_float(sums[0]["total_duration"]) if sums else 0.0
    total_cost = _to_float(sums[0]["total_cost"]) if sums else 0.0
    avg_call_duration_sec = round(_to_float(sums[0]["avg_duration"]), 2) if sums else 0.0

    transferred_calls = await call_q.filter(is_transferred=True).count()
    transfer_rate_pct = _safe_pct(transferred_calls, total_calls)

    recent_calls = await call_q.order_by("-call_started_at").limit(recent_limit).values(
        "id", "call_id", "customer_name", "customer_number", "status",
        "call_started_at", "call_ended_at", "call_duration", "cost",
        "call_ended_reason", "is_transferred"
    )

    # Python-side day bucketing for calls (count, duration, cost)
    calls_since_rows = await call_q.filter(call_started_at__gte=since).values(
        "call_started_at", "call_duration", "cost"
    )
    calls_per_day_prefill: Dict[str, int] = defaultdict(int)
    dur_per_day_prefill: Dict[str, float] = defaultdict(float)
    cost_per_day_prefill: Dict[str, float] = defaultdict(float)
    for r in calls_since_rows:
        key = _day_key(r.get("call_started_at"))
        if not key:
            continue
        calls_per_day_prefill[key] += 1
        dur_per_day_prefill[key] += _to_float(r.get("call_duration"))
        cost_per_day_prefill[key] += _to_float(r.get("cost"))

    calls_per_day = _zero_fill_timeseries(days, now, calls_per_day_prefill, 0)
    duration_per_day_sec = _zero_fill_timeseries(days, now, {k: round(v, 2) for k, v in dur_per_day_prefill.items()}, 0.0)
    cost_per_day = _zero_fill_timeseries(days, now, {k: round(v, 4) for k, v in cost_per_day_prefill.items()}, 0.0)

    # ── Call Details (VAPI-enriched) ─────────────────────────────────────────
    cd_q = CallDetail.filter(user_id=user.id)
    total_cd = await cd_q.count()
    success_status_rows = await cd_q.annotate(c=Count("id")).group_by("status").values(
        "status", "c"
    )
    success_evaluation_breakdown = {
        (row["status"] or "unknown"): row["c"] for row in success_status_rows
    }
    success_like = sum(
        v for k, v in success_evaluation_breakdown.items()
        if k and "success" in k.lower()
    )
    success_like_rate_pct = _safe_pct(success_like, total_cd)

    # ── Messaging ────────────────────────────────────────────────────────────
    mr_q = MessageRecord.filter(user_id=user.id)
    total_messages = await mr_q.count()
    total_messages_success = await mr_q.filter(success=True).count()
    total_messages_failed = total_messages - total_messages_success
    message_success_rate_pct = _safe_pct(total_messages_success, total_messages)

    # Python-side per-day counts for messages
    mr_since_rows = await mr_q.filter(created_at__gte=since).values("created_at")
    msgs_per_day_prefilled: Dict[str, int] = defaultdict(int)
    for r in mr_since_rows:
        key = _day_key(r.get("created_at"))
        if key:
            msgs_per_day_prefilled[key] += 1
    messages_per_day = _zero_fill_timeseries(days, now, msgs_per_day_prefilled, 0)

    # ── Appointments ─────────────────────────────────────────────────────────
    ap_q = Appointment.filter(user_id=user.id)
    ap_total = await ap_q.count()
    ap_buckets = await ap_q.annotate(c=Count("id")).group_by("status").values("status", "c")
    appointment_status_breakdown = { row["status"]: row["c"] for row in ap_buckets }

    upcoming = await ap_q.filter(
        start_at__gte=now,
        status=AppointmentStatus.SCHEDULED.value
    ).order_by("start_at").limit(recent_limit).values(
        "id", "title", "start_at", "end_at", "phone", "location", "status"
    )

    recently_completed = await ap_q.filter(
        end_at__lte=now,
        end_at__gte=now - timedelta(days=7),
        status=AppointmentStatus.COMPLETED.value
    ).order_by("-end_at").limit(recent_limit).values(
        "id", "title", "start_at", "end_at", "phone", "location", "status"
    )

    # ── Wallet / Billing ─────────────────────────────────────────────────────
    at_q = AccountTransaction.filter(user_id=user.id)

    lifetime_credit_cents = _to_int((await at_q.filter(amount_cents__gt=0)
                                     .annotate(s=Sum("amount_cents"))
                                     .values("s") or [{"s": 0}])[0]["s"])
    lifetime_debit_cents = abs(_to_int((await at_q.filter(amount_cents__lt=0)
                                        .annotate(s=Sum("amount_cents"))
                                        .values("s") or [{"s": 0}])[0]["s"]))
    lifetime_net_cents = lifetime_credit_cents - lifetime_debit_cents

    at_since_rows = await at_q.filter(created_at__gte=since_long).values("created_at", "amount_cents", "kind", "currency")
    spend_per_day: Dict[str, int] = defaultdict(int)
    credit_per_day: Dict[str, int] = defaultdict(int)
    kinds_breakdown: Dict[str, int] = defaultdict(int)
    for r in at_since_rows:
        d = _day_key(r.get("created_at"))
        amt = _to_int(r.get("amount_cents"))
        kinds_breakdown[r.get("kind") or "unknown"] += amt
        if amt >= 0:
            credit_per_day[d] += amt
        else:
            spend_per_day[d] += abs(amt)

    spend_per_day_filled = _zero_fill_timeseries(days_long, now, spend_per_day, 0)
    credit_per_day_filled = _zero_fill_timeseries(days_long, now, credit_per_day, 0)

    recent_tx = await at_q.order_by("-created_at").limit(recent_limit).values(
        "id", "amount_cents", "kind", "description", "currency",
        "stripe_payment_intent_id", "created_at"
    )

    # ── Campaigns ────────────────────────────────────────────────────────────
    camp_q = Campaign.filter(user_id=user.id)
    total_campaigns = await camp_q.count()
    campaigns_by_status = {
        row["status"]: row["c"]
        for row in await camp_q.annotate(c=Count("id")).group_by("status").values("status", "c")
    }

    clp_q = CampaignLeadProgress.filter(campaign__user_id=user.id)
    clp_status_breakdown = {
        (row["status"] or "unknown"): row["c"]
        for row in await clp_q.annotate(c=Count("id")).group_by("status").values("status", "c")
    }
    clp_attempts_sum = _to_int((await clp_q.annotate(s=Sum("attempt_count")).values("s") or [{"s": 0}])[0]["s"])

    # ── Files / Leads ────────────────────────────────────────────────────────
    file_lead_rows = await File.filter(user_id=user.id)\
        .annotate(lead_count=Count("leads"))\
        .order_by("-lead_count")\
        .limit(10)\
        .values("id", "name", "alphanumeric_id", "lead_count", "created_at")
    top_files_by_leads = file_lead_rows

    lead_rows = await Lead.filter(file__user_id=user.id, created_at__gte=since).values("created_at")
    leads_per_day_prefill: Dict[str, int] = defaultdict(int)
    for r in lead_rows:
        key = _day_key(r.get("created_at"))
        if key:
            leads_per_day_prefill[key] += 1
    leads_per_day = _zero_fill_timeseries(days, now, leads_per_day_prefill, 0)

    # ── Numbers / Calendar accounts ──────────────────────────────────────────
    pn_q = PurchasedNumber.filter(user_id=user.id)
    pn_total = await pn_q.count()
    pn_country = {
        (row["iso_country"] or "unknown"): row["c"]
        for row in await pn_q.annotate(c=Count("id")).group_by("iso_country").values("iso_country", "c")
    }

    cal_q = CalendarAccount.filter(user_id=user.id)
    cal_total = await cal_q.count()
    cal_by_provider = {
        (row["provider"] or "unknown"): row["c"]
        for row in await cal_q.annotate(c=Count("id")).group_by("provider").values("provider", "c")
    }

    # ── Forms ────────────────────────────────────────────────────────────────
    fs_q = FormSubmission.filter(user_id=user.id)
    fs_total = await fs_q.count()
    fs_by_status = {
        (row["status"] or "unknown"): row["c"]
        for row in await fs_q.annotate(c=Count("id")).group_by("status").values("status", "c")
    }
    fs_booked_last_window = await fs_q.filter(
        status=SubmissionStatus.BOOKED.value,
        created_at__gte=since
    ).count()

    # ── Derived KPIs ────────────────────────────────────────────────────────
    total_completed_calls = status_breakdown.get("completed", 0) + status_breakdown.get("COMPLETED", 0)
    avg_daily_calls = round(sum(calls_per_day.values()) / max(1, len(calls_per_day)), 2)
    avg_daily_spend_cents = round(sum(spend_per_day_filled.values()) / max(1, len(spend_per_day_filled)))
    avg_daily_credit_cents = round(sum(credit_per_day_filled.values()) / max(1, len(credit_per_day_filled)))
    avg_call_cost = round(total_cost / total_calls, 4) if total_calls > 0 else 0.0

    return {
        "meta": {
            "window_days": days,
            "window_days_long": days_long,
            "as_of": now.isoformat(),
        },

        "totals": {
            "leads": total_leads,
            "files": total_files,
            "assistants": total_assistants,
            "phone_numbers": total_phone_numbers,
            "knowledge_base_docs": total_kb_docs,
            "balance_cents": balance_cents,
            "bonus_cents": bonus_cents,
        },

        "calls": {
            "lifetime": {
                "count": total_calls,
                "duration_seconds_sum": round(total_duration_sec, 2),
                "avg_duration_seconds": avg_call_duration_sec,
                "cost_sum": round(total_cost, 4),
                "transfer_rate_pct": transfer_rate_pct,
                "transferred_count": transferred_calls,
                "status_breakdown": status_breakdown,
                "ended_reason_breakdown": ended_reason_breakdown,
            },
            "recent": recent_calls,
            "timeseries": {
                "per_day_count": calls_per_day,
                "per_day_duration_seconds": duration_per_day_sec,
                "per_day_cost": cost_per_day,
            },
        },

        "call_details": {
            "rows": total_cd,
            "success_evaluation_breakdown": success_evaluation_breakdown,
            "success_like_rate_pct": success_like_rate_pct,
        },

        "messages": {
            "lifetime": {
                "total": total_messages,
                "success": total_messages_success,
                "failed": total_messages_failed,
                "success_rate_pct": message_success_rate_pct,
            },
            "timeseries": {
                "per_day_count": messages_per_day,
            },
        },

        "appointments": {
            "total": ap_total,
            "status_breakdown": appointment_status_breakdown,
            "upcoming": upcoming,
            "recently_completed": recently_completed,
        },

        "wallet": {
            "lifetime": {
                "credited_cents": lifetime_credit_cents,
                "debited_cents": lifetime_debit_cents,
                "net_cents": lifetime_net_cents,
            },
            "recent_activity": recent_tx,
            f"timeseries_{days_long}d": {
                "credit_per_day_cents": credit_per_day_filled,
                "spend_per_day_cents": spend_per_day_filled,
            },
            "kinds_breakdown_cents": kinds_breakdown,
            "derived": {
                "avg_daily_spend_cents": avg_daily_spend_cents,
                "avg_daily_credit_cents": avg_daily_credit_cents,
            },
        },

        "campaigns": {
            "total": total_campaigns,
            "by_status": campaigns_by_status,
            "lead_progress": {
                "status_breakdown": clp_status_breakdown,
                "attempts_sum": clp_attempts_sum,
            },
        },

        "files_and_leads": {
            "top_files_by_leads": top_files_by_leads,
            "leads_timeseries": {
                "per_day_count": leads_per_day,
            },
        },

        "numbers_and_calendar": {
            "purchased_numbers_total": pn_total,
            "numbers_by_country": pn_country,
            "calendar_accounts_total": cal_total,
            "calendar_by_provider": cal_by_provider,
        },

        "forms": {
            "total_submissions": fs_total,
            "by_status": fs_by_status,
            f"booked_last_{days}d": fs_booked_last_window,
        },

        "derived_kpis": {
            "avg_daily_calls": avg_daily_calls,
            "avg_call_cost": avg_call_cost,
            "completed_calls": total_completed_calls,
        },
    }
