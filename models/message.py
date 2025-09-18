from tortoise import fields
from tortoise.models import Model


class MessageJob(Model):
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="message_jobs")
    assistant = fields.ForeignKeyField("models.Assistant", related_name="message_jobs", null=True)

    from_number = fields.CharField(max_length=32, null=True)

    status = fields.CharField(max_length=24, default="running")  # running|completed|failed
    total = fields.IntField(default=0)
    sent = fields.IntField(default=0)
    failed = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "message_jobs"


class MessageRecord(Model):
    id = fields.IntField(pk=True)
    job = fields.ForeignKeyField("models.MessageJob", related_name="messages")
    user = fields.ForeignKeyField("models.User", related_name="message_records")
    assistant = fields.ForeignKeyField("models.Assistant", related_name="message_records", null=True)
    appointment = fields.ForeignKeyField("models.Appointment", related_name="message_records", null=True)

    to_number = fields.CharField(max_length=32)
    from_number = fields.CharField(max_length=32)
    body = fields.TextField()
    sid = fields.CharField(max_length=255, null=True)
    success = fields.BooleanField(default=False)
    error = fields.TextField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "message_records"
        indexes = (("user_id", "created_at"), ("job_id", "created_at"))

