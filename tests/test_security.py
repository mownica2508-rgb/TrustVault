from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.permission import AccessLevel


def test_unshared_member_cannot_read_download_edit_or_delete(
    client, db_factory, auth_headers, owned_document
):
    headers = auth_headers("outsider")
    doc_url = f"/api/documents/{owned_document}"

    assert client.get(doc_url, headers=headers).status_code == 404
    assert client.get(f"{doc_url}/view", headers=headers).status_code == 404
    assert client.get(f"{doc_url}/download", headers=headers).status_code == 404
    assert client.get(f"{doc_url}/versions", headers=headers).status_code == 404
    assert client.get(f"{doc_url}/permissions", headers=headers).status_code == 404
    assert client.patch(doc_url, headers=headers, json={"title": "Stolen"}).status_code == 404
    assert client.delete(doc_url, headers=headers).status_code == 404

    with db_factory() as db:
        denied = db.scalars(
            select(AuditEvent).where(AuditEvent.document_id == owned_document, AuditEvent.outcome == "denied")
        ).all()
        assert len(denied) == 7
        assert all(event.action in {
            "metadata_read", "view", "download", "version_list", "list_permissions",
            "metadata_update", "delete",
        } for event in denied)


def test_read_permission_allows_only_read_operations(
    client, auth_headers, owned_document, grant, monkeypatch, tmp_path
):
    grant("reader", AccessLevel.READ)
    headers = auth_headers("reader")
    file_path = tmp_path / "plan.txt"
    file_path.write_text("private plan", encoding="utf-8")
    monkeypatch.setattr("app.api.documents.stored_path", lambda _key: file_path)
    doc_url = f"/api/documents/{owned_document}"

    assert client.get(doc_url, headers=headers).status_code == 200
    assert client.get(f"{doc_url}/download", headers=headers).status_code == 200
    assert client.patch(doc_url, headers=headers, json={"title": "Changed"}).status_code == 404
    assert client.put(
        f"{doc_url}/file", headers=headers, files={"file": ("new.txt", b"new", "text/plain")}
    ).status_code == 404
    assert client.post(
        f"{doc_url}/permissions", headers=headers,
        json={"email": "outsider@example.com", "access_level": "read"},
    ).status_code == 404
    assert client.delete(doc_url, headers=headers).status_code == 404


def test_edit_grant_can_change_metadata_but_cannot_share_or_delete(
    client, auth_headers, owned_document, grant
):
    grant("editor", AccessLevel.EDIT)
    headers = auth_headers("editor")
    doc_url = f"/api/documents/{owned_document}"

    changed = client.patch(doc_url, headers=headers, json={"title": "Updated plan"})
    assert changed.status_code == 200
    assert changed.json()["title"] == "Updated plan"
    assert client.delete(doc_url, headers=headers).status_code == 404
    assert client.get(f"{doc_url}/permissions", headers=headers).status_code == 404


def test_revocation_blocks_the_next_request_and_removes_shared_listing(
    client, auth_headers, owned_document, grant
):
    grant_id = grant("reader", AccessLevel.READ)
    owner_headers = auth_headers("owner")
    reader_headers = auth_headers("reader")
    doc_url = f"/api/documents/{owned_document}"

    assert client.get(doc_url, headers=reader_headers).status_code == 200
    assert len(client.get("/api/documents/shared", headers=reader_headers).json()) == 1
    revoked = client.delete(f"{doc_url}/permissions/{grant_id}", headers=owner_headers)
    assert revoked.status_code == 204
    assert client.get(doc_url, headers=reader_headers).status_code == 404
    assert client.get("/api/documents/shared", headers=reader_headers).json() == []


def test_admin_activity_api_is_admin_only_and_does_not_grant_document_access(
    client, auth_headers, owned_document
):
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert "Latest events" in dashboard.text
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/overview", headers=auth_headers("outsider")).status_code == 403
    assert client.get("/api/admin/activity", headers=auth_headers("reader")).status_code == 403
    assert client.get(f"/api/documents/{owned_document}", headers=auth_headers("admin")).status_code == 404

    overview = client.get("/api/admin/overview", headers=auth_headers("admin"))
    activity = client.get("/api/admin/activity", headers=auth_headers("admin"))
    assert overview.status_code == 200
    assert overview.json()["total_documents"] == 1
    assert len(overview.json()["daily_events"]) == 7
    assert activity.status_code == 200
    assert activity.json()["total"] >= 1
    assert any(item["action"] == "admin_access" and item["outcome"] == "denied" for item in activity.json()["items"])
    assert any(item["action"] == "metadata_read" and item["outcome"] == "denied" for item in activity.json()["items"])


def test_public_registration_cannot_promote_itself_to_admin(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "new-person@example.com",
            "full_name": "New Person",
            "password": "A-long-demo-password-123",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "member"
