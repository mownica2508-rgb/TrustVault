import os
import hashlib

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditEvent  # noqa: F401
from app.models.document import Document
from app.models.permission import AccessLevel, DocumentPermission  # noqa: F401
from app.core.security import create_access_token
from app.models.user import User, UserRole


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_factory):
    def override_get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def accounts(db_factory):
    with db_factory() as db:
        owner = User(email="owner@example.com", full_name="Owner One", password_hash="not-used", role=UserRole.MEMBER)
        reader = User(email="reader@example.com", full_name="Read Member", password_hash="not-used", role=UserRole.MEMBER)
        editor = User(email="editor@example.com", full_name="Edit Member", password_hash="not-used", role=UserRole.MEMBER)
        outsider = User(email="outsider@example.com", full_name="Outside Member", password_hash="not-used", role=UserRole.MEMBER)
        admin = User(email="admin@example.com", full_name="Vault Admin", password_hash="not-used", role=UserRole.ADMIN)
        db.add_all([owner, reader, editor, outsider, admin])
        db.commit()
        ids = {user.email.split("@")[0]: user.id for user in [owner, reader, editor, outsider, admin]}
    return ids


@pytest.fixture
def auth_headers(accounts):
    def headers_for(name: str) -> dict[str, str]:
        token, _ = create_access_token(accounts[name])
        return {"Authorization": f"Bearer {token}"}

    return headers_for


@pytest.fixture
def owned_document(db_factory, accounts):
    with db_factory() as db:
        document = Document(
            owner_id=accounts["owner"],
            title="Quarterly plan",
            original_filename="plan.txt",
            category="Planning",
            storage_name="a" * 32 + ".txt",
            content_type="text/plain",
            size_bytes=12,
            sha256=hashlib.sha256(b"private plan").hexdigest(),
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
    return document_id


@pytest.fixture
def grant(db_factory, accounts, owned_document):
    def create(name: str, level: AccessLevel) -> int:
        with db_factory() as db:
            permission = DocumentPermission(
                document_id=owned_document,
                recipient_id=accounts[name],
                granted_by_id=accounts["owner"],
                access_level=level,
            )
            db.add(permission)
            db.commit()
            return permission.id

    return create
