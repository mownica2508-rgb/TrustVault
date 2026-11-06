from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_admin
from app.core.audit import append_audit
from app.core.audit import verify_audit_chain
from app.core.database import get_db
from app.models.audit import AuditEvent
from app.models.document import Document
from app.models.permission import DocumentPermission
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminActivityItem,
    AdminActivityPage,
    AdminOverview,
    AdminUserItem,
    AuditIntegrity,
    UserStatusUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["administration"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/overview", response_model=AdminOverview)
def admin_overview(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminOverview:
    cutoff = _now() - timedelta(days=6)
    day_start = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_documents = db.scalar(select(func.count(Document.id))) or 0
    active_shares = db.scalar(
        select(func.count(DocumentPermission.id)).where(
            DocumentPermission.revoked_at.is_(None),
            or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > _now()),
        )
    ) or 0
    events_last_7_days = db.scalar(
        select(func.count(AuditEvent.id)).where(AuditEvent.created_at >= day_start)
    ) or 0
    denied_last_7_days = db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.created_at >= day_start, AuditEvent.outcome == "denied"
        )
    ) or 0
    daily_rows = db.execute(
        select(func.date(AuditEvent.created_at), func.count(AuditEvent.id))
        .where(AuditEvent.created_at >= day_start)
        .group_by(func.date(AuditEvent.created_at))
    ).all()
    counts = {str(day): int(count) for day, count in daily_rows}
    daily_events = []
    for offset in range(7):
        day = (day_start + timedelta(days=offset)).date().isoformat()
        daily_events.append({"date": day, "count": counts.get(day, 0)})
    alert_rows = db.execute(
        select(User.id, User.full_name, User.email, func.count(AuditEvent.id).label("denied_count"))
        .join(AuditEvent, AuditEvent.actor_id == User.id)
        .where(AuditEvent.outcome == "denied", AuditEvent.created_at >= _now() - timedelta(hours=1))
        .group_by(User.id, User.full_name, User.email)
        .having(func.count(AuditEvent.id) >= 5)
        .order_by(func.count(AuditEvent.id).desc())
        .limit(10)
    ).all()
    security_alerts = [
        {"user_id": user_id, "name": name, "email": email, "denied_count": int(count)}
        for user_id, name, email, count in alert_rows
    ]
    return AdminOverview(
        total_users=total_users,
        total_documents=total_documents,
        active_shares=active_shares,
        events_last_7_days=events_last_7_days,
        denied_last_7_days=denied_last_7_days,
        daily_events=daily_events,
        security_alerts=security_alerts,
    )


@router.get("/audit-integrity", response_model=AuditIntegrity)
def audit_integrity(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AuditIntegrity:
    """Verify the HMAC chain without exposing or mutating audit events."""
    return AuditIntegrity(**verify_audit_chain(db))


@router.get("/users", response_model=list[AdminUserItem])
def admin_users(
    search: str | None = Query(default=None, max_length=320),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminUserItem]:
    query = select(User)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        query = query.where(or_(User.full_name.ilike(needle), User.email.ilike(needle)))
    users = db.scalars(query.order_by(User.created_at.desc(), User.id.desc()).limit(limit)).all()
    return [
        AdminUserItem(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
        )
        for user in users
    ]


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminUserItem:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not payload.is_active and target.id == admin.id:
        append_audit(db, admin.id, "account_disable", "denied", target_user_id=target.id, target_email=target.email, reason="self_disable")
        db.commit()
        raise HTTPException(status_code=409, detail="You cannot disable your own administrator account")
    if not payload.is_active and target.role == UserRole.ADMIN and target.is_active:
        active_admins = db.scalar(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        ) or 0
        if active_admins <= 1:
            append_audit(db, admin.id, "account_disable", "denied", target_user_id=target.id, target_email=target.email, reason="last_active_admin")
            db.commit()
            raise HTTPException(status_code=409, detail="The last active administrator cannot be disabled")
    if target.is_active != payload.is_active:
        target.is_active = payload.is_active
        if not payload.is_active:
            now = _now()
            grants = db.scalars(
                select(DocumentPermission).where(
                    or_(
                        DocumentPermission.recipient_id == target.id,
                        DocumentPermission.granted_by_id == target.id,
                    ),
                    DocumentPermission.revoked_at.is_(None),
                )
            ).all()
            for grant in grants:
                grant.revoked_at = now
                append_audit(
                    db,
                    admin.id,
                    "permission_revoked",
                    "success",
                    grant.document_id,
                    recipient_id=target.id,
                    grantor_id=grant.granted_by_id,
                    reason="account_disabled",
                )
        append_audit(
            db,
            admin.id,
            "account_enabled" if payload.is_active else "account_disabled",
            "success",
            target_user_id=target.id,
            target_email=target.email,
        )
        db.commit()
        db.refresh(target)
    return AdminUserItem(
        id=target.id,
        full_name=target.full_name,
        email=target.email,
        role=target.role.value,
        is_active=target.is_active,
        created_at=target.created_at,
    )


@router.get("/activity", response_model=AdminActivityPage)
def admin_activity(
    action: str | None = Query(default=None, max_length=40),
    outcome: str | None = Query(default=None, pattern="^(success|denied)$"),
    search: str | None = Query(default=None, max_length=320),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminActivityPage:
    query = (
        select(AuditEvent, User.full_name, User.email, Document.title)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .outerjoin(Document, Document.id == AuditEvent.document_id)
    )
    filters = []
    if action:
        filters.append(AuditEvent.action == action)
    if outcome:
        filters.append(AuditEvent.outcome == outcome)
    if date_from:
        filters.append(AuditEvent.created_at >= date_from)
    if date_to:
        filters.append(AuditEvent.created_at <= date_to)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        filters.append(or_(User.full_name.ilike(needle), User.email.ilike(needle), Document.title.ilike(needle)))
    if filters:
        query = query.where(*filters)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset(offset).limit(limit)
    ).all()
    items = [
        AdminActivityItem(
            id=event.id,
            actor_name=actor_name,
            actor_email=actor_email,
            document_id=event.document_id,
            document_title=document_title,
            action=event.action,
            outcome=event.outcome,
            details=event.details,
            created_at=event.created_at,
        )
        for event, actor_name, actor_email, document_title in rows
    ]
    return AdminActivityPage(items=items, total=total, limit=limit, offset=offset)
