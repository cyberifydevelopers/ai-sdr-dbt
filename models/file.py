from tortoise import fields
from tortoise.models import Model
import uuid

def generate_alphanumeric_id(numeric_id: int) -> str:
    unique_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(numeric_id))
    return f"ID-{unique_uuid.hex[:5]}"  

class File(Model):
    id = fields.IntField(primary_key=True)
    alphanumeric_id = fields.CharField(8, unique=True, null=True)  
    name = fields.CharField(255)
    user = fields.ForeignKeyField("models.User")
    leads: fields.ReverseRelation['Lead']
    url = fields.TextField(null=True)
    sync_enable = fields.BooleanField(default=False, null=True)
    sync_frequency = fields.IntField(null=True)
    is_syncing = fields.BooleanField(default=False, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    async def save(self, *args, **kwargs):
        is_new = self._saved_in_db is False

        await super().save(*args, **kwargs)

        if is_new and not self.alphanumeric_id:
            self.alphanumeric_id = generate_alphanumeric_id(self.id)
            await super().save(update_fields=["alphanumeric_id"])
