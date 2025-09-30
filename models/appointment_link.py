# models/appointment_link.py
from tortoise import fields, models

class AppointmentExternalLink(models.Model):
    id = fields.UUIDField(pk=True)
    appointment = fields.ForeignKeyField("models.Appointment", related_name="external_links")
    account = fields.ForeignKeyField("models.CalendarAccount", related_name="appointment_links")
    provider = fields.CharField(max_length=32)
    external_event_id = fields.CharField(max_length=128)
    external_calendar_id = fields.CharField(max_length=128, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "appointment_external_links"
        unique_together = (("provider", "external_event_id"),)
        indexes = (("account_id", "external_event_id"),)
