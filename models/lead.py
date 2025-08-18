from tortoise.models import Model
from tortoise import fields

class Lead(Model):
    id = fields.IntField(primary_key=True)
    first_name = fields.CharField(max_length=255)
    last_name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255)
    add_date = fields.DateField()
    salesforce_id = fields.CharField(max_length=255, null=True) 
    mobile = fields.CharField(max_length=255)
    state = fields.CharField(max_length=255 , null = True)
    timezone = fields.CharField(max_length = 255 , null = True) 
    dnc = fields.BooleanField(default=False)
    submit_for_approval = fields.BooleanField(default=False) 
 
    other_data = fields.JSONField(null=True) #null ture
    file = fields.ForeignKeyField("models.File" , related_name="leads", null = True)
    last_called_at = fields.DatetimeField(null = True)  
    call_count = fields.IntField(null = True , default = 0) 
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    