from tortoise.models import Model
from tortoise import fields


class Lead(Model):
    id = fields.IntField(primary_key=True)

    first_name = fields.CharField(max_length=255)
    last_name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255)

    add_date = fields.DateField()
    salesforce_id = fields.CharField(max_length=255, null=True, index=True)

    mobile = fields.CharField(max_length=255)
    state = fields.CharField(max_length=255, null=True)
    timezone = fields.CharField(max_length=255, null=True)

    dnc = fields.BooleanField(default=False)
    submit_for_approval = fields.BooleanField(default=False)
    last_called_at = fields.DatetimeField(null=True)
    call_count = fields.IntField(null=True, default=0)

    other_data = fields.JSONField(null=True)

    file = fields.ForeignKeyField("models.File", related_name="leads", null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    origin = fields.CharField(max_length=32, default="CSV", index=True)
    origin_meta = fields.CharField(max_length=64, null=True)

    class Meta:
        table = "lead"
        indexes = (("file_id", "origin"),)

    def __str__(self) -> str:
        return f"<Lead #{self.id} {self.first_name} {self.last_name} ({self.email})>"
