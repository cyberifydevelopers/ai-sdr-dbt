from tortoise.models import Model
from tortoise import fields

class Documents(Model):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField("models.User")
    file_name = fields.CharField(max_length=255)
    vapi_file_id = fields.CharField(max_length=255 , null = True)
