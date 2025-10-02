# # controllers/stripe_controller.py
# import os
# import stripe
# from typing import Annotated, Optional, Dict, Any

# from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
# from fastapi.responses import HTMLResponse, JSONResponse
# from pydantic import BaseModel, conint

# from helpers.token_helper import get_current_user
# from helpers.billing_helper import (
#     apply_transaction,
#     ensure_stripe_customer,
#     per_minute_cost_cents,
#     compute_call_charge_cents,
# )
# from models.auth import User
# from models.billing import AccountTransaction


# router = APIRouter()

# # ──────────────────────────────────────────────────────────────────────────────
# # MODE & KEYS (default: test) + guardrails
# # ──────────────────────────────────────────────────────────────────────────────
# MODE = os.getenv("STRIPE_MODE", "test").lower()  # "test" | "live"
# STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
# STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
# WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# if not STRIPE_SECRET_KEY:
#     raise RuntimeError("STRIPE_SECRET_KEY not set")

# stripe.api_key = STRIPE_SECRET_KEY

# if MODE == "test" and not STRIPE_SECRET_KEY.startswith("sk_test_"):
#     raise RuntimeError("STRIPE_MODE=test but STRIPE_SECRET_KEY is not sk_test_*")
# if MODE == "live" and not STRIPE_SECRET_KEY.startswith("sk_live_"):
#     raise RuntimeError("STRIPE_MODE=live but STRIPE_SECRET_KEY is not sk_live_*")

# PUBLIC_BASE = os.getenv("BILLING_PUBLIC_BASE", "http://localhost:8000").rstrip("/")
# SUCCESS_URL = os.getenv("BILLING_SUCCESS_URL", f"{PUBLIC_BASE}/success")
# CANCEL_URL  = os.getenv("BILLING_CANCEL_URL",  f"{PUBLIC_BASE}/cancel")

# # ──────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ──────────────────────────────────────────────────────────────────────────────
# class CheckoutBody(BaseModel):
#     amount_usd: conint(strict=True, gt=0)  # e.g., 5 = $5 top-up

# class SimDebitBody(BaseModel):
#     duration_seconds: conint(ge=1)        # e.g., 185 => ceil to 4 min @ 10¢/min => 40¢

# class SimCreditBody(BaseModel):
#     amount_cents: conint(gt=0)

# # ──────────────────────────────────────────────────────────────────────────────
# # Helpers
# # ──────────────────────────────────────────────────────────────────────────────
# def _ok(data: Dict[str, Any]) -> JSONResponse:
#     return JSONResponse(data)

# def _err(status_code: int, msg: str) -> None:
#     raise HTTPException(status_code=status_code, detail=msg)

# # ──────────────────────────────────────────────────────────────────────────────
# # Public UX / Config
# # ──────────────────────────────────────────────────────────────────────────────
# @router.get("/mode")
# async def get_billing_mode():
#     key_kind = "test" if STRIPE_SECRET_KEY.startswith("sk_test_") else "live" if STRIPE_SECRET_KEY.startswith("sk_live_") else "unknown"
#     return {"mode": MODE, "key_kind": key_kind}

# @router.get("/config")
# async def get_public_config():
#     return {
#         "publishable_key": STRIPE_PUBLIC_KEY,
#         "mode": MODE,
#         "success_url": SUCCESS_URL,
#         "cancel_url": CANCEL_URL,
#     }

# @router.get("/pricing")
# async def get_pricing(user: Annotated[User, Depends(get_current_user)]):
#     rate = per_minute_cost_cents(user)
#     return {
#         "currency": user.currency or "USD",
#         "per_minute_cents": rate,
#         "per_minute_dollars": rate / 100.0,
#         "billing_policy": "per-started-minute (ceil)",
#         "examples": { "60s": rate, "61s": rate * 2, "185s": rate * 4 }
#     }

# # ──────────────────────────────────────────────────────────────────────────────
# # Wallet
# # ──────────────────────────────────────────────────────────────────────────────
# @router.get("/wallet")
# async def get_wallet(user: Annotated[User, Depends(get_current_user)]):
#     return {
#         "balance_cents": user.balance_cents or 0,
#         "bonus_cents": user.bonus_cents or 0,
#         "currency": user.currency or "USD",
#         "per_minute_cents": user.per_minute_cents or 10,
#     }

# @router.get("/wallet/transactions")
# async def wallet_transactions(
#     user: Annotated[User, Depends(get_current_user)],
#     limit: int = Query(50, ge=1, le=200),
# ):
#     rows = await AccountTransaction.filter(user=user).limit(limit).values()
#     return rows

# @router.get("/wallet/can-call")
# async def wallet_can_call(
#     user: Annotated[User, Depends(get_current_user)],
#     seconds: int = Query(..., ge=1, description="Planned call duration in seconds"),
# ):
#     rate = per_minute_cost_cents(user)
#     needed = compute_call_charge_cents(seconds, rate_per_min_cents=rate, round_mode="ceil")
#     balance = (user.balance_cents or 0) + (user.bonus_cents or 0)
#     ok = balance >= needed
#     return {
#         "ok": ok,
#         "needed_cents": needed,
#         "balance_cents": balance,
#         "shortfall_cents": 0 if ok else max(0, needed - balance),
#         "note": "Per-started-minute billing."
#     }

# # ──────────────────────────────────────────────────────────────────────────────
# # Top-up via Stripe Checkout
# # ──────────────────────────────────────────────────────────────────────────────
# @router.post("/topup/checkout")
# async def create_topup_checkout(body: CheckoutBody, user: Annotated[User, Depends(get_current_user)]):
#     """
#     Create a Stripe Checkout Session for a one-time wallet top-up.
#     Metadata is set on both Session & PaymentIntent for reliable crediting.
#     """
#     try:
#         customer_id = await ensure_stripe_customer(user, stripe)
#         meta = {"user_id": str(user.id), "kind": "wallet_topup", "mode": MODE}
#         session = stripe.checkout.Session.create(
#             mode="payment",
#             customer=customer_id,
#             payment_method_types=["card"],
#             line_items=[{
#                 "quantity": 1,
#                 "price_data": {
#                     "currency": (user.currency or "USD").lower(),
#                     "product_data": {"name": "Wallet Top-up"},
#                     "unit_amount": body.amount_usd * 100,
#                 },
#             }],
#             payment_intent_data={"metadata": meta},
#             success_url=SUCCESS_URL,
#             cancel_url=CANCEL_URL,
#             metadata=meta,
#         )
#         return {"id": session["id"], "url": session["url"]}
#     except Exception as e:
#         _err(status.HTTP_400_BAD_REQUEST, str(e))

# # ──────────────────────────────────────────────────────────────────────────────
# # Stripe Customer Portal (manage cards)
# # ──────────────────────────────────────────────────────────────────────────────
# @router.post("/portal")
# async def create_billing_portal(user: Annotated[User, Depends(get_current_user)]):
#     """
#     Creates a Customer Portal session. In TEST mode, Stripe requires that you
#     save a default portal configuration at:
#     https://dashboard.stripe.com/test/settings/billing/portal
#     """
#     try:
#         customer_id = await ensure_stripe_customer(user, stripe)
#         portal = stripe.billing_portal.Session.create(
#             customer=customer_id,
#             return_url=PUBLIC_BASE,
#         )
#         return {"url": portal["url"]}
#     except stripe.error.InvalidRequestError as e:
#         # Nice hint when default config isn't created yet (what you just saw)
#         _err(
#             status.HTTP_400_BAD_REQUEST,
#             "Stripe portal not configured for TEST mode. "
#             "Open https://dashboard.stripe.com/test/settings/billing/portal and click Save to create the default configuration."
#         )
#     except Exception as e:
#         _err(status.HTTP_400_BAD_REQUEST, str(e))

# # Friendly success/cancel pages (useful when testing bare URLs)
# @router.get("/success", response_class=HTMLResponse)
# async def success_page():
#     return "<h3>Payment successful ✅</h3><p>You can close this window.</p>"

# @router.get("/cancel", response_class=HTMLResponse)
# async def cancel_page():
#     return "<h3>Payment canceled ❌</h3><p>No charge was made.</p>"

# # ──────────────────────────────────────────────────────────────────────────────
# # Webhook (source of truth)
# # ──────────────────────────────────────────────────────────────────────────────
# @router.post("/webhook")
# async def stripe_webhook(req: Request):
#     # 1) Read raw payload as string for signature verification
#     raw = await req.body()
#     try:
#         payload = raw.decode("utf-8")
#     except Exception:
#         payload = ""

#     # 2) Signature header
#     sig_header = req.headers.get("stripe-signature")
#     if not sig_header:
#         if MODE == "test":
#             safe_headers = {k: v for k, v in req.headers.items() if k.lower() != "authorization"}
#             _err(status.HTTP_400_BAD_REQUEST, f"Missing Stripe-Signature header. Got headers: {safe_headers}")
#         _err(status.HTTP_400_BAD_REQUEST, "Missing Stripe-Signature header.")

#     if not WEBHOOK_SECRET or not WEBHOOK_SECRET.startswith("whsec_"):
#         _err(status.HTTP_400_BAD_REQUEST, "Server misconfigured: STRIPE_WEBHOOK_SECRET missing or invalid.")

#     # 3) Construct event
#     try:
#         event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
#     except Exception as e:
#         _err(status.HTTP_400_BAD_REQUEST, f"Webhook verify failed: {e}")

#     # 4) Ignore cross-mode events
#     is_live_event = bool(event.get("livemode"))
#     if MODE == "test" and is_live_event:
#         return _ok({"ok": True, "skipped": "live event ignored (test mode)"})
#     if MODE == "live" and not is_live_event:
#         return _ok({"ok": True, "skipped": "test event ignored (live mode)"})

#     # 5) Handle success → credit wallet
#     if event["type"] in ("checkout.session.completed", "payment_intent.succeeded"):
#         pi_id: Optional[str] = None
#         amount_received: Optional[int] = None
#         currency = "USD"
#         user_id: Optional[str] = None

#         if event["type"] == "checkout.session.completed":
#             session = event["data"]["object"]
#             pi_id = session.get("payment_intent")
#             amount_received = session.get("amount_total")
#             currency = (session.get("currency") or "usd").upper()
#             user_id = (session.get("metadata") or {}).get("user_id")
#         else:
#             intent = event["data"]["object"]
#             pi_id = intent.get("id")
#             amount_received = intent.get("amount_received") or intent.get("amount")
#             currency = (intent.get("currency") or "usd").upper()
#             user_id = (intent.get("metadata") or {}).get("user_id")
#             # Fallback: fetch Session for metadata if missing
#             if not user_id and pi_id:
#                 try:
#                     sessions = stripe.checkout.Session.list(payment_intent=pi_id, limit=1)
#                     if sessions and sessions["data"]:
#                         user_id = (sessions["data"][0].get("metadata") or {}).get("user_id")
#                 except Exception:
#                     pass

#         if not (user_id and amount_received and pi_id):
#             return _ok({"ok": True, "skipped": True})

#         try:
#             uid = int(user_id)
#         except Exception:
#             return _ok({"ok": True, "skipped": True})

#         # Idempotency: do not double-credit same PI
#         already = await AccountTransaction.filter(stripe_payment_intent_id=pi_id).exists()
#         if not already:
#             await apply_transaction(
#                 user_id=uid,
#                 amount_cents=int(amount_received),
#                 kind="topup",
#                 description="Stripe wallet top-up",
#                 currency=currency.upper(),
#                 stripe_pi=pi_id,
#                 metadata={"source": "stripe_webhook", "mode": MODE},
#             )

#     return _ok({"ok": True})

# # ──────────────────────────────────────────────────────────────────────────────
# # Test utilities (only in TEST mode)
# # ──────────────────────────────────────────────────────────────────────────────
# if MODE == "test":
#     @router.post("/test/credit")
#     async def test_credit(body: SimCreditBody, user: Annotated[User, Depends(get_current_user)]):
#         """
#         Direct credit in TEST mode (bypasses Stripe). Handy for quick iterations.
#         """
#         new_balance = await apply_transaction(
#             user_id=user.id,
#             amount_cents=body.amount_cents,
#             kind="test_credit",
#             description="Manual test credit (no Stripe)",
#             currency=(user.currency or "USD").upper(),
#             stripe_pi=None,
#             metadata={"source": "manual_test"},
#         )
#         return {"credited_cents": body.amount_cents, "new_balance_cents": new_balance}

#     @router.post("/test/debit")
#     async def test_debit(body: SimDebitBody, user: Annotated[User, Depends(get_current_user)]):
#         """
#         Simulate a call debit using the same policy as production billing.
#         Returns 402 if balance is insufficient.
#         """
#         try:
#             rate = per_minute_cost_cents(user)  # default 10¢/min
#             charge_cents = compute_call_charge_cents(
#                 duration_seconds=body.duration_seconds,
#                 rate_per_min_cents=rate,
#                 round_mode="ceil",
#             )
#             new_balance = await apply_transaction(
#                 user_id=user.id,
#                 amount_cents=-charge_cents,
#                 kind="debit_call",
#                 description=f"Test debit: {int((body.duration_seconds+59)//60)} min @ ${rate/100:.2f}/min",
#             )
#             return {"debited_cents": charge_cents, "new_balance_cents": new_balance}
#         except ValueError as e:  # "Insufficient balance"
#             _err(status.HTTP_402_PAYMENT_REQUIRED, str(e))










# controllers/stripe_controller.py
import os
import math
import stripe
from typing import Annotated, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, conint, validator

from helpers.token_helper import get_current_user
from helpers.billing_helper import (
    apply_transaction,
    ensure_stripe_customer,
    per_minute_cost_cents,       # kept for compatibility with your earlier logic
    compute_call_charge_cents,   # still used by old test debit endpoint
)
from models.auth import User
from models.billing import AccountTransaction


router = APIRouter(prefix="/billing", tags=["Billing / Stripe"])

# ──────────────────────────────────────────────────────────────────────────────
# MODE & KEYS (default: test) + guardrails
# ──────────────────────────────────────────────────────────────────────────────
MODE = os.getenv("STRIPE_MODE", "test").lower()  # "test" | "live"
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY not set")

stripe.api_key = STRIPE_SECRET_KEY

if MODE == "test" and not STRIPE_SECRET_KEY.startswith("sk_test_"):
    raise RuntimeError("STRIPE_MODE=test but STRIPE_SECRET_KEY is not sk_test_*")
if MODE == "live" and not STRIPE_SECRET_KEY.startswith("sk_live_"):
    raise RuntimeError("STRIPE_MODE=live but STRIPE_SECRET_KEY is not sk_live_*")

PUBLIC_BASE = os.getenv("BILLING_PUBLIC_BASE", "http://localhost:8000").rstrip("/")
SUCCESS_URL = os.getenv("BILLING_SUCCESS_URL", f"{PUBLIC_BASE}/billing/success")
CANCEL_URL  = os.getenv("BILLING_CANCEL_URL",  f"{PUBLIC_BASE}/billing/cancel")

# ──────────────────────────────────────────────────────────────────────────────
# Pricing constants (in USD cents)
# ──────────────────────────────────────────────────────────────────────────────
CALL_SURCHARGE_CROSS_PER_MIN_CENTS = 0.5   # 0.5 cents per minute
CALL_SURCHARGE_SAME_PER_MIN_CENTS  = 0.2   # 0.2 cents per minute

TEXT_SURCHARGE_CROSS_PER_MSG_CENTS = 0.3   # 0.3 cents per message
TEXT_SURCHARGE_SAME_PER_MSG_CENTS  = 0.2   # 0.2 cents per message


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────
class CheckoutBody(BaseModel):
    amount_usd: conint(strict=True, gt=0)  # e.g., 5 = $5 top-up


class CallPreviewBody(BaseModel):
    duration_seconds: conint(ge=1)
    actual_cost_cents: conint(ge=0)
    from_country: str  # ISO-3166 alpha-2 (e.g., "US")
    to_country: str

    @validator("from_country", "to_country")
    def _iso_upper(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if len(v) != 2:
            raise ValueError("country must be ISO-3166 alpha-2 (e.g., 'US')")
        return v


class CallDebitBody(CallPreviewBody):
    """Same shape as preview; will actually debit wallet."""


class TextPreviewBody(BaseModel):
    messages: conint(ge=1)
    actual_cost_cents_per_message: conint(ge=0)
    from_country: str
    to_country: str

    @validator("from_country", "to_country")
    def _iso_upper(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if len(v) != 2:
            raise ValueError("country must be ISO-3166 alpha-2 (e.g., 'US')")
        return v


class TextDebitBody(TextPreviewBody):
    """Same shape as preview; will actually debit wallet."""


class SimDebitBody(BaseModel):
    duration_seconds: conint(ge=1)


class SimCreditBody(BaseModel):
    amount_cents: conint(gt=0)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(data)

def _err(status_code: int, msg: str) -> None:
    raise HTTPException(status_code=status_code, detail=msg)

def cents_round(x: float) -> int:
    """Standard rounding to nearest cent (0.5 -> 1)."""
    return int(round(x))

def is_cross_country(from_country: str, to_country: str) -> bool:
    """True if countries differ (case-insensitive)."""
    return (from_country or "").strip().upper() != (to_country or "").strip().upper()

def calc_call_total_cents(
    actual_cost_cents: int,
    duration_seconds: int,
    from_country: str,
    to_country: str,
) -> int:
    """
    Total = provider's actual cost + surcharge (per-minute rate prorated by seconds).
    Surcharge/minute:
      - cross-country: 0.5¢/min
      - same-country : 0.2¢/min
    Surcharge is prorated by seconds (no ceiling).
    """
    cross = is_cross_country(from_country, to_country)
    rate_per_min = CALL_SURCHARGE_CROSS_PER_MIN_CENTS if cross else CALL_SURCHARGE_SAME_PER_MIN_CENTS
    # prorate by seconds:
    surcharge = rate_per_min * (duration_seconds / 60.0)
    total = float(actual_cost_cents) + surcharge
    return cents_round(total)

def calc_text_total_cents(
    actual_cost_cents_per_message: int,
    messages: int,
    from_country: str,
    to_country: str,
) -> int:
    """
    Total = sum(actual per-message cost) + per-message surcharge.
    Surcharge/message:
      - cross-country: 0.3¢
      - same-country : 0.2¢
    """
    cross = is_cross_country(from_country, to_country)
    per_msg_surcharge = TEXT_SURCHARGE_CROSS_PER_MSG_CENTS if cross else TEXT_SURCHARGE_SAME_PER_MSG_CENTS
    # subtotal actual provider cost:
    provider_total = actual_cost_cents_per_message * messages
    # surcharge total:
    surcharge_total = per_msg_surcharge * messages
    total = float(provider_total) + surcharge_total
    return cents_round(total)


# ──────────────────────────────────────────────────────────────────────────────
# Public UX / Config
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/mode")
async def get_billing_mode():
    key_kind = "test" if STRIPE_SECRET_KEY.startswith("sk_test_") else "live" if STRIPE_SECRET_KEY.startswith("sk_live_") else "unknown"
    return {"mode": MODE, "key_kind": key_kind}

@router.get("/config")
async def get_public_config():
    return {
        "publishable_key": STRIPE_PUBLIC_KEY,
        "mode": MODE,
        "success_url": SUCCESS_URL,
        "cancel_url": CANCEL_URL,
    }

@router.get("/pricing")
async def get_pricing(user: Annotated[User, Depends(get_current_user)]):
    """
    Returns surcharge policy + legacy per-minute info for reference.
    """
    legacy_per_min = per_minute_cost_cents(user)  # kept for compatibility/show
    return {
        "currency": user.currency or "USD",
        "legacy_per_minute_cents": legacy_per_min,
        "legacy_per_minute_dollars": legacy_per_min / 100.0,
        "billing_policy": "wallet + Stripe top-ups; usage debits are provider actual cost + small surcharge",
        "call_surcharge": {
            "cross_country_per_min_cents": CALL_SURCHARGE_CROSS_PER_MIN_CENTS,
            "same_country_per_min_cents": CALL_SURCHARGE_SAME_PER_MIN_CENTS,
            "proration": "per-second (no ceiling)",
        },
        "text_surcharge": {
            "cross_country_per_message_cents": TEXT_SURCHARGE_CROSS_PER_MSG_CENTS,
            "same_country_per_message_cents": TEXT_SURCHARGE_SAME_PER_MSG_CENTS,
        },
        "examples": {
            "call_60s_cross_country": calc_call_total_cents(0, 60, "US", "GB"),
            "call_185s_same_country": calc_call_total_cents(0, 185, "US", "US"),
            "text_1_cross_country": calc_text_total_cents(0, 1, "US", "GB"),
            "text_3_same_country": calc_text_total_cents(0, 3, "US", "US"),
        }
    }

# ──────────────────────────────────────────────────────────────────────────────
# Wallet
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/wallet")
async def get_wallet(user: Annotated[User, Depends(get_current_user)]):
    return {
        "balance_cents": user.balance_cents or 0,
        "bonus_cents": user.bonus_cents or 0,
        "currency": user.currency or "USD",
        "per_minute_cents_legacy": user.per_minute_cents or 10,
    }

@router.get("/wallet/transactions")
async def wallet_transactions(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
):
    rows = await AccountTransaction.filter(user=user).order_by("-created_at").limit(limit).values()
    return rows

@router.get("/wallet/can-call")
async def wallet_can_call(
    user: Annotated[User, Depends(get_current_user)],
    seconds: int = Query(..., ge=1, description="Planned call duration in seconds"),
    actual_cost_cents: int = Query(0, ge=0, description="Provider base cost (cents) for this call so far / predicted"),
    from_country: str = Query(..., min_length=2, max_length=2, description="ISO-3166 alpha-2"),
    to_country: str = Query(..., min_length=2, max_length=2, description="ISO-3166 alpha-2"),
):
    """
    Preview affordability for a specific call using the new surcharge policy.
    """
    needed = calc_call_total_cents(actual_cost_cents, seconds, from_country.upper(), to_country.upper())
    balance = (user.balance_cents or 0) + (user.bonus_cents or 0)
    ok = balance >= needed
    return {
        "ok": ok,
        "needed_cents": needed,
        "balance_cents": balance,
        "shortfall_cents": 0 if ok else max(0, needed - balance),
        "note": "Call surcharge is prorated per second; provider cost + small surcharge.",
    }

# ──────────────────────────────────────────────────────────────────────────────
# Top-up via Stripe Checkout
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/topup/checkout")
async def create_topup_checkout(body: CheckoutBody, user: Annotated[User, Depends(get_current_user)]):
    """
    Create a Stripe Checkout Session for a one-time wallet top-up.
    Metadata is set on both Session & PaymentIntent for reliable crediting.
    """
    try:
        customer_id = await ensure_stripe_customer(user, stripe)
        meta = {"user_id": str(user.id), "kind": "wallet_topup", "mode": MODE}
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            payment_method_types=["card"],
            allow_promotion_codes=True,  # nice DX
            automatic_tax={"enabled": False},  # set True if you enable Stripe Tax
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": (user.currency or "USD").lower(),
                    "product_data": {"name": "Wallet Top-up"},
                    "unit_amount": body.amount_usd * 100,
                },
            }],
            payment_intent_data={"metadata": meta},
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            metadata=meta,
        )
        return {"id": session["id"], "url": session["url"]}
    except Exception as e:
        _err(status.HTTP_400_BAD_REQUEST, str(e))

# ──────────────────────────────────────────────────────────────────────────────
# Stripe Customer Portal (manage cards)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/portal")
async def create_billing_portal(user: Annotated[User, Depends(get_current_user)]):
    """
    Creates a Customer Portal session. In TEST mode, Stripe requires that you
    save a default portal configuration at:
    https://dashboard.stripe.com/test/settings/billing/portal
    """
    try:
        customer_id = await ensure_stripe_customer(user, stripe)
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=PUBLIC_BASE,
        )
        return {"url": portal["url"]}
    except stripe.error.InvalidRequestError:
        _err(
            status.HTTP_400_BAD_REQUEST,
            "Stripe portal not configured for TEST mode. "
            "Open https://dashboard.stripe.com/test/settings/billing/portal and click Save to create the default configuration."
        )
    except Exception as e:
        _err(status.HTTP_400_BAD_REQUEST, str(e))

# Friendly success/cancel pages (useful when testing bare URLs)
@router.get("/success", response_class=HTMLResponse)
async def success_page():
    return "<h3>Payment successful ✅</h3><p>You can close this window.</p>"

@router.get("/cancel", response_class=HTMLResponse)
async def cancel_page():
    return "<h3>Payment canceled ❌</h3><p>No charge was made.</p>"

# ──────────────────────────────────────────────────────────────────────────────
# Webhook (source of truth)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/webhook")
async def stripe_webhook(req: Request):
    # 1) Read raw payload as string for signature verification
    raw = await req.body()
    try:
        payload = raw.decode("utf-8")
    except Exception:
        payload = ""

    # 2) Signature header
    sig_header = req.headers.get("stripe-signature")
    if not sig_header:
        if MODE == "test":
            safe_headers = {k: v for k, v in req.headers.items() if k.lower() != "authorization"}
            _err(status.HTTP_400_BAD_REQUEST, f"Missing Stripe-Signature header. Got headers: {safe_headers}")
        _err(status.HTTP_400_BAD_REQUEST, "Missing Stripe-Signature header.")

    if not WEBHOOK_SECRET or not WEBHOOK_SECRET.startswith("whsec_"):
        _err(status.HTTP_400_BAD_REQUEST, "Server misconfigured: STRIPE_WEBHOOK_SECRET missing or invalid.")

    # 3) Construct event
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except Exception as e:
        _err(status.HTTP_400_BAD_REQUEST, f"Webhook verify failed: {e}")

    # 4) Ignore cross-mode events
    is_live_event = bool(event.get("livemode"))
    if MODE == "test" and is_live_event:
        return _ok({"ok": True, "skipped": "live event ignored (test mode)"})
    if MODE == "live" and not is_live_event:
        return _ok({"ok": True, "skipped": "test event ignored (live mode)"})

    # 5) Handle success → credit wallet
    if event["type"] in ("checkout.session.completed", "payment_intent.succeeded"):
        pi_id: Optional[str] = None
        amount_received: Optional[int] = None
        currency = "USD"
        user_id: Optional[str] = None

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            pi_id = session.get("payment_intent")
            amount_received = session.get("amount_total")
            currency = (session.get("currency") or "usd").upper()
            user_id = (session.get("metadata") or {}).get("user_id")
        else:
            intent = event["data"]["object"]
            pi_id = intent.get("id")
            amount_received = intent.get("amount_received") or intent.get("amount")
            currency = (intent.get("currency") or "usd").upper()
            user_id = (intent.get("metadata") or {}).get("user_id")
            # Fallback: fetch Session for metadata if missing
            if not user_id and pi_id:
                try:
                    sessions = stripe.checkout.Session.list(payment_intent=pi_id, limit=1)
                    if sessions and sessions["data"]:
                        user_id = (sessions["data"][0].get("metadata") or {}).get("user_id")
                except Exception:
                    pass

        if not (user_id and amount_received and pi_id):
            return _ok({"ok": True, "skipped": True})

        try:
            uid = int(user_id)
        except Exception:
            return _ok({"ok": True, "skipped": True})

        # Idempotency: do not double-credit same PI
        already = await AccountTransaction.filter(stripe_payment_intent_id=pi_id).exists()
        if not already:
            await apply_transaction(
                user_id=uid,
                amount_cents=int(amount_received),
                kind="topup",
                description="Stripe wallet top-up",
                currency=currency.upper(),
                stripe_pi=pi_id,
                metadata={"source": "stripe_webhook", "mode": MODE},
            )

    return _ok({"ok": True})

# ──────────────────────────────────────────────────────────────────────────────
# Usage PREVIEW endpoints (no debit)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/usage/call/preview")
async def preview_call_cost(
    body: CallPreviewBody,
    user: Annotated[User, Depends(get_current_user)],
):
    total_cents = calc_call_total_cents(
        actual_cost_cents=body.actual_cost_cents,
        duration_seconds=body.duration_seconds,
        from_country=body.from_country,
        to_country=body.to_country,
    )
    return {
        "currency": user.currency or "USD",
        "total_cents": total_cents,
        "breakdown": {
            "actual_cost_cents": body.actual_cost_cents,
            "surcharge_cents": total_cents - body.actual_cost_cents,
            "seconds": body.duration_seconds,
            "cross_country": is_cross_country(body.from_country, body.to_country),
        },
    }

@router.post("/usage/text/preview")
async def preview_text_cost(
    body: TextPreviewBody,
    user: Annotated[User, Depends(get_current_user)],
):
    total_cents = calc_text_total_cents(
        actual_cost_cents_per_message=body.actual_cost_cents_per_message,
        messages=body.messages,
        from_country=body.from_country,
        to_country=body.to_country,
    )
    provider_total = body.actual_cost_cents_per_message * body.messages
    return {
        "currency": user.currency or "USD",
        "total_cents": total_cents,
        "breakdown": {
            "actual_provider_total_cents": provider_total,
            "surcharge_cents": total_cents - provider_total,
            "messages": body.messages,
            "cross_country": is_cross_country(body.from_country, body.to_country),
        },
    }

# ──────────────────────────────────────────────────────────────────────────────
# Usage DEBIT endpoints (charge wallet; 402 if insufficient)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/usage/call/debit")
async def debit_call(
    body: CallDebitBody,
    user: Annotated[User, Depends(get_current_user)],
):
    total_cents = calc_call_total_cents(
        actual_cost_cents=body.actual_cost_cents,
        duration_seconds=body.duration_seconds,
        from_country=body.from_country,
        to_country=body.to_country,
    )
    balance = (user.balance_cents or 0) + (user.bonus_cents or 0)
    if balance < total_cents:
        _err(status.HTTP_402_PAYMENT_REQUIRED, f"Insufficient balance. Need {total_cents}¢, have {balance}¢.")

    desc = (
        f"Call debit: {body.duration_seconds}s "
        f"({'cross' if is_cross_country(body.from_country, body.to_country) else 'same'}-country) "
        f"(actual {body.actual_cost_cents}¢ + surcharge {total_cents - body.actual_cost_cents}¢)"
    )
    new_balance = await apply_transaction(
        user_id=user.id,
        amount_cents=-total_cents,
        kind="debit_call",
        description=desc,
        currency=(user.currency or "USD").upper(),
        stripe_pi=None,
        metadata={
            "from_country": body.from_country,
            "to_country": body.to_country,
            "duration_seconds": body.duration_seconds,
            "actual_cost_cents": body.actual_cost_cents,
            "pricing_mode": "provider_actual_plus_surcharge_prorated_seconds",
        },
    )
    return {"debited_cents": total_cents, "new_balance_cents": new_balance}

@router.post("/usage/text/debit")
async def debit_text(
    body: TextDebitBody,
    user: Annotated[User, Depends(get_current_user)],
):
    total_cents = calc_text_total_cents(
        actual_cost_cents_per_message=body.actual_cost_cents_per_message,
        messages=body.messages,
        from_country=body.from_country,
        to_country=body.to_country,
    )
    balance = (user.balance_cents or 0) + (user.bonus_cents or 0)
    if balance < total_cents:
        _err(status.HTTP_402_PAYMENT_REQUIRED, f"Insufficient balance. Need {total_cents}¢, have {balance}¢.")

    provider_total = body.actual_cost_cents_per_message * body.messages
    desc = (
        f"Text debit: {body.messages} msg "
        f"({'cross' if is_cross_country(body.from_country, body.to_country) else 'same'}-country) "
        f"(actual {provider_total}¢ + surcharge {total_cents - provider_total}¢)"
    )
    new_balance = await apply_transaction(
        user_id=user.id,
        amount_cents=-total_cents,
        kind="debit_text",
        description=desc,
        currency=(user.currency or "USD").upper(),
        stripe_pi=None,
        metadata={
            "from_country": body.from_country,
            "to_country": body.to_country,
            "messages": body.messages,
            "actual_cost_cents_per_message": body.actual_cost_cents_per_message,
            "pricing_mode": "provider_actual_plus_surcharge_per_message",
        },
    )
    return {"debited_cents": total_cents, "new_balance_cents": new_balance}


if MODE == "test":
    @router.post("/test/credit")
    async def test_credit(body: SimCreditBody, user: Annotated[User, Depends(get_current_user)]):
        """
        Direct credit in TEST mode (bypasses Stripe). Handy for quick iterations.
        """
        new_balance = await apply_transaction(
            user_id=user.id,
            amount_cents=body.amount_cents,
            kind="test_credit",
            description="Manual test credit (no Stripe)",
            currency=(user.currency or "USD").upper(),
            stripe_pi=None,
            metadata={"source": "manual_test"},
        )
        return {"credited_cents": body.amount_cents, "new_balance_cents": new_balance}

    @router.post("/test/debit")
    async def test_debit(body: SimDebitBody, user: Annotated[User, Depends(get_current_user)]):
        """
        Legacy: Simulate a call debit using your old per-started-minute policy
        (still available for quick testing scenarios).
        """
        try:
            rate = per_minute_cost_cents(user)  
            charge_cents = compute_call_charge_cents(
                duration_seconds=body.duration_seconds,
                rate_per_min_cents=rate,
                round_mode="ceil",
            )
            new_balance = await apply_transaction(
                user_id=user.id,
                amount_cents=-charge_cents,
                kind="debit_call_legacy",
                description=f"Legacy debit: {int((body.duration_seconds+59)//60)} min @ {rate}¢/min (ceil)",
            )
            return {"debited_cents": charge_cents, "new_balance_cents": new_balance}
        except ValueError as e: 
            _err(status.HTTP_402_PAYMENT_REQUIRED, str(e))
