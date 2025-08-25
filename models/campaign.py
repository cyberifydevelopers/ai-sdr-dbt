# models/campaign.py
from enum import Enum
from tortoise import fields, models


class CampaignSelectionMode(str, Enum):
    ALL = "ALL"
    ONLY = "ONLY"     # include only the provided lead IDs
    SKIP = "SKIP"     # include all except the provided lead IDs


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class Campaign(models.Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="campaigns")
    name = fields.CharField(max_length=255)

    # selection + source
    file = fields.ForeignKeyField("models.File", related_name="campaigns")
    selection_mode = fields.CharEnumField(CampaignSelectionMode, default=CampaignSelectionMode.ALL)
    include_lead_ids = fields.JSONField(null=True)   # list[int] when mode=ONLY
    exclude_lead_ids = fields.JSONField(null=True)   # list[int] when mode=SKIP

    # assistant to place calls
    assistant = fields.ForeignKeyField("models.Assistant", related_name="campaigns")

    # scheduling window
    timezone = fields.CharField(max_length=64, default="America/Los_Angeles")
    days_of_week = fields.JSONField(null=True)   # [0..6] 0=Mon
    daily_start = fields.CharField(max_length=5, null=True)  # "09:00"
    daily_end = fields.CharField(max_length=5, null=True)    # "18:00"
    start_at = fields.DatetimeField(null=True)
    end_at = fields.DatetimeField(null=True)

    # pacing
    calls_per_minute = fields.IntField(default=10)
    parallel_calls = fields.IntField(default=2)

    # retry
    retry_on_busy = fields.BooleanField(default=True)
    busy_retry_delay_minutes = fields.IntField(default=15)
    max_attempts = fields.IntField(default=3)

    # states
    status = fields.CharEnumField(CampaignStatus, default=CampaignStatus.DRAFT)
    last_tick_at = fields.DatetimeField(null=True)

    # optional: store a generated .ics
    calendar_ics = fields.TextField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class CampaignLeadProgress(models.Model):
    id = fields.IntField(pk=True)
    campaign = fields.ForeignKeyField("models.Campaign", related_name="lead_progress")
    lead = fields.ForeignKeyField("models.Lead", related_name="campaign_progress")

    # status machine: pending → calling → completed | failed | retry_scheduled | skipped
    status = fields.CharField(max_length=32, default="pending")
    attempt_count = fields.IntField(default=0)
    last_attempt_at = fields.DatetimeField(null=True)
    next_attempt_at = fields.DatetimeField(null=True)

    last_call_id = fields.CharField(max_length=200, null=True)
    last_ended_reason = fields.CharField(max_length=200, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (("campaign", "lead"),)
