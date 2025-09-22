from tortoise import fields, models

class CallBlocklist(models.Model):
    id = fields.IntField(pk=True)
    phone_number = fields.CharField(32, index=True)
    reason = fields.CharField(255, null=True)
    blocked_until = fields.DatetimeField(null=True)
    hit_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "call_blocklist"
        unique_together = (("phone_number",),)
