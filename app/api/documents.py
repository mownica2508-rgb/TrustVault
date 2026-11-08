from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.audit import append_audit
from app.core.database import get_db
from app.core.file_storage import UploadRejected, remove_stored_file, save_upload, stored_path, verify_file_digest
from app.models.document import Document, DocumentVersion
from app.models.permission import AccessLevel, DocumentPermission
from app.models.share_suggestion import ShareSuggestion
from app.models.user import User
from app.schemas.document import (
    DocumentResponse,
    DocumentSharingStatus,
    DocumentVersionResponse,
    DocumentUpdate,
    PermissionResponse,
    ShareRequest,
    SharedRecipient,
    SharedDocumentResponse,
    ShareSuggestionDecision,
    ShareSuggestionResponse,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _audit(
    db: Session,
    actor_id: int,
    action: str,
    outcome: str,
    document_id: int | None = None,
    **details: object,
) -> None:
    append_audit(db, actor_id, action, outcome, document_id, **details)


def _deny(
    db: Session,
    user: User,
    action: str,
    document_id: int,
    *,
    status_code: int = 404,
    detail: str = "Document not found",
) -> None:
    _audit(db, user.id, action, "denied", document_id)
    db.commit()
    raise HTTPException(status_code=status_code, detail=detail)


def _document(db: Session, document_id: int) -> Document | None:
    return db.scalar(select(Document).where(Document.id == document_id))


def _active_permission(db: Session, document_id: int, recipient_id: int) -> DocumentPermission | None:
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(DocumentPermission)
        .where(
            DocumentPermission.document_id == document_id,
            DocumentPermission.recipient_id == recipient_id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > now),
        )
        .order_by(DocumentPermission.id.desc())
    )


def _require_document(
    db: Session,
    document_id: int,
    user: User,
    action: str,
    required: AccessLevel = AccessLevel.READ,
) -> tuple[Document, AccessLevel]:
    document = _document(db, document_id)
    if document is None:
        _deny(db, user, action, document_id)
    if document.owner_id == user.id:
        return document, AccessLevel.EDIT
    grant = _active_permission(db, document_id, user.id)
    permitted = grant is not None and (
        required == AccessLevel.READ
        or grant.access_level == AccessLevel.EDIT
    )
    if not permitted:
        _deny(db, user, action, document_id)
    return document, grant.access_level


def _require_owner(db: Session, document_id: int, user: User, action: str) -> Document:
    document = _document(db, document_id)
    if document is None or document.owner_id != user.id:
        _deny(db, user, action, document_id)
    return document


def _response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        owner_id=document.owner_id,
        owner_name=document.owner.full_name,
        title=document.title,
        original_filename=document.original_filename,
        category=document.category,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _clean_label(value: str | None, field: str, maximum: int, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} is required")
        return None
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} cannot be blank")
        return None
    if len(cleaned) > maximum or any(ord(char) < 32 for char in cleaned):
        raise HTTPException(status_code=422, detail=f"{field} is invalid")
    return cleaned


def _save_file(upload: UploadFile, db: Session, user: User, document_id: int | None = None):
    try:
        return save_upload(upload.file, upload.filename)
    except UploadRejected as exc:
        _audit(db, user.id, "upload" if document_id is None else "file_replace", "denied",
               document_id, reason="validation_rejected")
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _apply_filters(query, *, name, owner, category, date_from, date_to):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    if name and name.strip():
        needle = f"%{name.strip()}%"
        query = query.where(or_(Document.title.ilike(needle), Document.original_filename.ilike(needle)))
    if owner and owner.strip():
        needle = f"%{owner.strip()}%"
        query = query.join(User, User.id == Document.owner_id).where(
            or_(User.full_name.ilike(needle), User.email.ilike(needle))
        )
    if category and category.strip():
        query = query.where(Document.category.ilike(f"%{category.strip()}%"))
    if date_from:
        query = query.where(func.date(Document.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(Document.created_at) <= date_to)
    return query


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=160),
    category: str | None = Form(default=None, max_length=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document_title = _clean_label(title, "Title", 160, required=False)
    document_category = _clean_label(category, "Category", 80, required=False)
    stored = _save_file(file, db, user)
    if document_title is None:
        document_title = Path(stored.original_filename).stem[:160].strip() or "Untitled document"
    document = Document(
        owner_id=user.id,
        title=document_title,
        original_filename=stored.original_filename,
        category=document_category,
        storage_name=stored.storage_name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )
    db.add(document)
    try:
        db.flush()
        db.add(DocumentVersion(
            document_id=document.id,
            version_number=1,
            original_filename=stored.original_filename,
            storage_name=stored.storage_name,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            uploaded_by_id=user.id,
        ))
        _audit(db, user.id, "upload", "success", document.id)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        remove_stored_file(stored.storage_name)
        raise
    return _response(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    name: str | None = Query(default=None, max_length=160),
    owner: str | None = Query(default=None, max_length=320),
    category: str | None = Query(default=None, max_length=80),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    query = _apply_filters(
        select(Document).where(Document.owner_id == user.id),
        name=name, owner=owner, category=category, date_from=date_from, date_to=date_to,
    )
    documents = db.scalars(
        query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit)
    ).all()
    return [_response(document) for document in documents]


@router.get("/shared", response_model=list[SharedDocumentResponse])
def list_shared_documents(
    name: str | None = Query(default=None, max_length=160),
    owner: str | None = Query(default=None, max_length=320),
    category: str | None = Query(default=None, max_length=80),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SharedDocumentResponse]:
    query = (
        select(Document, DocumentPermission.access_level)
        .join(DocumentPermission, DocumentPermission.document_id == Document.id)
        .where(
            DocumentPermission.recipient_id == user.id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > datetime.now(timezone.utc)),
        )
    )
    query = _apply_filters(
        query, name=name, owner=owner, category=category, date_from=date_from, date_to=date_to
    )
    rows = db.execute(
        query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit)
    ).all()
    result = []
    for document, access_level in rows:
        base = _response(document).model_dump()
        result.append(SharedDocumentResponse(**base, access_level=access_level))
    return result


@router.get("/sharing-status", response_model=list[DocumentSharingStatus])
def list_owned_sharing_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentSharingStatus]:
    """Return the signed-in owner's documents with their active named recipients."""
    rows = db.execute(
        select(Document, DocumentPermission, User)
        .outerjoin(
            DocumentPermission,
            and_(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.revoked_at.is_(None),
                or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > datetime.now(timezone.utc)),
            ),
        )
        .outerjoin(User, User.id == DocumentPermission.recipient_id)
        .where(Document.owner_id == user.id)
        .order_by(Document.created_at.desc(), Document.id.desc(), DocumentPermission.id)
    ).all()
    grouped: dict[int, dict] = {}
    for document, grant, recipient in rows:
        if document.id not in grouped:
            grouped[document.id] = {
                **_response(document).model_dump(),
                "active_share_count": 0,
                "recipients": [],
            }
        if grant is not None and recipient is not None:
            grouped[document.id]["active_share_count"] += 1
            grouped[document.id]["recipients"].append(
                SharedRecipient(
                    grant_id=grant.id,
                    full_name=recipient.full_name,
                    email=recipient.email,
                    access_level=grant.access_level,
                    expires_at=grant.expires_at,
                ).model_dump()
            )
    return [DocumentSharingStatus(**item) for item in grouped.values()]


@router.get("/{document_id}/permissions", response_model=list[PermissionResponse])
def list_permissions(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PermissionResponse]:
    document = _require_owner(db, document_id, user, "list_permissions")
    grants = db.scalars(
        select(DocumentPermission)
        .where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > datetime.now(timezone.utc)),
        )
        .order_by(DocumentPermission.id)
    ).all()
    return [
        PermissionResponse(
            id=grant.id,
            recipient_email=grant.recipient.email,
            recipient_name=grant.recipient.full_name,
            access_level=grant.access_level,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
        )
        for grant in grants
    ]


@router.post("/{document_id}/permissions", response_model=PermissionResponse, status_code=201)
def grant_permission(
    document_id: int,
    payload: ShareRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PermissionResponse:
    document = _require_owner(db, document_id, user, "grant_permission")
    email = str(payload.email).strip().lower()
    recipient = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if recipient is None or recipient.id == user.id:
        _deny(db, user, "grant_permission", document.id, status_code=404, detail="Account not found")
    existing = _active_permission(db, document.id, recipient.id)
    if existing:
        existing.access_level = payload.access_level
        existing.expires_at = payload.expires_at
        grant = existing
        action = "permission_updated"
    else:
        grant = DocumentPermission(
            document_id=document.id,
            recipient_id=recipient.id,
            granted_by_id=user.id,
            access_level=payload.access_level,
            expires_at=payload.expires_at,
        )
        db.add(grant)
        action = "permission_granted"
    pending_suggestion = db.scalar(
        select(ShareSuggestion).where(
            ShareSuggestion.document_id == document.id,
            ShareSuggestion.recipient_id == recipient.id,
            ShareSuggestion.status == "pending",
        )
    )
    if pending_suggestion is not None:
        pending_suggestion.status = "dismissed"
        pending_suggestion.decided_at = datetime.now(timezone.utc)
    _audit(db, user.id, action, "success", document.id, recipient_id=recipient.id,
           access_level=payload.access_level.value)
    db.commit()
    db.refresh(grant)
    return PermissionResponse(
        id=grant.id,
        recipient_email=recipient.email,
        recipient_name=recipient.full_name,
        access_level=grant.access_level,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
    )


def _share_suggestion_response(item: ShareSuggestion) -> ShareSuggestionResponse:
    return ShareSuggestionResponse(
        id=item.id,
        recipient_email=item.recipient.email,
        recipient_name=item.recipient.full_name,
        score=item.score,
        rationale=item.rationale,
        status=item.status,
        created_at=item.created_at,
    )


@router.get("/{document_id}/sharing-suggestions", response_model=list[ShareSuggestionResponse])
def list_sharing_suggestions(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ShareSuggestionResponse]:
    document = _require_owner(db, document_id, user, "share_suggestions_list")
    items = db.scalars(
        select(ShareSuggestion).where(
            ShareSuggestion.document_id == document.id,
            ShareSuggestion.status == "pending",
        )
    ).all()
    active_grants = db.scalars(
        select(DocumentPermission.recipient_id).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > datetime.now(timezone.utc)),
        )
    ).all()
    active_recipient_ids = set(active_grants)
    visible = [item for item in items if item.recipient_id not in active_recipient_ids]
    return [_share_suggestion_response(item) for item in sorted(visible, key=lambda entry: (-entry.score, entry.recipient.email))]


@router.post("/{document_id}/sharing-suggestions", response_model=list[ShareSuggestionResponse])
def create_sharing_suggestions(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ShareSuggestionResponse]:
    """Recommend likely recipients from this owner's past grants, without reading file content."""
    document = _require_owner(db, document_id, user, "share_suggestions_generate")
    now = datetime.now(timezone.utc)
    active_grants = db.scalars(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > now),
        )
    ).all()
    current_recipient_ids = {grant.recipient_id for grant in active_grants}

    # Recommendations use only this owner's permission history and document category.
    # No document bytes, title, or metadata leave the database or get sent to a model.
    history_rows = db.execute(
        select(DocumentPermission.recipient_id, Document.category)
        .join(Document, Document.id == DocumentPermission.document_id)
        .where(
            Document.owner_id == user.id,
            Document.id != document.id,
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > now),
        )
    ).all()
    same_category_counts: dict[int, int] = {}
    all_counts: dict[int, int] = {}
    current_category = (document.category or "").strip().casefold()
    for recipient_id, category in history_rows:
        all_counts[recipient_id] = all_counts.get(recipient_id, 0) + 1
        if current_category and (category or "").strip().casefold() == current_category:
            same_category_counts[recipient_id] = same_category_counts.get(recipient_id, 0) + 1

    candidate_ids = set(all_counts) - current_recipient_ids - {user.id}
    existing_rows = db.scalars(
        select(ShareSuggestion).where(ShareSuggestion.document_id == document.id)
    ).all()
    already_suggested = {item.recipient_id for item in existing_rows}
    candidates = db.scalars(
        select(User).where(User.id.in_(candidate_ids), User.is_active.is_(True))
    ).all() if candidate_ids else []
    suggestions: list[ShareSuggestion] = []
    for candidate in candidates:
        if candidate.id in already_suggested:
            continue
        same_category = same_category_counts.get(candidate.id, 0)
        score = same_category * 3 + all_counts[candidate.id]
        rationale = (
            f"Previously received access to {same_category} other document(s) in this category."
            if same_category
            else f"Previously received access to {all_counts[candidate.id]} other document(s) from you."
        )
        suggestion = ShareSuggestion(
            document_id=document.id,
            recipient_id=candidate.id,
            score=score,
            rationale=rationale,
            status="pending",
        )
        db.add(suggestion)
        suggestions.append(suggestion)
    _audit(db, user.id, "share_suggestions_generated", "success", document.id,
           suggestion_count=len(suggestions))
    db.commit()
    return list_sharing_suggestions(document_id, db, user)


@router.post("/{document_id}/sharing-suggestions/{suggestion_id}/decision", response_model=PermissionResponse | ShareSuggestionResponse)
def decide_sharing_suggestion(
    document_id: int,
    suggestion_id: int,
    payload: ShareSuggestionDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PermissionResponse | ShareSuggestionResponse:
    document = _require_owner(db, document_id, user, "share_suggestion_decision")
    suggestion = db.scalar(
        select(ShareSuggestion).where(
            ShareSuggestion.id == suggestion_id,
            ShareSuggestion.document_id == document.id,
            ShareSuggestion.status == "pending",
        )
    )
    if suggestion is None:
        _deny(db, user, "share_suggestion_decision", document.id, status_code=404,
              detail="Pending suggestion not found")
    recipient = db.get(User, suggestion.recipient_id)
    if recipient is None or not recipient.is_active:
        _deny(db, user, "share_suggestion_decision", document.id, status_code=404,
              detail="Account not found")

    suggestion.decided_at = datetime.now(timezone.utc)
    if payload.decision == "dismiss":
        suggestion.status = "dismissed"
        _audit(db, user.id, "share_suggestion_dismissed", "success", document.id,
               recipient_id=recipient.id)
        db.commit()
        return _share_suggestion_response(suggestion)

    if _active_permission(db, document.id, recipient.id) is not None:
        raise HTTPException(status_code=409, detail="This person already has access to the document")
    grant = DocumentPermission(
        document_id=document.id,
        recipient_id=recipient.id,
        granted_by_id=user.id,
        access_level=payload.access_level,
        expires_at=None,
    )
    db.add(grant)
    suggestion.status = "approved"
    _audit(db, user.id, "share_suggestion_approved", "success", document.id,
           recipient_id=recipient.id, access_level=payload.access_level.value)
    _audit(db, user.id, "permission_granted", "success", document.id,
           recipient_id=recipient.id, access_level=payload.access_level.value,
           source="owner_approved_suggestion")
    db.commit()
    db.refresh(grant)
    return PermissionResponse(
        id=grant.id,
        recipient_email=recipient.email,
        recipient_name=recipient.full_name,
        access_level=grant.access_level,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
    )


@router.delete("/{document_id}/permissions/{grant_id}", status_code=204)
def revoke_permission(
    document_id: int,
    grant_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    document = _require_owner(db, document_id, user, "revoke_permission")
    grant = db.scalar(
        select(DocumentPermission).where(
            DocumentPermission.id == grant_id,
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
        )
    )
    if grant is None:
        _deny(db, user, "revoke_permission", document_id, status_code=404)
    grant.revoked_at = datetime.now(timezone.utc)
    _audit(db, user.id, "permission_revoked", "success", document.id,
           recipient_id=grant.recipient_id, access_level=grant.access_level.value)
    db.commit()
    return Response(status_code=204)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document, _ = _require_document(db, document_id, user, "metadata_read")
    _audit(db, user.id, "metadata_read", "success", document.id)
    db.commit()
    return _response(document)


def _file_response(db: Session, document: Document, user: User, *, inline: bool) -> FileResponse:
    action = "view" if inline else "download"
    try:
        path = stored_path(document.storage_name)
    except FileNotFoundError:
        _audit(db, user.id, action, "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document file not found")
    if not path.is_file():
        _audit(db, user.id, action, "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document file not found")
    if not verify_file_digest(path, document.sha256):
        _audit(db, user.id, action, "denied", document.id, reason="stored_file_integrity_mismatch")
        db.commit()
        raise HTTPException(status_code=409, detail="Document failed its integrity check")
    _audit(db, user.id, action, "success", document.id)
    db.commit()
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if inline:
        headers.update({
            "Content-Security-Policy": "sandbox; default-src 'none'; object-src 'none'",
            "X-Frame-Options": "SAMEORIGIN",
        })
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="inline" if inline else "attachment",
        headers=headers,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    document, _ = _require_document(db, document_id, user, "download")
    return _file_response(db, document, user, inline=False)


@router.get("/{document_id}/view")
def view_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    document, _ = _require_document(db, document_id, user, "view")
    if document.content_type not in {"application/pdf", "text/plain"}:
        _audit(db, user.id, "view", "denied", document.id, reason="unsupported_preview")
        db.commit()
        raise HTTPException(status_code=415, detail="In-browser preview is available for PDF and TXT files")
    return _file_response(db, document, user, inline=True)


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document, _ = _require_document(db, document_id, user, "metadata_update", AccessLevel.EDIT)
    fields = payload.model_fields_set
    if "title" in fields:
        document.title = _clean_label(payload.title, "Title", 160, required=True)
    if "category" in fields:
        document.category = _clean_label(payload.category, "Category", 80, required=False)
    _audit(db, user.id, "metadata_update", "success", document.id)
    db.commit()
    db.refresh(document)
    return _response(document)


@router.put("/{document_id}/file", response_model=DocumentResponse)
def replace_document_file(
    document_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document, _ = _require_document(db, document_id, user, "file_replace", AccessLevel.EDIT)
    stored = _save_file(file, db, user, document.id)
    next_version = (db.scalar(
        select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
    ) or 0) + 1
    db.add(DocumentVersion(
        document_id=document.id,
        version_number=next_version,
        original_filename=stored.original_filename,
        storage_name=stored.storage_name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        uploaded_by_id=user.id,
    ))
    document.original_filename = stored.original_filename
    document.storage_name = stored.storage_name
    document.content_type = stored.content_type
    document.size_bytes = stored.size_bytes
    document.sha256 = stored.sha256
    try:
        _audit(db, user.id, "file_replace", "success", document.id)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        remove_stored_file(stored.storage_name)
        raise
    return _response(document)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
def list_document_versions(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentVersionResponse]:
    document, _ = _require_document(db, document_id, user, "version_list")
    versions = db.execute(
        select(DocumentVersion, User.full_name)
        .outerjoin(User, User.id == DocumentVersion.uploaded_by_id)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    ).all()
    current_number = max((version.version_number for version, _ in versions), default=0)
    _audit(db, user.id, "version_list", "success", document.id)
    db.commit()
    return [
        DocumentVersionResponse(
            id=version.id,
            version_number=version.version_number,
            original_filename=version.original_filename,
            content_type=version.content_type,
            size_bytes=version.size_bytes,
            sha256=version.sha256,
            uploaded_by_name=uploaded_by,
            created_at=version.created_at,
            is_current=version.version_number == current_number,
        )
        for version, uploaded_by in versions
    ]


@router.get("/{document_id}/versions/{version_id}/download")
def download_document_version(
    document_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    document, _ = _require_document(db, document_id, user, "version_download")
    version = db.scalar(select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document.id,
    ))
    if version is None:
        _deny(db, user, "version_download", document_id)
    try:
        path = stored_path(version.storage_name)
    except FileNotFoundError:
        _audit(db, user.id, "version_download", "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document version not found")
    if not path.is_file():
        _audit(db, user.id, "version_download", "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document version not found")
    if not verify_file_digest(path, version.sha256):
        _audit(db, user.id, "version_download", "denied", document.id,
               reason="stored_file_integrity_mismatch", version=version.version_number)
        db.commit()
        raise HTTPException(status_code=409, detail="Document version failed its integrity check")
    _audit(db, user.id, "version_download", "success", document.id, version=version.version_number)
    db.commit()
    return FileResponse(
        path,
        media_type=version.content_type,
        filename=version.original_filename,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{document_id}/versions/{version_id}/restore", response_model=DocumentResponse)
def restore_document_version(
    document_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document = _require_owner(db, document_id, user, "version_restore")
    version = db.scalar(select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document.id,
    ))
    if version is None:
        _deny(db, user, "version_restore", document_id)
    try:
        path = stored_path(version.storage_name)
    except FileNotFoundError:
        _audit(db, user.id, "version_restore", "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document version not found")
    if not path.is_file():
        _audit(db, user.id, "version_restore", "denied", document.id, reason="stored_file_missing")
        db.commit()
        raise HTTPException(status_code=404, detail="Document version not found")
    if not verify_file_digest(path, version.sha256):
        _audit(db, user.id, "version_restore", "denied", document.id,
               reason="stored_file_integrity_mismatch", version=version.version_number)
        db.commit()
        raise HTTPException(status_code=409, detail="Document version failed its integrity check")
    next_version = (db.scalar(
        select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)
    ) or 0) + 1
    document.original_filename = version.original_filename
    document.storage_name = version.storage_name
    document.content_type = version.content_type
    document.size_bytes = version.size_bytes
    document.sha256 = version.sha256
    db.add(DocumentVersion(
        document_id=document.id,
        version_number=next_version,
        original_filename=version.original_filename,
        storage_name=version.storage_name,
        content_type=version.content_type,
        size_bytes=version.size_bytes,
        sha256=version.sha256,
        uploaded_by_id=user.id,
    ))
    _audit(db, user.id, "version_restore", "success", document.id,
           restored_version=version.version_number, new_version=next_version)
    db.commit()
    db.refresh(document)
    return _response(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    document = _require_owner(db, document_id, user, "delete")
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)).all()
    storage_names = {document.storage_name, *(version.storage_name for version in versions)}
    for version in versions:
        db.delete(version)
    document_id = document.id
    db.delete(document)
    _audit(db, user.id, "delete", "success", document_id)
    db.commit()
    for storage_name in storage_names:
        remove_stored_file(storage_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
