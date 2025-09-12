from tortoise import fields, models
from enum import Enum


class SubmissionStatus(str, Enum):
    UNBOOKED = "unbooked"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class FormSubmission(models.Model):
    """
    Stores raw form submissions + structured fields if available
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="submissions" , null=True)
    first_name = fields.CharField(max_length=100, null=True)
    last_name = fields.CharField(max_length=100, null=True)
    email = fields.CharField(max_length=255, null=True, index=True)
    phone = fields.CharField(max_length=50, null=True, index=True)

    booking_time = fields.DatetimeField(null=True)
    additional_details = fields.JSONField(null=True)

    # Store raw full payload (flexible, for AI parsing later)
    raw_data = fields.JSONField(null=True)

    status = fields.CharEnumField(SubmissionStatus, default=SubmissionStatus.UNBOOKED)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "form_submissions"

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''} ({self.status})"
