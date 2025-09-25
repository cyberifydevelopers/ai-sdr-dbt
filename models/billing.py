# models/billing.py
from tortoise import fields, models

class AccountTransaction(models.Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="transactions", on_delete=fields.CASCADE)
    # signed amount: positive for top-ups/refunds; negative for debits (e.g., calls)
    amount_cents = fields.IntField()
    currency = fields.CharField(max_length=8, default="USD")
    # e.g., "topup", "debit_call", "refund", "adjust"
    kind = fields.CharField(max_length=32)
    description = fields.CharField(max_length=255, null=True)
    stripe_payment_intent_id = fields.CharField(max_length=128, null=True)
    metadata = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "account_transactions"
        ordering = ["-id"]
