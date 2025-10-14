import uuid
from tortoise import fields
from tortoise.models import Model
from datetime import datetime


class User(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255)
    email_verified = fields.BooleanField(default=False)
    password = fields.CharField(max_length=255)
    role = fields.CharField(max_length=255, default='user')
    codes = fields.ReverseRelation['Code']
    profile_photo = fields.CharField(max_length=255, null=True) 
    twilio_account_sid = fields.CharField(max_length=64, null=True)
    twilio_auth_token = fields.CharField(max_length=64, null=True)
    webhook_token = fields.CharField(max_length=64, unique=True, default=lambda: uuid.uuid4().hex)
    balance_cents = fields.IntField(default=0)              
    bonus_cents = fields.IntField(default=0)                  
    currency = fields.CharField(max_length=8, default="USD")
    stripe_customer_id = fields.CharField(max_length=64, null=True)
    per_minute_cents = fields.IntField(default=10)       

    transactions = fields.ReverseRelation['AccountTransaction']
    consent_to_call = fields.BooleanField(default=False, description="User asserts they have consent to call uploaded leads")
    consent_note = fields.TextField(null=True, description="Optional context/description for consent")
    consent_updated_at = fields.DatetimeField(null=True)
    
class Code(Model):
    __tablename__ = 'codes'

    id = fields.IntField(primary_key=True, index=True)
    type = fields.CharField(max_length=255, nullable=False)
    value = fields.TextField(nullable=False)
    expires_at = fields.DateField(nullable=False)
    created_at = fields.DatetimeField(default=datetime.utcnow, nullable=False)
    updated_at = fields.DatetimeField(default=datetime.utcnow, on_update=datetime.utcnow, nullable=False)
    user = fields.ForeignKeyField('models.User', related_name='codes', on_delete=fields.CASCADE)
    class Meta:
        table = 'codes'