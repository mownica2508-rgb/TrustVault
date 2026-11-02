from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.file_storage import UploadRejected, remove_stored_file, save_upload, stored_path
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentUpdate

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _owner_document(db: Session, document_id: int, user_id: int) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == user_id)
    )
    if document is None:
        # A uniform 404 avoids confirming that another user owns this ID.
        raise HTTPException(status_code=404, detail="Document not found")
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


def _save_file(upload: UploadFile):
    try:
        return save_upload(upload.file, upload.filename)
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
    stored = _save_file(file)
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
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    query = select(Document).where(Document.owner_id == user.id)
    if name and name.strip():
        needle = f"%{name.strip()}%"
        query = query.where((Document.title.ilike(needle)) | (Document.original_filename.ilike(needle)))
    if owner and owner.strip():
        needle = f"%{owner.strip()}%"
        query = query.join(User, User.id == Document.owner_id).where(
            (User.full_name.ilike(needle)) | (User.email.ilike(needle))
        )
    if category and category.strip():
        query = query.where(Document.category.ilike(f"%{category.strip()}%"))
    if date_from:
        query = query.where(func.date(Document.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(Document.created_at) <= date_to)
    documents = db.scalars(
        query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit)
    ).all()
    return [_response(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    return _response(_owner_document(db, document_id, user.id))


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    document = _owner_document(db, document_id, user.id)
    try:
        path = stored_path(document.storage_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{document_id}/view")
def view_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    document = _owner_document(db, document_id, user.id)
    if document.content_type not in {"application/pdf", "text/plain"}:
        raise HTTPException(status_code=415, detail="In-browser preview is available for PDF and TXT files")
    try:
        path = stored_path(document.storage_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; object-src 'none'",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    document = _owner_document(db, document_id, user.id)
    fields = payload.model_fields_set
    if "title" in fields:
        document.title = _clean_label(payload.title, "Title", 160, required=True)
    if "category" in fields:
        document.category = _clean_label(payload.category, "Category", 80, required=False)
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
    document = _owner_document(db, document_id, user.id)
    stored = _save_file(file)
    previous_storage_name = document.storage_name
    document.original_filename = stored.original_filename
    document.storage_name = stored.storage_name
    document.content_type = stored.content_type
    document.size_bytes = stored.size_bytes
    document.sha256 = stored.sha256
    try:
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        remove_stored_file(stored.storage_name)
        raise
    remove_stored_file(previous_storage_name)
    return _response(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    document = _owner_document(db, document_id, user.id)
    storage_name = document.storage_name
    db.delete(document)
    db.commit()
    remove_stored_file(storage_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
