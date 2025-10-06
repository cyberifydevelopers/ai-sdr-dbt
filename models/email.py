# models/email.py
from tortoise import fields, models

class EmailCredential(models.Model):
    """
    Per-user SMTP (or API) credentials.
    If you prefer SendGrid/Resend/etc, keep provider + token; for raw SMTP, keep host/port/username/password.
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="email_credentials")

    provider = fields.CharField(max_length=64, null=True)  # "smtp" | "sendgrid" | "resend" | etc.
    api_key = fields.CharField(max_length=255, null=True)

    smtp_host = fields.CharField(max_length=255, null=True)
    smtp_port = fields.IntField(null=True)
    smtp_username = fields.CharField(max_length=255, null=True)
    smtp_password = fields.CharField(max_length=255, null=True)
    smtp_use_tls = fields.BooleanField(default=True)

    from_email = fields.CharField(max_length=320, null=True)  # default From

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "email_credentials"
        indexes = (("user_id", "provider"),)


class EmailJob(models.Model):
    """
    Mirrors MessageJob (SMS) — tracks bulk email runs and daemon ticks.
    """
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="email_jobs")
    assistant = fields.ForeignKeyField("models.Assistant", related_name="email_jobs", null=True)

    from_email = fields.CharField(max_length=320, null=True)
    subject_template = fields.CharField(max_length=255, null=True)

    status = fields.CharField(max_length=24, default="running")  # running|completed|failed|canceled
    total = fields.IntField(default=0)
    sent = fields.IntField(default=0)
    failed = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "email_jobs"


class EmailRecord(models.Model):
    """
    Each email attempt/result with full audit.
    """
    id = fields.IntField(pk=True)

    job = fields.ForeignKeyField("models.EmailJob", related_name="emails", null=True)
    user = fields.ForeignKeyField("models.User", related_name="email_records")
    assistant = fields.ForeignKeyField("models.Assistant", related_name="email_records", null=True)
    appointment = fields.ForeignKeyField("models.Appointment", related_name="email_records", null=True)

    to_email = fields.CharField(max_length=320)
    from_email = fields.CharField(max_length=320, null=True)
    subject = fields.CharField(max_length=255, null=True)
    body = fields.TextField()

    provider_message_id = fields.CharField(max_length=255, null=True)  # Message-Id / API id
    success = fields.BooleanField(default=False)
    error = fields.TextField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "email_records"
        indexes = (("user_id", "created_at"), ("job_id", "created_at"))
