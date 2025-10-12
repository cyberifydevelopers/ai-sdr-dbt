# models/billing.py
from tortoise import fields, models


class Payment(models.Model):
    """
    Source of truth for successful Stripe payments.
    Amounts are in the smallest currency unit (e.g., cents for USD).
    """
    id = fields.IntField(pk=True)

    # Who paid
    user = fields.ForeignKeyField(
        "models.User",
        related_name="payments",
        on_delete=fields.CASCADE,
        index=True,
    )

    # Gross amount the customer paid (from Checkout/PI)
    amount_cents = fields.IntField()

    # Stripe fee & net credited to your Stripe balance (from balance_transaction)
    fee_cents = fields.IntField(default=0)
    net_cents = fields.IntField(default=0)

    currency = fields.CharField(max_length=8, default="USD", index=True)
    status = fields.CharField(max_length=32, default="succeeded", index=True)  # e.g. succeeded, processing, etc.

    # Stripe references
    stripe_payment_intent_id = fields.CharField(max_length=128, unique=True)
    stripe_checkout_session_id = fields.CharField(max_length=128, null=True, index=True)
    stripe_balance_txn_id = fields.CharField(max_length=128, null=True, index=True)

    metadata = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "payments"
        ordering = ["-id"]


class Notification(models.Model):
    """
    Admin/user notifications (e.g. payment_received, pricing_updated).
    """
    id = fields.IntField(pk=True)
    kind = fields.CharField(max_length=32, index=True)   # "payment_received", "pricing_updated", ...
    title = fields.CharField(max_length=128)
    body = fields.CharField(max_length=512, null=True)
    user = fields.ForeignKeyField("models.User", null=True, on_delete=fields.SET_NULL, index=True)
    data = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "notifications"
        ordering = ["-id"]


class AccountTransaction(models.Model):
    """
    Wallet-style ledger.
    - Credits are positive amounts (e.g., top-up net after fees).
    - Debits are negative amounts (e.g., usage charges).
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="transactions",
        on_delete=fields.CASCADE,
        index=True,
    )
    amount_cents = fields.IntField()  # credits > 0, debits < 0
    currency = fields.CharField(max_length=8, default="USD", index=True)
    kind = fields.CharField(max_length=32, index=True)   # e.g., "topup_net", "debit_call_fixed", "debit_text_fixed"
    description = fields.CharField(max_length=255, null=True)
    stripe_payment_intent_id = fields.CharField(max_length=128, null=True, index=True)
    metadata = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "account_transactions"
        ordering = ["-id"]


class PricingSettings(models.Model):
    """
    Admin-set global pricing (latest row is active).
    - Calls: per-second price in MILLICENTS (1 cent = 1000 millicents).
      Example: $0.00125/sec = 0.125¢/sec = 125 millicents/sec.
    - Texts: per-message price in CENTS.
    """
    id = fields.IntField(pk=True)
    currency = fields.CharField(max_length=8, default="USD", index=True)

    # Per-second (integer, millicents): 125 = 0.125¢/sec = $0.00125/sec
    call_millicents_per_second = fields.IntField(default=0)

    # Per-message (integer, cents): 2 = $0.02/msg
    text_cents_per_message = fields.IntField(default=0)

    updated_by_user_id = fields.IntField(null=True, index=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pricing_settings"
        ordering = ["-id"]
