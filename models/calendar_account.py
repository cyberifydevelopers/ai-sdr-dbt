# from tortoise import fields, models

# class CalendarAccount(models.Model):
#     id = fields.UUIDField(pk=True)
#     user = fields.ForeignKeyField("models.User", related_name="calendar_accounts")

#     # Supported providers in this app: 'google' | 'calcom' | 'calendly'
#     provider = fields.CharField(max_length=32)

#     # Provider's account identifier (e.g., Google email, Cal.com user id/handle, Calendly user URI)
#     external_account_id = fields.CharField(max_length=128)
#     external_email = fields.CharField(max_length=255, null=True)

#     access_token = fields.TextField()
#     refresh_token = fields.TextField(null=True)
#     scope = fields.TextField(null=True)
#     expires_at = fields.DatetimeField(null=True)

#     primary_calendar_id = fields.CharField(max_length=128, null=True)

#     created_at = fields.DatetimeField(auto_now_add=True)
#     updated_at = fields.DatetimeField(auto_now=True)

#     class Meta:
#         table = "calendar_accounts"
#         unique_together = (("user_id", "provider", "external_account_id"),)
#         indexes = (
#             ("user_id", "provider"),
#             ("provider", "external_account_id"),
#         )
from tortoise import fields, models

class CalendarAccount(models.Model):
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="calendar_accounts")

    # Supported providers: 'google' | 'calcom' | 'calendly'
    provider = fields.CharField(max_length=32)

    # Provider's account identifier:
    # - Google: email
    # - Cal.com: user id/handle
    # - Calendly: user URI (e.g., https://api.calendly.com/users/XXXX)
    external_account_id = fields.CharField(max_length=512)

    # Convenience (display / filtering)
    external_email = fields.CharField(max_length=320, null=True)

    # Some providers expose an organization URI (Calendly),
    # keep it for faster account resolution in webhooks.
    external_org_id = fields.CharField(max_length=512, null=True)

    # Auth
    access_token = fields.TextField()
    refresh_token = fields.TextField(null=True)
    scope = fields.TextField(null=True)
    expires_at = fields.DatetimeField(null=True)

    # Default/primary calendar if applicable (Google)
    primary_calendar_id = fields.CharField(max_length=512, null=True)

    # Webhook management (shared schema for Calendly & Cal.com)
    # - Calendly: webhook_subscriptions -> id (uuid) + signing_key (returned by API)
    # - Cal.com: store our generated secret here; webhook id if API returns one
    webhook_id = fields.CharField(max_length=256, null=True)
    webhook_signing_key = fields.CharField(max_length=512, null=True)

    # Version pinning (useful for Cal.com v2 headers, etc.)
    api_version = fields.CharField(max_length=64, null=True)

    # Flexible bag for provider-specific extras
    metadata = fields.JSONField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "calendar_accounts"
        # ek hi user ke andar provider+external_account ka unique pair
        unique_together = (("user_id", "provider", "external_account_id"),)
        indexes = (
            ("user_id", "provider"),
            ("provider", "external_account_id"),
            ("provider", "external_org_id"),
            ("provider", "webhook_id"),
        )
