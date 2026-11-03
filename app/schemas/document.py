from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.permission import AccessLevel


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    owner_name: str
    title: str
    original_filename: str
    category: str | None
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    updated_at: datetime


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=80)


class ShareRequest(BaseModel):
    email: EmailStr
    access_level: AccessLevel


class PermissionResponse(BaseModel):
    id: int
    recipient_email: EmailStr
    recipient_name: str
    access_level: AccessLevel
    created_at: datetime


class SharedDocumentResponse(DocumentResponse):
    access_level: AccessLevel

