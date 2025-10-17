from enum import Enum
from tortoise import fields, models
from tortoise.indexes import Index
class AppointmentOutcome(str, Enum):
    BOOKED = "Booked"
    FOLLOW_UP_NEEDED = "Follow-up Needed"

class Appointment(models.Model):
    id = fields.UUIDField(pk=True)

    user = fields.ForeignKeyField("models.User", related_name="appointments", on_delete=fields.CASCADE)

    assistant_id = fields.CharField(max_length=191, null=True)         
    source_call_id = fields.CharField(max_length=191, null=True, index=True)
    source_transcript_id = fields.CharField(max_length=191, null=True)

    title = fields.CharField(max_length=200)
    notes = fields.TextField(null=True)

    phone = fields.CharField(max_length=32)                            
    location = fields.CharField(max_length=200, null=True)
    timezone = fields.CharField(max_length=64)                        

    start_at = fields.DatetimeField()                                  
    end_at = fields.DatetimeField(null=True)                                    

    
    status = fields.CharEnumField(AppointmentOutcome)

  
    extraction_version = fields.CharField(max_length=32, null=True)
    extraction_confidence = fields.FloatField(null=True)
    extraction_raw = fields.JSONField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "appointments"
        indexes = [
            Index(fields=["user_id", "start_at"]),
            Index(fields=["user_id", "phone"]),
            Index(fields=["user_id", "source_call_id"]),
        ]
        unique_together = (("user_id", "source_call_id"),) 
