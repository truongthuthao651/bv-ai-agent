"""User-scoped conversation CRUD — each account sees only its own threads.

There is no admin list endpoint here by design (employee chat privacy).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import auth, conversations as conv_store

router = APIRouter(tags=["conversations"])


class MessagePayload(BaseModel):
    role: str
    text: str = ""
    streaming: bool = False
    completionId: str | None = None


class ConversationPayload(BaseModel):
    id: str
    title: str = "Cuộc trò chuyện mới"
    customTitle: str | None = None
    messages: list[MessagePayload] = Field(default_factory=list)
    updatedAt: int


class ConversationSyncRequest(BaseModel):
    conversations: list[ConversationPayload] = Field(default_factory=list)
    activeId: str | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationPayload]
    activeId: str | None = None


def _require_account(request: Request):
    account = auth.current_account(request)
    if account is None:
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập.")
    return account


def _to_payload(conv: conv_store.Conversation) -> ConversationPayload:
    return ConversationPayload(
        id=conv.id,
        title=conv.title,
        customTitle=conv.custom_title,
        messages=[MessagePayload.model_validate(m) for m in conv.messages],
        updatedAt=conv.updated_at,
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_my_conversations(request: Request) -> ConversationListResponse:
    account = _require_account(request)
    items = [_to_payload(c) for c in conv_store.list_conversations(account.email)]
    active_id = items[0].id if items else None
    return ConversationListResponse(conversations=items, activeId=active_id)


@router.put("/conversations/{conv_id}", response_model=ConversationPayload)
async def upsert_my_conversation(
    request: Request, conv_id: str, body: ConversationPayload
) -> ConversationPayload:
    account = _require_account(request)
    if body.id != conv_id:
        raise HTTPException(status_code=400, detail="ID trong URL và body phải khớp.")
    saved = conv_store.upsert_conversation(
        account.email,
        conv_id,
        title=body.title,
        custom_title=body.customTitle,
        messages=[m.model_dump(by_alias=False) for m in body.messages],
        updated_at=body.updatedAt,
    )
    return _to_payload(saved)


@router.post("/conversations/sync", response_model=ConversationListResponse)
async def sync_my_conversations(
    request: Request, body: ConversationSyncRequest
) -> ConversationListResponse:
    """Replace the caller's server-side list — used for sessionStorage migration."""
    account = _require_account(request)
    items = [
        conv_store.Conversation(
            id=c.id,
            title=c.title,
            custom_title=c.customTitle,
            messages=[m.model_dump(by_alias=False) for m in c.messages],
            updated_at=c.updatedAt,
        )
        for c in body.conversations
    ]
    conv_store.replace_all_conversations(account.email, items)
    active_id = body.activeId
    if active_id and not any(c.id == active_id for c in items):
        active_id = items[0].id if items else None
    elif not active_id and items:
        active_id = items[0].id
    return ConversationListResponse(
        conversations=[
            _to_payload(c) for c in conv_store.list_conversations(account.email)
        ],
        activeId=active_id,
    )


@router.delete("/conversations/{conv_id}")
async def delete_my_conversation(request: Request, conv_id: str) -> dict[str, bool]:
    account = _require_account(request)
    if not conv_store.delete_conversation(account.email, conv_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
    return {"ok": True}


@router.delete("/conversations")
async def delete_all_my_conversations(request: Request) -> dict[str, bool]:
    account = _require_account(request)
    conv_store.delete_all_conversations(account.email)
    return {"ok": True}
