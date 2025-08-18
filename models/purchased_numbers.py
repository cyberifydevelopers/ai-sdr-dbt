from tortoise.models import Model
from tortoise import fields

class PurchasedNumber(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="purchased_numbers", on_delete=fields.CASCADE)
    phone_number = fields.CharField(max_length=20)
    friendly_name = fields.CharField(max_length=255, null=True)
    region = fields.CharField(max_length=255, null=True)
    postal_code = fields.CharField(max_length=20, null=True)
    iso_country = fields.CharField(max_length=10, null=True)
    last_month_payment = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    attached_assistant = fields.IntField(null=True)
    vapi_phone_uuid = fields.CharField(max_length=255, null=True, default=None)