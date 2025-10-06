# # models/appointment.py
# from enum import Enum
# from tortoise import fields, models


# class AppointmentStatus(str, Enum):
#     SCHEDULED = "scheduled"
#     CANCELLED = "cancelled"
#     COMPLETED = "completed"


# class Appointment(models.Model):
#     """
#     Stores a single appointment with tz-aware start/end.
#     """
#     id = fields.UUIDField(pk=True)
#     title = fields.CharField(max_length=200)
#     notes = fields.TextField(null=True)
#     location = fields.CharField(max_length=200, null=True)

#     # Store phone as string (safer for leading zeros, country codes, +)
#     phone = fields.CharField(max_length=32)

#     timezone = fields.CharField(max_length=64)

#     # tz-aware datetimes
#     start_at = fields.DatetimeField()
#     end_at = fields.DatetimeField()

#     duration_minutes = fields.IntField()
#     status = fields.CharEnumField(AppointmentStatus, default=AppointmentStatus.SCHEDULED)

#     created_at = fields.DatetimeField(auto_now_add=True)
#     updated_at = fields.DatetimeField(auto_now=True)

#     class Meta:
#         table = "appointments"
#         indexes = ("start_at", "phone")

#     def __str__(self):
#         return f"{self.title} ({self.start_at.isoformat()})"






# models/appointment.py
from enum import Enum
from tortoise import fields, models

class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class Appointment(models.Model):
    id = fields.UUIDField(pk=True)

    # 🔐 multi-tenant
    user = fields.ForeignKeyField("models.User", related_name="appointments" , null=True)

    title = fields.CharField(max_length=200)
    notes = fields.TextField(null=True)
    location = fields.CharField(max_length=200, null=True)
    email = fields.CharField(max_length=320, null=True)  
    phone = fields.CharField(max_length=32)
    timezone = fields.CharField(max_length=64)

    start_at = fields.DatetimeField()   # tz-aware
    end_at = fields.DatetimeField()     # tz-aware

    duration_minutes = fields.IntField()
    status = fields.CharEnumField(AppointmentStatus)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "appointments"
        indexes = (("user_id", "start_at"), ("user_id", "phone"))
