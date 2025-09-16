# models/facebook.py
from tortoise import fields, models
from typing import Optional
from datetime import datetime

class FacebookIntegration(models.Model):
    """
    Stores the long-lived user access token per platform user.
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="facebook_integrations")
    fb_user_id = fields.CharField(max_length=64, index=True)
    user_access_token = fields.TextField()
    token_expires_at = fields.DatetimeField(null=True)  # optional; FB may not always return
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "facebook_integrations"

class FacebookPage(models.Model):
    """
    Stores connected Pages and their page access tokens (needed to read leads & subscribe webhooks).
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="facebook_pages")
    page_id = fields.CharField(max_length=64, index=True)
    name = fields.CharField(max_length=255, null=True)
    page_access_token = fields.TextField()  # derived from user token via /me/accounts
    subscribed = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "facebook_pages"
