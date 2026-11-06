from datetime import datetime

from pydantic import BaseModel, Field


class AdminOverview(BaseModel):
    total_users: int
    total_documents: int
    active_shares: int
    events_last_7_days: int
    denied_last_7_days: int
    daily_events: list[dict[str, int | str]]
    security_alerts: list[dict[str, int | str]] = Field(default_factory=list)


class AuditIntegrity(BaseModel):
    valid: bool
    checkpoint_matches: bool
    sealed_events: int
    legacy_unsealed_events: int


class AdminUserItem(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class UserStatusUpdate(BaseModel):
    is_active: bool


class AdminActivityItem(BaseModel):
    id: int
    actor_name: str | None
    actor_email: str | None
    document_id: int | None
    document_title: str | None
    action: str
    outcome: str
    details: str | None
    created_at: datetime


class AdminActivityPage(BaseModel):
    items: list[AdminActivityItem]
    total: int
    limit: int
    offset: int
