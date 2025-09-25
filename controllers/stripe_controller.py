# controllers/stripe_controller.py
import os
import stripe
from typing import Annotated, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, conint

from helpers.token_helper import get_current_user
from helpers.billing_helper import (
    apply_transaction,
    ensure_stripe_customer,
    per_minute_cost_cents,
    compute_call_charge_cents,
)
from models.auth import User
from models.billing import AccountTransaction


router = APIRouter()

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
SUCCESS_URL = os.getenv("BILLING_SUCCESS_URL", f"{PUBLIC_BASE}/success")
CANCEL_URL  = os.getenv("BILLING_CANCEL_URL",  f"{PUBLIC_BASE}/cancel")

# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────
class CheckoutBody(BaseModel):
    amount_usd: conint(strict=True, gt=0)  # e.g., 5 = $5 top-up

class SimDebitBody(BaseModel):
    duration_seconds: conint(ge=1)        # e.g., 185 => ceil to 4 min @ 10¢/min => 40¢

class SimCreditBody(BaseModel):
    amount_cents: conint(gt=0)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(data)

def _err(status_code: int, msg: str) -> None:
    raise HTTPException(status_code=status_code, detail=msg)

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
    rate = per_minute_cost_cents(user)
    return {
        "currency": user.currency or "USD",
        "per_minute_cents": rate,
        "per_minute_dollars": rate / 100.0,
        "billing_policy": "per-started-minute (ceil)",
        "examples": { "60s": rate, "61s": rate * 2, "185s": rate * 4 }
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
        "per_minute_cents": user.per_minute_cents or 10,
    }

@router.get("/wallet/transactions")
async def wallet_transactions(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=200),
):
    rows = await AccountTransaction.filter(user=user).limit(limit).values()
    return rows

@router.get("/wallet/can-call")
async def wallet_can_call(
    user: Annotated[User, Depends(get_current_user)],
    seconds: int = Query(..., ge=1, description="Planned call duration in seconds"),
):
    rate = per_minute_cost_cents(user)
    needed = compute_call_charge_cents(seconds, rate_per_min_cents=rate, round_mode="ceil")
    balance = (user.balance_cents or 0) + (user.bonus_cents or 0)
    ok = balance >= needed
    return {
        "ok": ok,
        "needed_cents": needed,
        "balance_cents": balance,
        "shortfall_cents": 0 if ok else max(0, needed - balance),
        "note": "Per-started-minute billing."
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
    except stripe.error.InvalidRequestError as e:
        # Nice hint when default config isn't created yet (what you just saw)
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
# Test utilities (only in TEST mode)
# ──────────────────────────────────────────────────────────────────────────────
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
        Simulate a call debit using the same policy as production billing.
        Returns 402 if balance is insufficient.
        """
        try:
            rate = per_minute_cost_cents(user)  # default 10¢/min
            charge_cents = compute_call_charge_cents(
                duration_seconds=body.duration_seconds,
                rate_per_min_cents=rate,
                round_mode="ceil",
            )
            new_balance = await apply_transaction(
                user_id=user.id,
                amount_cents=-charge_cents,
                kind="debit_call",
                description=f"Test debit: {int((body.duration_seconds+59)//60)} min @ ${rate/100:.2f}/min",
            )
            return {"debited_cents": charge_cents, "new_balance_cents": new_balance}
        except ValueError as e:  # "Insufficient balance"
            _err(status.HTTP_402_PAYMENT_REQUIRED, str(e))
