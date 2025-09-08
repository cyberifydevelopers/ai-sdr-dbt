
from tortoise import fields, models
from tortoise.models import Model

from models.auth import User
class ChatThread(Model):
    """
    One thread per (user, admin) pair.
    """
    id = fields.IntField(pk=True)
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="chat_threads_as_user", on_delete=fields.CASCADE
    )
    admin: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="chat_threads_as_admin", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "chat_thread"
        unique_together = (("user", "admin"),)
        indexes = (("user_id",), ("admin_id",),)


class ChatMessage(Model):
    """
    Messages inside a thread.
    - read_by_user / read_by_admin track per-side unread state.
    - attachments is a JSON list of string URLs (optional).
    """
    id = fields.IntField(pk=True)
    thread: fields.ForeignKeyRelation[ChatThread] = fields.ForeignKeyField(
        "models.ChatThread", related_name="messages", on_delete=fields.CASCADE
    )
    sender: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="chat_messages_sent", on_delete=fields.CASCADE
    )
    text = fields.TextField(null=True)
    attachments = fields.JSONField(null=True)  # list[str]
    read_by_user = fields.BooleanField(default=False)
    read_by_admin = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "chat_message"
        indexes = (("thread_id", "created_at"),)
