# from tortoise.models import Model
# from tortoise import fields

# class CallLog(Model):
#     id = fields.IntField(primary_key=True)
#     lead_id=fields.IntField(max_length=255 , null=True)
#     user=fields.ForeignKeyField("models.User", related_name="call_log") 
#     call_started_at = fields.DatetimeField(null=True)
#     customer_number = fields.CharField(max_length=100 , null=True)
#     customer_name= fields.CharField(max_length=100, null =True)
#     call_id =  fields.CharField(max_length=1000, null=True)
#     # after call
#     cost =fields.DecimalField(max_digits = 10 , decimal_places = 2,null=True)
#     call_ended_at = fields.DatetimeField(null=True)
#     call_ended_reason =  fields.CharField(max_length=100 , null=True)
#     call_duration = fields.FloatField(null=True)  
#     is_transferred  = fields.BooleanField(default = False, null=True) 
#     status = fields.CharField(max_length=100 , null=True)  
#     criteria_satisfied = fields.BooleanField(default = False ,null=True)  






# models/call_log.py
from tortoise.models import Model
from tortoise import fields

ALLOWED_STATUSES = {
    "Booked",
    "Follow-up Needed",
    "Not Interested",
    "No Answer",
    "Voice Mail",
    "Failed to Call",
    "Transferred to Human",
}

def _normalize_status(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    norm_map = {
        "booked": "Booked",
        "follow-up needed": "Follow-up Needed",
        "follow up needed": "Follow-up Needed",
        "not interested": "Not Interested",
        "no answer": "No Answer",
        "voice mail": "Voice Mail",
        "voicemail": "Voice Mail",
        "failed to call": "Failed to Call",
        "transferred to human": "Transferred to Human",
        "transferred": "Transferred to Human",
    }
    return norm_map.get(v, None)

class CallLog(Model):
    id = fields.IntField(primary_key=True)
    lead_id = fields.IntField(null=True)
    user = fields.ForeignKeyField("models.User", related_name="call_log")

    # timings
    call_started_at = fields.DatetimeField(null=True)
    call_ended_at = fields.DatetimeField(null=True)
    call_duration = fields.FloatField(null=True)  # seconds

    # caller info
    customer_number = fields.CharField(max_length=100, null=True)
    customer_name = fields.CharField(max_length=100, null=True)

    # vapi ids
    call_id = fields.CharField(max_length=1000, null=True)

    # costs/reasons
    cost = fields.DecimalField(max_digits=10, decimal_places=2, null=True)
    call_ended_reason = fields.CharField(max_length=100, null=True)

    # transfer + criteria
    is_transferred = fields.BooleanField(default=False, null=True)
    criteria_satisfied = fields.BooleanField(default=False, null=True)

    # unified status
    status = fields.CharField(max_length=50, null=True, index=True)

    # blobs/links
    summary = fields.TextField(null=True)         # string-friendly
    transcript = fields.TextField(null=True)      # string-friendly
    analysis = fields.JSONField(null=True)        # can be dict/list
    recording_url = fields.CharField(max_length=500, null=True)

    async def save(self, *args, **kwargs):
        if self.status:
            norm = _normalize_status(self.status)
            if norm not in ALLOWED_STATUSES:
                raise ValueError(f"Invalid status '{self.status}'. Allowed: {sorted(ALLOWED_STATUSES)}")
            self.status = norm
        await super().save(*args, **kwargs)
