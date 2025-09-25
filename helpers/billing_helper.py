# helpers/billing_helper.py
import os
from contextlib import asynccontextmanager
from tortoise.transactions import in_transaction
from models.auth import User
from models.billing import AccountTransaction

USD = "USD"

def cents(n: float) -> int:
    return int(round(n))

def per_minute_cost_cents(user: User) -> int:
    return user.per_minute_cents or 10

def compute_call_charge_cents(duration_seconds: float, rate_per_min_cents: int, round_mode: str = "ceil") -> int:
    """
    round_mode: 'ceil' to bill per started minute, 'exact' for per-second.
    """
    if duration_seconds is None:
        return 0
    if round_mode == "exact":
        per_sec = rate_per_min_cents / 60.0
        return cents(duration_seconds * per_sec)
    # default: ceil minute billing
    minutes = int((duration_seconds + 59) // 60)  # ceil
    return minutes * rate_per_min_cents

@asynccontextmanager
async def atomic():
    async with in_transaction() as conn:
        yield conn

async def apply_transaction(user_id: int, amount_cents: int, kind: str, description: str = "", 
                            currency: str = USD, stripe_pi: str = None, metadata: dict = None):
    """
    Positive amount_cents increases balance; negative decreases.
    """
    async with atomic():
        user = await User.get(id=user_id)
        new_balance = (user.balance_cents or 0) + amount_cents
        if new_balance < 0:
            raise ValueError("Insufficient balance")
        user.balance_cents = new_balance
        await user.save()
        await AccountTransaction.create(
            user=user, amount_cents=amount_cents, currency=currency, kind=kind,
            description=description or kind, stripe_payment_intent_id=stripe_pi, metadata=metadata
        )
        return user.balance_cents

async def ensure_stripe_customer(user: User, stripe):
    if user.stripe_customer_id:
        return user.stripe_customer_id
    cust = stripe.Customer.create(email=user.email, name=user.name or f"User {user.id}",
                                  metadata={"user_id": str(user.id)})
    user.stripe_customer_id = cust["id"]
    await user.save()
    return user.stripe_customer_id
