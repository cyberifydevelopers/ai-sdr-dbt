# # controllers/admin_billing.py
# from typing import Annotated, Optional, Dict, Any, List
# from decimal import Decimal, ROUND_HALF_UP
# import os

# import stripe
# from fastapi import APIRouter, Depends, HTTPException, Query
# from pydantic import BaseModel, condecimal, constr

# from models.auth import User
# from models.billing import Payment, Notification, AccountTransaction, PricingSettings
# from helpers.token_helper import get_current_user
# from helpers.pricing_helper import get_active_pricing

# # Keep this router un-prefixed if you include with prefix="/api" in main.py
# router = APIRouter()

# # ── STRIPE ENV ────────────────────────────────────────────────────────────────
# MODE = os.getenv("STRIPE_MODE", "test").lower()  # "test" | "live"
# STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
# STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
# # OPTIONAL: if you're using Stripe Connect and want admin to see THEIR connected account
# STRIPE_ACCOUNT_ID = os.getenv("STRIPE_ACCOUNT_ID", "")  # e.g., "acct_123..."

# if not STRIPE_SECRET_KEY:
#     raise RuntimeError("STRIPE_SECRET_KEY not set")

# stripe.api_key = STRIPE_SECRET_KEY

# if MODE == "test" and not STRIPE_SECRET_KEY.startswith("sk_test_"):
#     raise RuntimeError("STRIPE_MODE=test but STRIPE_SECRET_KEY is not sk_test_*")
# if MODE == "live" and not STRIPE_SECRET_KEY.startswith("sk_live_"):
#     raise RuntimeError("STRIPE_MODE=live but STRIPE_SECRET_KEY is not sk_live_*")


# # ── Helpers ──────────────────────────────────────────────────────────────────
# def _ensure_admin(u: User):
#     role = (u.role or "").lower()
#     if role not in {"admin", "superadmin", "owner"}:
#         raise HTTPException(status_code=403, detail="Admins only")

# def _dec_cents(x: int) -> str:
#     return str((Decimal(x) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

# def _connected_kwargs() -> Dict[str, Any]:
#     """
#     If STRIPE_ACCOUNT_ID is set (Connect), return stripe_account header so we
#     read the connected account's data. Otherwise, return {} and read the
#     platform account.
#     """
#     return {"stripe_account": STRIPE_ACCOUNT_ID} if STRIPE_ACCOUNT_ID.startswith("acct_") else {}

# def _pi_to_row(pi: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Transform a PaymentIntent (and its charge/balance_transaction if present)
#     into a compact row for the admin table. Also fetches BalanceTransaction if
#     Stripe returned only its ID so fee/net are populated.
#     """
#     amount = int(pi.get("amount") or 0)
#     currency = (pi.get("currency") or "usd").upper()
#     status = pi.get("status") or "unknown"
#     created = int(pi.get("created") or 0)
#     customer_email = None

#     # Try to get customer email (expanded customer, or charges->billing_details)
#     cust = pi.get("customer")
#     if isinstance(cust, dict):
#         customer_email = cust.get("email")
#     if not customer_email:
#         charges = (pi.get("charges") or {}).get("data") or []
#         if charges:
#             bd = charges[0].get("billing_details") or {}
#             customer_email = bd.get("email")

#     # Resolve fee + net via balance_transaction on the latest charge
#     fee_cents = None
#     net_cents = None
#     charges = (pi.get("charges") or {}).get("data") or []
#     if charges:
#         bt = charges[0].get("balance_transaction")
#         if isinstance(bt, dict):
#             # already expanded with PaymentIntent.list(expand=[...])
#             try:
#                 fee_cents = int(bt.get("fee"))
#                 net_cents = int(bt.get("net"))
#             except Exception:
#                 pass
#         elif isinstance(bt, str):
#             # Fetch the BT to get fee/net
#             try:
#                 bt_obj = stripe.BalanceTransaction.retrieve(bt, **_connected_kwargs())
#                 fee_cents = int(bt_obj.get("fee") or 0)
#                 net_cents = int(bt_obj.get("net") or 0)
#             except Exception:
#                 # leave as None if not retrievable
#                 pass

#     return {
#         "id": pi.get("id"),
#         "amount_cents": amount,
#         "currency": currency,
#         "status": status,
#         "created": created,
#         "customer_email": customer_email,
#         "fee_cents": fee_cents,
#         "net_cents": net_cents,
#     }


# # ── Pricing (Admin-set) ───────────────────────────────────────────────────────
# class PricingBody(BaseModel):
#     currency: constr(strip_whitespace=True, min_length=3, max_length=8) = "USD"
#     # Human-friendly dollars input:
#     # $/sec (e.g., 0.00125 => 0.125¢/sec => 125 millicents/sec)
#     call_dollars_per_second: condecimal(ge=0, max_digits=12, decimal_places=6)
#     # $/msg (e.g., 0.018 => 1.8¢/msg) -> stored as cents (rounded)
#     text_dollars_per_message: condecimal(ge=0, max_digits=12, decimal_places=6)

# @router.get("/pricing")
# async def get_pricing_admin(user: Annotated[User, Depends(get_current_user)]):
#     _ensure_admin(user)
#     cur, call_mps, text_cents = await get_active_pricing()

#     call_cents_per_second = Decimal(call_mps) / Decimal(1000)          # 125 -> 0.125 ¢/sec
#     call_dollars_per_second = (call_cents_per_second / Decimal(100))   # -> $/sec
#     text_dollars_per_message = Decimal(text_cents) / Decimal(100)      # -> $/msg

#     return {
#         "currency": cur,
#         "call_millicents_per_second": call_mps,
#         "text_cents_per_message": text_cents,
#         "human_readable": {
#             "call_cents_per_second": float(call_cents_per_second),
#             "call_dollars_per_second": float(call_dollars_per_second),
#             "text_dollars_per_message": float(text_dollars_per_message),
#         }
#     }

# @router.put("/pricing")
# async def set_pricing_admin(
#     body: PricingBody,
#     user: Annotated[User, Depends(get_current_user)]
# ):
#     _ensure_admin(user)

#     # $/sec -> millicents/sec (×100 [cents] ×1000 [millicents] = ×100000)
#     call_mps = int((Decimal(body.call_dollars_per_second) * Decimal(100_000)).quantize(0, rounding=ROUND_HALF_UP))
#     # $/msg -> cents/msg (×100)
#     text_cents = int((Decimal(body.text_dollars_per_message) * Decimal(100)).quantize(0, rounding=ROUND_HALF_UP))

#     row = await PricingSettings.create(
#         currency=body.currency.upper(),
#         call_millicents_per_second=call_mps,
#         text_cents_per_message=text_cents,
#         updated_by_user_id=user.id,
#     )

#     await Notification.create(
#         kind="pricing_updated",
#         title="Pricing updated",
#         body=f"Currency={row.currency}, call={row.call_millicents_per_second} m¢/sec, text={row.text_cents_per_message}¢/msg",
#         user_id=user.id,
#         data={
#             "pricing_id": row.id,
#             "currency": row.currency,
#             "call_millicents_per_second": row.call_millicents_per_second,
#             "text_cents_per_message": row.text_cents_per_message,
#         },
#     )
#     return {"ok": True, "id": row.id}


# # ── Lists & Balance (DB) ─────────────────────────────────────────────────────
# @router.get("/payments")
# async def list_payments(
#     user: Annotated[User, Depends(get_current_user)],
#     limit: int = Query(50, ge=1, le=200),
# ):
#     _ensure_admin(user)
#     rows = await Payment.all().prefetch_related("user").limit(limit).values(
#         "id", "created_at", "amount_cents", "fee_cents", "net_cents", "currency", "status",
#         "stripe_payment_intent_id", "stripe_checkout_session_id", "user_id",
#     )
#     return rows

# @router.get("/notifications")
# async def list_notifications(
#     user: Annotated[User, Depends(get_current_user)],
#     limit: int = Query(50, ge=1, le=200),
# ):
#     _ensure_admin(user)
#     rows = await Notification.all().limit(limit).values()
#     return rows

# @router.get("/user/{uid}/balance")
# async def user_balance(uid: int, user: Annotated[User, Depends(get_current_user)]):
#     """
#     Prefer ledger (credits positive, debits negative).
#     If no ledger, fall back to sum of payments.net_cents (historical).
#     """
#     _ensure_admin(user)
#     tx = await AccountTransaction.filter(user_id=uid).values_list("amount_cents", flat=True)
#     if tx:
#         balance = sum(tx)
#         credits = sum([x for x in tx if x > 0])
#         debits = -sum([x for x in tx if x < 0])
#         return {
#             "user_id": uid,
#             "credits_cents": credits,
#             "debits_cents": debits,
#             "balance_cents": balance,
#             "currency": "USD",
#         }

#     paid_net = await Payment.filter(user_id=uid).values_list("net_cents", flat=True)
#     balance = sum(paid_net) if paid_net else 0
#     return {
#         "user_id": uid,
#         "credits_cents": balance,
#         "debits_cents": 0,
#         "balance_cents": balance,
#         "currency": "USD",
#     }

# @router.post("/billing/reconcile-topups")
# async def reconcile_topups(user: User = Depends(get_current_user)):
#     _ensure_admin(user)
#     fixed = 0
#     pays = await Payment.all().values("id", "user_id", "net_cents", "currency", "stripe_payment_intent_id")
#     for p in pays:
#         if (p["net_cents"] or 0) <= 0:
#             continue
#         exists = await AccountTransaction.filter(
#             user_id=p["user_id"],
#             kind="topup_net",
#             stripe_payment_intent_id=p["stripe_payment_intent_id"],
#         ).first()
#         if exists:
#             continue
#         await AccountTransaction.create(
#             user_id=p["user_id"],
#             amount_cents=p["net_cents"],
#             currency=p["currency"] or "USD",
#             kind="topup_net",
#             description=f"Stripe top-up (reconcile): ${_dec_cents(p['net_cents'])}",
#             stripe_payment_intent_id=p["stripe_payment_intent_id"],
#             metadata={"payment_id": p["id"], "source": "reconcile"},
#         )
#         fixed += 1
#     return {"ok": True, "created_ledger_entries": fixed}


# # ── LIVE STRIPE (Admin, real-time from Stripe) ───────────────────────────────
# @router.get("/billing/stripe/summary")
# async def stripe_summary(user: User = Depends(get_current_user)):
#     """
#     Admin-only: real-time snapshot from Stripe (balance, account info).
#     If STRIPE_ACCOUNT_ID is set (Connect), shows that connected account.
#     Otherwise shows your platform account.
#     """
#     _ensure_admin(user)

#     # Account info
#     acct = stripe.Account.retrieve(**_connected_kwargs())
#     # Balance (available / pending per currency)
#     bal = stripe.Balance.retrieve(**_connected_kwargs())

#     # Normalize available/pending lists -> pick primary currency row (default_currency)
#     default_currency = (acct.get("default_currency") or "usd").upper()

#     def _sum_currency(rows: List[Dict[str, Any]], cur: str) -> int:
#         return sum(int(x["amount"]) for x in rows if (x.get("currency") or "").upper() == cur.upper())

#     available_cents = _sum_currency(bal.get("available") or [], default_currency)
#     pending_cents = _sum_currency(bal.get("pending") or [], default_currency)

#     return {
#         "mode": MODE,
#         "key_kind": "test" if STRIPE_SECRET_KEY.startswith("sk_test_") else "live" if STRIPE_SECRET_KEY.startswith("sk_live_") else "unknown",
#         "stripe_account_scope": "connected" if STRIPE_ACCOUNT_ID.startswith("acct_") else "platform",
#         "account": {
#             "id": acct.get("id"),
#             "business_type": acct.get("business_type"),
#             "country": acct.get("country"),
#             "default_currency": default_currency,
#             "charges_enabled": acct.get("charges_enabled"),
#             "payouts_enabled": acct.get("payouts_enabled"),
#             "details_submitted": acct.get("details_submitted"),
#         },
#         "balance": {
#             "available_cents": available_cents,
#             "available_dollars": _dec_cents(available_cents),
#             "pending_cents": pending_cents,
#             "pending_dollars": _dec_cents(pending_cents),
#         },
#     }

# @router.get("/billing/stripe/payments")
# async def stripe_payments(
#     user: User = Depends(get_current_user),
#     limit: int = Query(20, ge=1, le=100),
# ):
#     """
#     Admin-only: latest PaymentIntents directly from Stripe.
#     If account is connected (STRIPE_ACCOUNT_ID), reads that account via Connect.
#     """
#     _ensure_admin(user)

#     # Expand charges + balance_transaction so we can surface fee/net when available
#     pis = stripe.PaymentIntent.list(
#         limit=limit,
#         expand=["data.charges.data.balance_transaction", "data.customer"],
#         **_connected_kwargs()
#     )
#     rows = [_pi_to_row(pi) for pi in (pis.get("data") or [])]
#     return {"count": len(rows), "items": rows}

# @router.post("/billing/stripe/login")
# async def stripe_login_link(user: User = Depends(get_current_user)):
#     """
#     Admin-only: create a Login Link to the Stripe Dashboard for the CONNECTED
#     account. Requires STRIPE_ACCOUNT_ID. For platform accounts, return message.
#     """
#     _ensure_admin(user)

#     if not STRIPE_ACCOUNT_ID.startswith("acct_"):
#         # No Connect account; you log into your platform dashboard as usual.
#         return {
#             "ok": False,
#             "message": "No STRIPE_ACCOUNT_ID configured. This endpoint works for Stripe Connect accounts only.",
#         }

#     link = stripe.Account.create_login_link(STRIPE_ACCOUNT_ID)
#     return {"ok": True, "url": link["url"]}



# controllers/admin_billing.py
from typing import Annotated, Optional, Dict, Any, List
from decimal import Decimal, ROUND_HALF_UP
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, condecimal, constr

from models.auth import User
from models.billing import Payment, Notification, AccountTransaction, PricingSettings
from helpers.token_helper import get_current_user
from helpers.pricing_helper import get_active_pricing

# Keep this router un-prefixed if you include with prefix="/api" in main.py
router = APIRouter()

# ── STRIPE ENV ────────────────────────────────────────────────────────────────
MODE = os.getenv("STRIPE_MODE", "test").lower()  # "test" | "live"
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
# OPTIONAL: if you're using Stripe Connect and want admin to see THEIR connected account
STRIPE_ACCOUNT_ID = os.getenv("STRIPE_ACCOUNT_ID", "")  # e.g., "acct_123..."

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY not set")

stripe.api_key = STRIPE_SECRET_KEY

if MODE == "test" and not STRIPE_SECRET_KEY.startswith("sk_test_"):
    raise RuntimeError("STRIPE_MODE=test but STRIPE_SECRET_KEY is not sk_test_*")
if MODE == "live" and not STRIPE_SECRET_KEY.startswith("sk_live_"):
    raise RuntimeError("STRIPE_MODE=live but STRIPE_SECRET_KEY is not sk_live_*")


# ── Helpers ──────────────────────────────────────────────────────────────────
def _ensure_admin(u: User):
    role = (u.role or "").lower()
    if role not in {"admin", "superadmin", "owner"}:
        raise HTTPException(status_code=403, detail="Admins only")

def _dec_cents(x: int) -> str:
    return str((Decimal(x) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _connected_kwargs() -> Dict[str, Any]:
    """
    If STRIPE_ACCOUNT_ID is set (Connect), return stripe_account header so we
    read the connected account's data. Otherwise, return {} and read the
    platform account.
    """
    return {"stripe_account": STRIPE_ACCOUNT_ID} if STRIPE_ACCOUNT_ID.startswith("acct_") else {}

def _pi_to_row(pi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a PaymentIntent (and its charge/balance_transaction if present)
    into a compact row for the admin table. Also fetches BalanceTransaction if
    Stripe returned only its ID so fee/net are populated.
    """
    amount = int(pi.get("amount") or 0)
    currency = (pi.get("currency") or "usd").upper()
    status = pi.get("status") or "unknown"
    created = int(pi.get("created") or 0)
    customer_email = None

    # Try to get customer email (expanded customer, or charges->billing_details)
    cust = pi.get("customer")
    if isinstance(cust, dict):
        customer_email = cust.get("email")
    if not customer_email:
        charges = (pi.get("charges") or {}).get("data") or []
        if charges:
            bd = charges[0].get("billing_details") or {}
            customer_email = bd.get("email")

    # Resolve fee + net via balance_transaction on the latest charge
    fee_cents = None
    net_cents = None
    charges = (pi.get("charges") or {}).get("data") or []
    if charges:
        bt = charges[0].get("balance_transaction")
        if isinstance(bt, dict):
            # already expanded with PaymentIntent.list(expand=[...])
            try:
                fee_cents = int(bt.get("fee"))
                net_cents = int(bt.get("net"))
            except Exception:
                pass
        elif isinstance(bt, str):
            # Fetch the BT to get fee/net
            try:
                bt_obj = stripe.BalanceTransaction.retrieve(bt, **_connected_kwargs())
                fee_cents = int(bt_obj.get("fee") or 0)
                net_cents = int(bt_obj.get("net") or 0)
            except Exception:
                # leave as None if not retrievable
                pass

    return {
        "id": pi.get("id"),
        "amount_cents": amount,
        "currency": currency,
        "status": status,
        "created": created,
        "customer_email": customer_email,
        "fee_cents": fee_cents,
        "net_cents": net_cents,
    }


# ── Pricing (Admin-set) ───────────────────────────────────────────────────────
class PricingBody(BaseModel):
    currency: constr(strip_whitespace=True, min_length=3, max_length=8) = "USD"
    # Human-friendly dollars input:
    # $/sec (e.g., 0.00125 => 0.125¢/sec => 125 millicents/sec)
    call_dollars_per_second: condecimal(ge=0, max_digits=12, decimal_places=6)
    # $/msg (e.g., 0.018 => 1.8¢/msg) -> stored as cents (rounded)
    text_dollars_per_message: condecimal(ge=0, max_digits=12, decimal_places=6)

@router.get("/pricing")
async def get_pricing_admin(user: Annotated[User, Depends(get_current_user)]):
    _ensure_admin(user)
    cur, call_mps, text_cents = await get_active_pricing()

    call_cents_per_second = Decimal(call_mps) / Decimal(1000)          # 125 -> 0.125 ¢/sec
    call_dollars_per_second = (call_cents_per_second / Decimal(100))   # -> $/sec
    text_dollars_per_message = Decimal(text_cents) / Decimal(100)      # -> $/msg

    return {
        "currency": cur,
        "call_millicents_per_second": call_mps,
        "text_cents_per_message": text_cents,
        "human_readable": {
            "call_cents_per_second": float(call_cents_per_second),
            "call_dollars_per_second": float(call_dollars_per_second),
            "text_dollars_per_message": float(text_dollars_per_message),
        }
    }

@router.put("/pricing")
async def set_pricing_admin(
    body: PricingBody,
    user: Annotated[User, Depends(get_current_user)]
):
    _ensure_admin(user)

    # $/sec -> millicents/sec (×100 [cents] ×1000 [millicents] = ×100000)
    call_mps = int((Decimal(body.call_dollars_per_second) * Decimal(100_000)).quantize(0, rounding=ROUND_HALF_UP))
    # $/msg -> cents/msg (×100)
    text_cents = int((Decimal(body.text_dollars_per_message) * Decimal(100)).quantize(0, rounding=ROUND_HALF_UP))

    row = await PricingSettings.create(
        currency=body.currency.upper(),
        call_millicents_per_second=call_mps,
        text_cents_per_message=text_cents,
        updated_by_user_id=user.id,
    )

    await Notification.create(
        kind="pricing_updated",
        title="Pricing updated",
        body=f"Currency={row.currency}, call={row.call_millicents_per_second} m¢/sec, text={row.text_cents_per_message}¢/msg",
        user_id=user.id,
        data={
            "pricing_id": row.id,
            "currency": row.currency,
            "call_millicents_per_second": row.call_millicents_per_second,
            "text_cents_per_message": row.text_cents_per_message,
        },
    )
    return {"ok": True, "id": row.id}


# ── Lists & Balance (DB) ─────────────────────────────────────────────────────
@router.get("/payments")
async def list_payments(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
):
    _ensure_admin(user)
    rows = await Payment.all().prefetch_related("user").limit(limit).values(
        "id", "created_at", "amount_cents", "fee_cents", "net_cents", "currency", "status",
        "stripe_payment_intent_id", "stripe_checkout_session_id", "user_id",
    )
    return rows

@router.get("/notifications")
async def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
):
    _ensure_admin(user)
    rows = await Notification.all().limit(limit).values()
    return rows

@router.get("/user/{uid}/balance")
async def user_balance(uid: int, user: Annotated[User, Depends(get_current_user)]):
    """
    Prefer ledger (credits positive, debits negative).
    If no ledger, fall back to sum of payments.net_cents (historical).
    """
    _ensure_admin(user)
    tx = await AccountTransaction.filter(user_id=uid).values_list("amount_cents", flat=True)
    if tx:
        balance = sum(tx)
        credits = sum([x for x in tx if x > 0])
        debits = -sum([x for x in tx if x < 0])
        return {
            "user_id": uid,
            "credits_cents": credits,
            "debits_cents": debits,
            "balance_cents": balance,
            "currency": "USD",
        }

    paid_net = await Payment.filter(user_id=uid).values_list("net_cents", flat=True)
    balance = sum(paid_net) if paid_net else 0
    return {
        "user_id": uid,
        "credits_cents": balance,
        "debits_cents": 0,
        "balance_cents": balance,
        "currency": "USD",
    }

@router.post("/billing/reconcile-topups")
async def reconcile_topups(user: User = Depends(get_current_user)):
    _ensure_admin(user)
    fixed = 0
    pays = await Payment.all().values("id", "user_id", "net_cents", "currency", "stripe_payment_intent_id")
    for p in pays:
        if (p["net_cents"] or 0) <= 0:
            continue
        exists = await AccountTransaction.filter(
            user_id=p["user_id"],
            kind="topup_net",
            stripe_payment_intent_id=p["stripe_payment_intent_id"],
        ).first()
        if exists:
            continue
        await AccountTransaction.create(
            user_id=p["user_id"],
            amount_cents=p["net_cents"],
            currency=p["currency"] or "USD",
            kind="topup_net",
            description=f"Stripe top-up (reconcile): ${_dec_cents(p['net_cents'])}",
            stripe_payment_intent_id=p["stripe_payment_intent_id"],
            metadata={"payment_id": p["id"], "source": "reconcile"},
        )
        fixed += 1
    return {"ok": True, "created_ledger_entries": fixed}


# ── LIVE STRIPE (Admin, real-time from Stripe) ───────────────────────────────
@router.get("/billing/stripe/summary")
async def stripe_summary(user: User = Depends(get_current_user)):
    """
    Admin-only: real-time snapshot from Stripe (balance, account info).
    If STRIPE_ACCOUNT_ID is set (Connect), shows that connected account.
    Otherwise shows your platform account.
    """
    _ensure_admin(user)

    # Account info
    acct = stripe.Account.retrieve(**_connected_kwargs())
    # Balance (available / pending per currency)
    bal = stripe.Balance.retrieve(**_connected_kwargs())

    # Normalize available/pending lists -> pick primary currency row (default_currency)
    default_currency = (acct.get("default_currency") or "usd").upper()

    def _sum_currency(rows: List[Dict[str, Any]], cur: str) -> int:
        return sum(int(x["amount"]) for x in rows if (x.get("currency") or "").upper() == cur.upper())

    available_cents = _sum_currency(bal.get("available") or [], default_currency)
    pending_cents = _sum_currency(bal.get("pending") or [], default_currency)

    return {
        "mode": MODE,
        "key_kind": "test" if STRIPE_SECRET_KEY.startswith("sk_test_") else "live" if STRIPE_SECRET_KEY.startswith("sk_live_") else "unknown",
        "stripe_account_scope": "connected" if STRIPE_ACCOUNT_ID.startswith("acct_") else "platform",
        "account": {
            "id": acct.get("id"),
            "business_type": acct.get("business_type"),
            "country": acct.get("country"),
            "default_currency": default_currency,
            "charges_enabled": acct.get("charges_enabled"),
            "payouts_enabled": acct.get("payouts_enabled"),
            "details_submitted": acct.get("details_submitted"),
        },
        "balance": {
            "available_cents": available_cents,
            "available_dollars": _dec_cents(available_cents),
            "pending_cents": pending_cents,
            "pending_dollars": _dec_cents(pending_cents),
        },
    }

@router.get("/billing/stripe/payments")
async def stripe_payments(
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Admin-only: latest PaymentIntents directly from Stripe.
    If account is connected (STRIPE_ACCOUNT_ID), reads that account via Connect.
    """
    _ensure_admin(user)

    # Expand charges + balance_transaction so we can surface fee/net when available
    pis = stripe.PaymentIntent.list(
        limit=limit,
        expand=["data.charges.data.balance_transaction", "data.customer"],
        **_connected_kwargs()
    )
    rows = [_pi_to_row(pi) for pi in (pis.get("data") or [])]
    return {"count": len(rows), "items": rows}

@router.post("/billing/stripe/login")
async def stripe_login_link(user: User = Depends(get_current_user)):
    """
    Admin-only: create a Login Link to the Stripe Dashboard for the CONNECTED
    account. Requires STRIPE_ACCOUNT_ID. For platform accounts, return message.
    """
    _ensure_admin(user)

    if not STRIPE_ACCOUNT_ID.startswith("acct_"):
        # No Connect account; you log into your platform dashboard as usual.
        return {
            "ok": False,
            "message": "No STRIPE_ACCOUNT_ID configured. This endpoint works for Stripe Connect accounts only.",
        }

    link = stripe.Account.create_login_link(STRIPE_ACCOUNT_ID)
    return {"ok": True, "url": link["url"]}
