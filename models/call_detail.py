# # models/call_details.py  (your existing file)
# from tortoise import fields, models
# from tortoise.indexes import Index
# from models.auth import User
# from models.call_log import CallLog

# class CallDetail(models.Model):
#     id = fields.IntField(pk=True)

#     user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
#         "models.User", related_name="call_details", on_delete=fields.CASCADE
#     )
#     call_log: fields.ForeignKeyRelation[CallLog] = fields.ForeignKeyField(
#         "models.CallLog", related_name="call_detail", null=True, on_delete=fields.SET_NULL
#     )

#     call_id = fields.CharField(max_length=191, index=True, null=True)
#     assistant_id = fields.CharField(max_length=191, null=True)
#     phone_number_id = fields.CharField(max_length=191, null=True)

#     customer_number = fields.CharField(max_length=64, null=True, index=True)
#     customer_name = fields.CharField(max_length=191, null=True)

#     status = fields.CharField(max_length=64, null=True, index=True)
#     started_at = fields.DatetimeField(null=True)
#     ended_at = fields.DatetimeField(null=True)
#     duration = fields.IntField(null=True)
#     cost = fields.FloatField(null=True)
#     ended_reason = fields.CharField(max_length=128, null=True)
#     is_transferred = fields.BooleanField(null=True)
#     criteria_satisfied = fields.BooleanField(null=True)

#     success_evaluation_status = fields.CharField(max_length=64, null=True, index=True)

#     summary = fields.JSONField(null=True)
#     transcript = fields.JSONField(null=True)
#     analysis = fields.JSONField(null=True)
#     recording_url = fields.CharField(max_length=500, null=True)

#     vapi_created_at = fields.DatetimeField(null=True)
#     vapi_updated_at = fields.DatetimeField(null=True)

#     # NEW: interest classification
#     interest_status = fields.CharField(max_length=32, null=True, index=True)   # "interested" | "not-interested" | "could-not-say"
#     interest_confidence = fields.FloatField(null=True)                         # 0.0 - 1.0

#     created_at = fields.DatetimeField(auto_now_add=True)
#     updated_at = fields.DatetimeField(auto_now=True)
#     last_synced_at = fields.DatetimeField(null=True)

#     class Meta:
#         table = "call_details"
#         indexes = [
#             Index(fields=["user_id", "call_id"]),
#             Index(fields=["user_id", "status"]),
#             Index(fields=["user_id", "success_evaluation_status"]),
#             Index(fields=["user_id", "interest_status"]),   # helpful for filtering
#         ]




# models/call_details.py
from tortoise import fields, models
from tortoise.indexes import Index
from models.auth import User
from models.call_log import CallLog, ALLOWED_STATUSES, _normalize_status

class CallDetail(models.Model):
    id = fields.IntField(pk=True)

    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="call_details", on_delete=fields.CASCADE
    )
    call_log: fields.ForeignKeyRelation[CallLog] = fields.ForeignKeyField(
        "models.CallLog", related_name="call_detail", null=True, on_delete=fields.SET_NULL
    )

    # vapi refs
    call_id = fields.CharField(max_length=191, index=True, null=True)
    assistant_id = fields.CharField(max_length=191, null=True)
    phone_number_id = fields.CharField(max_length=191, null=True)

    # caller
    customer_number = fields.CharField(max_length=64, null=True, index=True)
    customer_name = fields.CharField(max_length=191, null=True)

    # unified status
    status = fields.CharField(max_length=50, null=True, index=True)

    started_at = fields.DatetimeField(null=True)
    ended_at = fields.DatetimeField(null=True)
    duration = fields.IntField(null=True)       # seconds (int ok here)
    cost = fields.FloatField(null=True)
    ended_reason = fields.CharField(max_length=128, null=True)
    is_transferred = fields.BooleanField(null=True)
    criteria_satisfied = fields.BooleanField(null=True)

    # blobs
    summary = fields.TextField(null=True)       # <— changed to TextField
    transcript = fields.TextField(null=True)    # already TextField
    analysis = fields.JSONField(null=True)      # keep JSON for structured data
    recording_url = fields.CharField(max_length=500, null=True)

    vapi_created_at = fields.DatetimeField(null=True)
    vapi_updated_at = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_synced_at = fields.DatetimeField(null=True)

    class Meta:
        table = "call_details"
        indexes = [
            Index(fields=["user_id", "call_id"]),
            Index(fields=["user_id", "status"]),
        ]

    async def save(self, *args, **kwargs):
        if self.status:
            norm = _normalize_status(self.status)
            if norm not in ALLOWED_STATUSES:
                raise ValueError(f"Invalid status '{self.status}'. Allowed: {sorted(ALLOWED_STATUSES)}")
            self.status = norm
        await super().save(*args, **kwargs)
