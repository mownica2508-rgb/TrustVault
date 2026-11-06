from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy import select

from app.models.document import Document, DocumentVersion
from app.models.permission import AccessLevel, DocumentPermission


def test_expired_grant_is_removed_from_search_and_denied_immediately(
    client, db_factory, auth_headers, owned_document, grant
):
    grant_id = grant("reader", AccessLevel.READ)
    with db_factory() as db:
        permission = db.get(DocumentPermission, grant_id)
        permission.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    reader = auth_headers("reader")
    assert client.get("/api/documents/shared", headers=reader).json() == []
    assert client.get(f"/api/documents/{owned_document}", headers=reader).status_code == 404
    assert client.get(f"/api/documents/{owned_document}/permissions", headers=reader).status_code == 404
    assert client.get("/api/admin/overview", headers=auth_headers("admin")).json()["active_shares"] == 0


def test_owner_can_create_expiring_grant_and_server_returns_its_expiry(
    client, auth_headers, owned_document
):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.post(
        f"/api/documents/{owned_document}/permissions",
        headers=auth_headers("owner"),
        json={"email": "reader@example.com", "access_level": "read", "expires_at": expiry},
    )
    assert response.status_code == 201
    assert response.json()["expires_at"] is not None
    assert len(client.get("/api/documents/shared", headers=auth_headers("reader")).json()) == 1


def test_version_history_is_scoped_and_owner_restore_creates_a_new_version(
    client, db_factory, auth_headers, owned_document, accounts, grant, monkeypatch, tmp_path
):
    first_bytes = b"first file version"
    second_bytes = b"current file version"
    first_path = tmp_path / "v1.txt"
    current_path = tmp_path / "v2.txt"
    first_path.write_bytes(first_bytes)
    current_path.write_bytes(second_bytes)
    first_hash = hashlib.sha256(first_bytes).hexdigest()
    current_hash = hashlib.sha256(second_bytes).hexdigest()
    with db_factory() as db:
        document = db.get(Document, owned_document)
        document.storage_name = "c" * 32 + ".txt"
        document.sha256 = current_hash
        v1 = DocumentVersion(
            document_id=owned_document, version_number=1, original_filename="plan-v1.txt",
            storage_name="d" * 32 + ".txt", content_type="text/plain",
            size_bytes=len(first_bytes), sha256=first_hash, uploaded_by_id=accounts["owner"],
        )
        v2 = DocumentVersion(
            document_id=owned_document, version_number=2, original_filename="plan-v2.txt",
            storage_name=document.storage_name, content_type="text/plain",
            size_bytes=len(second_bytes), sha256=current_hash, uploaded_by_id=accounts["owner"],
        )
        db.add_all([v1, v2])
        db.commit()
        first_version_id = v1.id

    paths = {"d" * 32 + ".txt": first_path, "c" * 32 + ".txt": current_path}
    monkeypatch.setattr("app.api.documents.stored_path", lambda storage_name: paths[storage_name])
    grant("reader", AccessLevel.READ)
    owner = auth_headers("owner")
    outsider = auth_headers("outsider")
    reader = auth_headers("reader")
    assert client.get(f"/api/documents/{owned_document}/versions", headers=outsider).status_code == 404
    assert client.post(
        f"/api/documents/{owned_document}/versions/{first_version_id}/restore", headers=outsider
    ).status_code == 404
    assert client.get(f"/api/documents/{owned_document}/versions", headers=reader).status_code == 200
    historical_download = client.get(
        f"/api/documents/{owned_document}/versions/{first_version_id}/download", headers=reader
    )
    assert historical_download.status_code == 200
    assert historical_download.content == first_bytes
    assert client.post(
        f"/api/documents/{owned_document}/versions/{first_version_id}/restore", headers=reader
    ).status_code == 404

    history = client.get(f"/api/documents/{owned_document}/versions", headers=owner)
    assert history.status_code == 200
    assert [item["version_number"] for item in history.json()] == [2, 1]
    restored = client.post(
        f"/api/documents/{owned_document}/versions/{first_version_id}/restore", headers=owner
    )
    assert restored.status_code == 200
    assert restored.json()["sha256"] == first_hash
    after_restore = client.get(f"/api/documents/{owned_document}/versions", headers=owner).json()
    assert after_restore[0]["version_number"] == 3
    assert after_restore[0]["is_current"] is True


def test_audit_hmac_chain_detects_database_tampering_and_is_admin_only(
    client, db_factory, auth_headers, owned_document
):
    client.get(f"/api/documents/{owned_document}", headers=auth_headers("owner"))
    admin = auth_headers("admin")
    assert client.get("/api/admin/audit-integrity", headers=admin).json()["valid"] is True
    assert client.get("/api/admin/audit-integrity", headers=auth_headers("reader")).status_code == 403

    from app.models.audit import AuditEvent
    with db_factory() as db:
        db.add(AuditEvent(actor_id=None, action="forged_event", outcome="success"))
        db.commit()
    assert client.get("/api/admin/audit-integrity", headers=admin).json()["valid"] is False

    with db_factory() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_hash.is_not(None)))
        event.details = '{"tampered":true}'
        db.commit()
    integrity = client.get("/api/admin/audit-integrity", headers=admin)
    assert integrity.status_code == 200
    assert integrity.json()["valid"] is False


def test_admin_alerts_after_repeated_denied_document_requests(
    client, auth_headers, owned_document
):
    outsider = auth_headers("outsider")
    for _ in range(5):
        assert client.get(f"/api/documents/{owned_document}", headers=outsider).status_code == 404
    overview = client.get("/api/admin/overview", headers=auth_headers("admin"))
    assert overview.status_code == 200
    assert any(alert["email"] == "outsider@example.com" for alert in overview.json()["security_alerts"])


def test_download_refuses_a_file_that_no_longer_matches_its_saved_digest(
    client, auth_headers, owned_document, grant, monkeypatch, tmp_path
):
    grant("reader", AccessLevel.READ)
    corrupt = tmp_path / "tampered.txt"
    corrupt.write_text("changed after upload", encoding="utf-8")
    monkeypatch.setattr("app.api.documents.stored_path", lambda _name: corrupt)
    response = client.get(
        f"/api/documents/{owned_document}/download", headers=auth_headers("reader")
    )
    assert response.status_code == 409
    assert "integrity" in response.json()["detail"].lower()


def test_admin_account_disable_revokes_shares_and_reenable_does_not_restore_them(
    client, auth_headers, accounts, owned_document, grant
):
    grant("reader", AccessLevel.READ)
    grant("editor", AccessLevel.EDIT)
    admin = auth_headers("admin")
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    assert client.get("/api/admin/users", headers=auth_headers("outsider")).status_code == 403

    disabled_reader = client.patch(
        f"/api/admin/users/{accounts['reader']}/status",
        headers=admin,
        json={"is_active": False},
    )
    assert disabled_reader.status_code == 200
    assert disabled_reader.json()["is_active"] is False
    assert client.get("/api/documents/shared", headers=auth_headers("reader")).status_code == 401

    assert client.patch(
        f"/api/admin/users/{accounts['reader']}/status",
        headers=admin,
        json={"is_active": True},
    ).status_code == 200
    assert client.get(f"/api/documents/{owned_document}", headers=auth_headers("reader")).status_code == 404

    disabled_owner = client.patch(
        f"/api/admin/users/{accounts['owner']}/status",
        headers=admin,
        json={"is_active": False},
    )
    assert disabled_owner.status_code == 200
    assert client.get(f"/api/documents/{owned_document}", headers=auth_headers("editor")).status_code == 404

    self_disable = client.patch(
        f"/api/admin/users/{accounts['admin']}/status",
        headers=admin,
        json={"is_active": False},
    )
    assert self_disable.status_code == 409
