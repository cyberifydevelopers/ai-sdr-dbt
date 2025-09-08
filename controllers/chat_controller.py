# controllers/chat_controller.py
from typing import List, Optional, Tuple, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from tortoise.transactions import in_transaction
from tortoise.exceptions import DoesNotExist
from fastapi import APIRouter
from helpers.token_helper import get_current_user
from helpers.get_user_admin import get_user_admin
from models.auth import User
from models.chat_models import ChatThread, ChatMessage  # <-- import the models you just created


router = APIRouter()
__all__ = ["router"]  # optional, but helpful

@router.get("/health")  # temporary smoke test
async def health():
    return {"ok": True}

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    text: Optional[str] = Field(None, description="Message text")
    attachments: Optional[List[str]] = Field(default=None, description="List of attachment URLs")

    @classmethod
    def validate_nonempty(cls, v: "SendMessageRequest"):
        if (not v.text or not v.text.strip()) and not v.attachments:
            raise ValueError("Either 'text' or 'attachments' is required")
        return v


class AdminSendMessageRequest(SendMessageRequest):
    user_id: str = Field(..., description="Recipient user id")


class MarkReadRequest(BaseModel):
    user_id: Optional[str] = Field(
        None, description="(Admin only) user id to mark read for; users omit this"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_create_thread(user: User, admin: User) -> ChatThread:
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if thread:
        return thread
    async with in_transaction():
        thread = await ChatThread.create(user=user, admin=admin)
    return thread


def _read_flags_for(sender: User, user: User, admin: User) -> Tuple[bool, bool]:
    """
    Return (read_by_user, read_by_admin) initial flags based on who is sending.
    Sender always has their own side marked read=true.
    """
    if sender.id == user.id:
        return True, False   # user sends → user read, admin unread
    else:
        return False, True   # admin sends → admin read, user unread


# ─────────────────────────────────────────────────────────────────────────────
# User endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat/send")
async def user_send_message(
    body: SendMessageRequest,
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
):
    # validate content
    SendMessageRequest.validate_nonempty(body)

    thread = await _get_or_create_thread(user=user, admin=admin)
    read_by_user, read_by_admin = _read_flags_for(sender=user, user=user, admin=admin)

    msg = await ChatMessage.create(
        thread=thread,
        sender=user,
        text=(body.text or "").strip() or None,
        attachments=body.attachments,
        read_by_user=read_by_user,
        read_by_admin=read_by_admin,
    )

    return {
        "success": True,
        "thread_id": thread.id,
        "message": {
            "id": msg.id,
            "text": msg.text,
            "attachments": msg.attachments or [],
            "created_at": msg.created_at,
            "sender_id": user.id,
        },
    }


@router.get("/chat/my-thread")
async def user_get_my_thread(
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
):
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if not thread:
        # lazily create on demand so UI can open immediately
        thread = await _get_or_create_thread(user=user, admin=admin)
    return {"thread_id": thread.id, "admin_id": admin.id}


@router.get("/chat/my/messages")
async def user_list_my_messages(
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    order: str = Query("asc", regex="^(asc|desc)$"),
):
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if not thread:
        return {"messages": [], "thread_id": None}

    qs = ChatMessage.filter(thread=thread)
    qs = qs.order_by("created_at" if order == "asc" else "-created_at")
    msgs = await qs.offset(skip).limit(limit)
    return {
        "thread_id": thread.id,
        "messages": [
            {
                "id": m.id,
                "text": m.text,
                "attachments": m.attachments or [],
                "created_at": m.created_at,
                "sender_id": m.sender_id,
                "read_by_user": m.read_by_user,
                "read_by_admin": m.read_by_admin,
            }
            for m in msgs
        ],
    }


@router.post("/chat/my/mark-read")
async def user_mark_read(
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
):
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if not thread:
        return {"success": True, "updated": 0}

    updated = await ChatMessage.filter(
        thread=thread, read_by_user=False
    ).exclude(sender=user).update(read_by_user=True)
    return {"success": True, "updated": updated}


@router.get("/chat/my/unread-count")
async def user_unread_count(
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
):
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if not thread:
        return {"count": 0}
    count = await ChatMessage.filter(thread=thread, read_by_user=False).exclude(sender=user).count()
    return {"count": count}


# NEW: User notifications (messages + total)
@router.get("/chat/my/notifications")
async def user_notifications(
    user: Annotated[User, Depends(get_current_user)],
    admin: Annotated[User, Depends(get_user_admin)],
    limit: int = Query(50, ge=1, le=200),
):
    """
    Return unread messages for this user (from their admin) + total count.
    """
    thread = await ChatThread.get_or_none(user=user, admin=admin)
    if not thread:
        return {"count": 0, "messages": []}

    qs = ChatMessage.filter(thread=thread, read_by_user=False).exclude(sender=user).order_by("-created_at")
    total = await qs.count()
    msgs = await qs.limit(limit).prefetch_related("sender")

    return {
        "count": total,
        "messages": [
            {
                "id": m.id,
                "thread_id": thread.id,
                "text": m.text,
                "attachments": m.attachments or [],
                "created_at": m.created_at,
                "from": {
                    "id": m.sender_id,
                    "name": getattr(m.sender, "name", None) if getattr(m, "sender", None) else None,
                    "email": getattr(m.sender, "email", None) if getattr(m, "sender", None) else None,
                },
            }
            for m in msgs
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chat/admin/threads")
async def admin_list_threads(
    admin: Annotated[User, Depends(get_user_admin)],
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """
    List all threads for this admin with latest message + unread counts.
    """
    threads = await ChatThread.filter(admin=admin).offset(skip).limit(limit).prefetch_related("user")
    result = []

    for t in threads:
        last_msg = await ChatMessage.filter(thread=t).order_by("-created_at").first()
        unread = await ChatMessage.filter(thread=t, read_by_admin=False).exclude(sender=admin).count()
        result.append(
            {
                "thread_id": t.id,
                "user": {"id": t.user_id, "name": getattr(t.user, "name", None), "email": getattr(t.user, "email", None)},
                "last_message": {
                    "id": last_msg.id if last_msg else None,
                    "text": last_msg.text if last_msg else None,
                    "created_at": last_msg.created_at if last_msg else None,
                    "sender_id": last_msg.sender_id if last_msg else None,
                } if last_msg else None,
                "unread_for_admin": unread,
                "created_at": t.created_at,
            }
        )

    return {"threads": result}


@router.get("/chat/admin/messages/{user_id}")
async def admin_list_messages_for_user(
    user_id: str,
    admin: Annotated[User, Depends(get_user_admin)],
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    order: str = Query("asc", regex="^(asc|desc)$"),
):
    try:
        u = await User.get(id=user_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")

    thread = await ChatThread.get_or_none(user=u, admin=admin)
    if not thread:
        return {"messages": [], "thread_id": None, "user_id": u.id}

    qs = ChatMessage.filter(thread=thread)
    qs = qs.order_by("created_at" if order == "asc" else "-created_at")
    msgs = await qs.offset(skip).limit(limit)
    return {
        "thread_id": thread.id,
        "user_id": u.id,
        "messages": [
            {
                "id": m.id,
                "text": m.text,
                "attachments": m.attachments or [],
                "created_at": m.created_at,
                "sender_id": m.sender_id,
                "read_by_user": m.read_by_user,
                "read_by_admin": m.read_by_admin,
            }
            for m in msgs
        ],
    }


@router.post("/chat/admin/send")
async def admin_send_message(
    body: AdminSendMessageRequest,
    admin: Annotated[User, Depends(get_user_admin)],
):
    # validate content
    SendMessageRequest.validate_nonempty(body)

    try:
        u = await User.get(id=body.user_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")

    thread = await _get_or_create_thread(user=u, admin=admin)
    read_by_user, read_by_admin = _read_flags_for(sender=admin, user=u, admin=admin)

    msg = await ChatMessage.create(
        thread=thread,
        sender=admin,
        text=(body.text or "").strip() or None,
        attachments=body.attachments,
        read_by_user=read_by_user,
        read_by_admin=read_by_admin,
    )

    return {
        "success": True,
        "thread_id": thread.id,
        "message": {
            "id": msg.id,
            "text": msg.text,
            "attachments": msg.attachments or [],
            "created_at": msg.created_at,
            "sender_id": admin.id,
        },
    }


@router.post("/chat/admin/mark-read")
async def admin_mark_read(
    body: MarkReadRequest,
    admin: Annotated[User, Depends(get_user_admin)],
):
    if not body.user_id:
        raise HTTPException(status_code=422, detail="'user_id' is required for admin mark-read")

    try:
        u = await User.get(id=body.user_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="User not found")

    thread = await ChatThread.get_or_none(user=u, admin=admin)
    if not thread:
        return {"success": True, "updated": 0}

    updated = await ChatMessage.filter(
        thread=thread, read_by_admin=False
    ).exclude(sender=admin).update(read_by_admin=True)
    return {"success": True, "updated": updated}


@router.get("/chat/admin/unread-count")
async def admin_unread_count(
    admin: Annotated[User, Depends(get_user_admin)],
    user_id: Optional[str] = None,
):
    """
    If user_id is provided, return unread for that thread; otherwise total unread across all threads.
    """
    if user_id:
        try:
            u = await User.get(id=user_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="User not found")
        thread = await ChatThread.get_or_none(user=u, admin=admin)
        if not thread:
            return {"count": 0}
        count = await ChatMessage.filter(thread=thread, read_by_admin=False).exclude(sender=admin).count()
        return {"count": count}

    # total across all threads for this admin
    threads = await ChatThread.filter(admin=admin)
    total = 0
    for t in threads:
        c = await ChatMessage.filter(thread=t, read_by_admin=False).exclude(sender=admin).count()
        total += c
    return {"count": total}


# NEW: Admin notifications (messages + total)
@router.get("/chat/admin/notifications")
async def admin_notifications(
    admin: Annotated[User, Depends(get_user_admin)],
    user_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """
    Return unread messages for admin:
      - If user_id provided: unread for that user's thread.
      - Else: unread across all threads for this admin.
    """
    if user_id:
        try:
            u = await User.get(id=user_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="User not found")

        thread = await ChatThread.get_or_none(user=u, admin=admin)
        if not thread:
            return {"count": 0, "messages": []}

        qs = ChatMessage.filter(thread=thread, read_by_admin=False).exclude(sender=admin).order_by("-created_at")
        total = await qs.count()
        msgs = await qs.limit(limit).prefetch_related("sender", "thread", "thread__user")

        return {
            "count": total,
            "messages": [
                {
                    "id": m.id,
                    "thread_id": m.thread_id,
                    "text": m.text,
                    "attachments": m.attachments or [],
                    "created_at": m.created_at,
                    "from_user": {
                        "id": m.sender_id,
                        "name": getattr(m.sender, "name", None) if getattr(m, "sender", None) else None,
                        "email": getattr(m.sender, "email", None) if getattr(m, "sender", None) else None,
                    },
                }
                for m in msgs
            ],
        }

    # All threads for this admin
    threads = await ChatThread.filter(admin=admin).only("id").all()
    if not threads:
        return {"count": 0, "messages": []}

    thread_ids = [t.id for t in threads]
    qs = (
        ChatMessage
        .filter(thread_id__in=thread_ids, read_by_admin=False)
        .exclude(sender=admin)
        .order_by("-created_at")
        .prefetch_related("sender", "thread", "thread__user")
    )

    total = await qs.count()
    msgs = await qs.limit(limit)

    return {
        "count": total,
        "messages": [
            {
                "id": m.id,
                "thread_id": m.thread_id,
                "text": m.text,
                "attachments": m.attachments or [],
                "created_at": m.created_at,
                "from_user": {
                    "id": m.sender_id,
                    "name": getattr(m.sender, "name", None) if getattr(m, "sender", None) else None,
                    "email": getattr(m.sender, "email", None) if getattr(m, "sender", None) else None,
                },
                "thread_user": {
                    "id": getattr(m.thread, "user_id", None) if getattr(m, "thread", None) else None,
                    "name": getattr(getattr(m.thread, "user", None), "name", None) if getattr(m, "thread", None) else None,
                    "email": getattr(getattr(m.thread, "user", None), "email", None) if getattr(m, "thread", None) else None,
                },
            }
            for m in msgs
        ],
    }
