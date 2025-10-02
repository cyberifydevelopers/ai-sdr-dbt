from __future__ import annotations
from typing import Optional, Any, Dict
from tortoise import fields, models
from tortoise.indexes import Index
from models.auth import User
from models.call_log import CallLog  # your existing model used by admin routes


class CallDetail(models.Model):
    """
    Per-user VAPI-enriched call snapshot.
    Links to the owning user and (optionally) the local CallLog row for mapping.
    """
    id = fields.IntField(pk=True)

    # Ownership
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="call_details", on_delete=fields.CASCADE
    )

    # Optional link to your main CallLog table (helps correlate)
    call_log: fields.ForeignKeyRelation[CallLog] = fields.ForeignKeyField(
        "models.CallLog", related_name="call_detail", null=True, on_delete=fields.SET_NULL
    )

    # VAPI / telephony identifiers
    call_id = fields.CharField(max_length=191, index=True, null=True)
    assistant_id = fields.CharField(max_length=191, null=True)
    phone_number_id = fields.CharField(max_length=191, null=True)

    # Parties
    customer_number = fields.CharField(max_length=64, null=True, index=True)
    customer_name = fields.CharField(max_length=191, null=True)

    # Status/Timing/Cost
    status = fields.CharField(max_length=64, null=True, index=True)
    started_at = fields.DatetimeField(null=True)
    ended_at = fields.DatetimeField(null=True)
    duration = fields.IntField(null=True)  # seconds
    cost = fields.FloatField(null=True)
    ended_reason = fields.CharField(max_length=128, null=True)
    is_transferred = fields.BooleanField(null=True)
    criteria_satisfied = fields.BooleanField(null=True)

    # **Extra**: success evaluation coming from VAPI
    success_evaluation_status = fields.CharField(max_length=64, null=True, index=True)

    # Rich data from VAPI (JSON)
    summary = fields.JSONField(null=True)
    transcript = fields.JSONField(null=True)
    analysis = fields.JSONField(null=True)
    recording_url = fields.CharField(max_length=500, null=True)

    # VAPI timestamps
    vapi_created_at = fields.DatetimeField(null=True)
    vapi_updated_at = fields.DatetimeField(null=True)

    # Bookkeeping
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_synced_at = fields.DatetimeField(null=True)

    class Meta:
        table = "call_details"
        indexes = [
            Index(fields=["user_id", "call_id"]),
            Index(fields=["user_id", "status"]),
            Index(fields=["user_id", "success_evaluation_status"]),
        ]
