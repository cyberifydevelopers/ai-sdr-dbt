from tortoise.models import Model
from tortoise import fields

class CallLog(Model):
    id = fields.IntField(primary_key=True)
    lead_id=fields.IntField(max_length=255 , null=True)
    user=fields.ForeignKeyField("models.User", related_name="call_log") 
    call_started_at = fields.DatetimeField(null=True)
    customer_number = fields.CharField(max_length=100 , null=True)
    customer_name= fields.CharField(max_length=100, null =True)
    call_id =  fields.CharField(max_length=1000, null=True)
    # after call
    cost =fields.DecimalField(max_digits = 10 , decimal_places = 2,null=True)
    call_ended_at = fields.DatetimeField(null=True)
    call_ended_reason =  fields.CharField(max_length=100 , null=True)
    call_duration = fields.FloatField(null=True)  
    is_transferred  = fields.BooleanField(default = False, null=True) 
    status = fields.CharField(max_length=100 , null=True)  
    criteria_satisfied = fields.BooleanField(default = False ,null=True)  

