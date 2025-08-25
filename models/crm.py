# models/crm.py
from tortoise import fields, models
from typing import Optional


class IntegrationAccount(models.Model):
    """
    A connected CRM account for a given user.
    One user can have 0..N accounts across providers.
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="integration_accounts")
    crm = fields.CharField(max_length=32)  # "hubspot"|"salesforce"|"zoho"|"pipedrive"|"close"

    # OAuth tokens (Close uses API key in access_token)
    access_token = fields.TextField(null=True)
    refresh_token = fields.TextField(null=True)
    expires_at = fields.DatetimeField(null=True)  # when access_token expires (UTC)

    # Provider-specific metadata
    instance_url = fields.CharField(max_length=255, null=True)      # e.g., Salesforce base URL
    scope = fields.CharField(max_length=512, null=True)             # space/comma separated
    external_account_id = fields.CharField(max_length=128, null=True)   # e.g., HubSpot portalId, Pipedrive company id
    external_account_name = fields.CharField(max_length=255, null=True) # friendly org name if available
    metadata = fields.JSONField(null=True)                          # anything else

    # UI niceties
    label = fields.CharField(max_length=255, null=True)             # user-provided label, optional
    is_active = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "integration_accounts"
        unique_together = (("user", "crm"),)  # 1 account per CRM per user (simplest). Remove if you want many.


class IntegrationOAuthState(models.Model):
    """
    Temporary state row for OAuth 'state' param so callbacks can identify user.
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="oauth_states")
    crm = fields.CharField(max_length=32)
    state = fields.CharField(max_length=128, unique=True)
    redirect_to = fields.CharField(max_length=512, null=True)  # front-end page to return to
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "integration_oauth_state"


class LeadExternalRef(models.Model):
    """
    Mapping of our Lead → external CRM Contact/Lead ID.
    Useful for idempotent upserts and deep links.
    """
    id = fields.IntField(pk=True)
    lead = fields.ForeignKeyField("models.Lead", related_name="external_refs")
    crm = fields.CharField(max_length=32)
    external_id = fields.CharField(max_length=128)
    external_url = fields.CharField(max_length=512, null=True)
    last_synced_at = fields.DatetimeField(null=True)
    last_error = fields.TextField(null=True)
    payload_snapshot = fields.JSONField(null=True)

    class Meta:
        table = "lead_external_refs"
        unique_together = (("lead", "crm"),)


class SyncJob(models.Model):
    """
    Optional: if you batch-push leads to CRMs, this tracks the job.
    """
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="crm_sync_jobs")
    crm = fields.CharField(max_length=32)
    scope = fields.CharField(max_length=32)        # "file"|"campaign"|"leads"
    scope_ref = fields.CharField(max_length=64, null=True)
    status = fields.CharField(max_length=16, default="queued")  # queued|running|done|failed
    total = fields.IntField(default=0)
    success = fields.IntField(default=0)
    failed = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "crm_sync_jobs"


class SyncItem(models.Model):
    id = fields.IntField(pk=True)
    job = fields.ForeignKeyField("models.SyncJob", related_name="items")
    lead = fields.ForeignKeyField("models.Lead", related_name="crm_sync_items")
    status = fields.CharField(max_length=16, default="queued")  # queued|success|failed
    error = fields.TextField(null=True)

    class Meta:
        table = "crm_sync_items"
