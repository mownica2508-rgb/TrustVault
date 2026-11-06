from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return value


class PermissionResponse(BaseModel):
    id: int
    recipient_email: EmailStr
    recipient_name: str
    access_level: AccessLevel
    created_at: datetime
    expires_at: datetime | None = None


class SharedDocumentResponse(DocumentResponse):
    access_level: AccessLevel


class SharedRecipient(BaseModel):
    grant_id: int
    full_name: str
    email: EmailStr
    access_level: AccessLevel
    expires_at: datetime | None = None


class DocumentVersionResponse(BaseModel):
    id: int
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by_name: str | None
    created_at: datetime
    is_current: bool


class DocumentSharingStatus(DocumentResponse):
    active_share_count: int
    recipients: list[SharedRecipient]
