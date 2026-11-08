# TrustVault — Secure Document Management and Access Control

TrustVault is a document management and sharing application built with **FastAPI, SQLAlchemy, MySQL, JWT authentication, and HTML/CSS/JavaScript**. Documents are private by default. The server verifies ownership or an active per-document grant for every document request.

> **Demo logins:** The reviewer accounts are listed directly below. Viewer 1 has an active grant to the owner's sample document; Viewer 2 has no grant and should be denied.

## Demo accounts

Use these disposable accounts to evaluate the public demo. These passwords are public and must not be reused for personal or production accounts.

| Role | Email | Password | What to verify |
|---|---|---|---|
| Administrator | `mownica2508@gmail.com` | `mownicA@#123` | Open the activity console and review audit activity and integrity status. |
| Document owner | `owner@gmail.com` | `passOwner@#123` | Manage a document and grant or revoke access. |
| Viewer 1 — shared | `viewer1@gmail.com` | `Viewer@#12345` | Access the owner's document through the active grant. |
| Viewer 2 — unshared | `viewer2@gmail.com` | `Viewer@#12345` | Verify the owner's document cannot be reached without a grant. |

## Capabilities

| Capability | What the application provides |
|---|---|
| Sign-up and sign-in | Member registration, email/password login, Argon2 password hashing, JWT authentication, and a current-account endpoint. Public registration cannot create an administrator. |
| Roles and ownership | A protected administrator role plus regular member accounts. A member becomes the owner of each document they upload; other members receive only document-specific grants. |
| Member workspace | Separate Overview, My Documents, Shared by Me, and Shared with Me screens, with document counts and account context. |
| Upload validation | PDF, DOCX, and UTF-8 TXT allowlist, configurable maximum upload size, and server-side validation. |
| Private file storage | Random internal storage names outside the static web directory, stored-file digest verification, and authorized preview/download routes. |
| Document organization | Titles and categories, metadata editing, file replacement, deletion by the owner, version history, and restoration as a new version. |
| Search and filters | Search documents using name, owner, category, and date filters, with pagination. Results remain scoped to documents the signed-in user may discover. |
| Named sharing | Owners can grant an existing member Read or Edit access, see active recipients, and choose an expiry date or “Until I revoke.” |
| Revocation and expiry | Owners can revoke access; each request checks current permission state. Expired and revoked grants stop authorizing later requests. |
| Sharing suggestions | Local recommendations based on the owner's active sharing history and category labels. The owner must approve a suggestion before it creates a grant. |
| Audit trail | Records successful uploads, previews/downloads, document changes and deletions, permission changes, and denied document-access attempts. |
| Audit integrity | HMAC-linked audit events, a protected database checkpoint, and an administrator integrity-verification endpoint. |
| Administrator console | Activity overview, date/action/outcome/search filters, denied-access signals, audit-integrity status, user listing, and account enable/disable controls. Admin status does not automatically grant document-content access. |
| Automated security tests | Pytest checks for cross-account IDOR attempts, read/edit boundaries, revocation, expiry, version access, audit tampering, administrator boundaries, and role escalation. |

## Architecture and access model

- The application separates API routes, SQLAlchemy models, request/response schemas, security helpers, and static web assets.
- Alembic manages schema changes; the application does not create production tables implicitly on startup.
- Public registration always creates a regular member. An administrator is created through the local operator command.
- `admin` is a global account role. Document ownership belongs to the member who uploaded that document. Other members receive Read or Edit access through document-specific grants.
- The backend reloads the account on authenticated requests and checks live grant state, so disabling an account or revoking a grant affects subsequent requests immediately.
- Uploaded files use random internal names and remain in `private_storage/`, outside the public static directory. The upload allowlist is PDF, DOCX, and UTF-8 TXT, with a configurable 10 MB default limit.
- The browser keeps the short-lived access token in `sessionStorage`. For production use, configure a hardened cookie-based session or equivalent browser token protections.

## Requirements

- Python 3.11 or later
- MySQL 8.x (or a compatible MySQL server)
- VS Code with the Python extension (recommended)

## Local development

Open this project folder in VS Code. In its integrated PowerShell terminal, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`. Set `DATABASE_URL` to a MySQL account/database available on your machine and replace `JWT_SECRET` with a random secret of at least 32 characters. For example, generate a local secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `.env`. Do not commit `.env` or use the example credentials outside a disposable local setup.
Set `AUDIT_HMAC_KEY` to a second random value of at least 32 characters and keep it stable and outside the database. If omitted, local development derives a separate-purpose key from `JWT_SECRET`; production should set a dedicated key and preserve it for verifying existing records.

If dependencies change in a later project phase, reactivate `.venv` and run `pip install -r requirements.txt` again. `python-multipart` supports FastAPI upload forms.

Create a database and a least-privilege local account in MySQL (change the sample password):

```sql
CREATE DATABASE trustvault CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'trustvault'@'127.0.0.1' IDENTIFIED BY 'replace-with-a-local-password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP ON trustvault.* TO 'trustvault'@'127.0.0.1';
```

Use the same username/password and host in `DATABASE_URL`. Then apply the schema and start the server:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

For a deployed environment, use a separate schema-migration account in `MIGRATION_DATABASE_URL` and keep `DATABASE_URL` as the app's runtime account. Grant the runtime account only the DML each table needs. The current audit writer inserts an event and then updates its `event_hash`, so it requires `SELECT, INSERT, UPDATE(event_hash)` on `audit_events`, plus `SELECT` and column-level `UPDATE(last_event_id,last_hash)` on `audit_chain_state`. This is a narrow privilege, but it means the table is not strictly append-only at the database-permission layer. HMAC verification can detect changes without the signing key; a future strict append-only design should remove this update requirement. The runtime account also needs `SELECT, INSERT, UPDATE` on `share_suggestions`. Do not grant `DELETE` on `audit_events`, or `INSERT`/`DELETE` or update access to other `audit_chain_state` fields. Migrations `0004` and `0005` create their security and suggestion tables. Apply Alembic with the migration account, then run the server with the least-privilege runtime account.

For example, after migration, grant the runtime account access to the new table (replace the database and account names for your host):

```sql
GRANT SELECT, INSERT, UPDATE ON railway.share_suggestions TO 'trustvault_app'@'%';
```

Open <http://127.0.0.1:8000/> for the sign-in page, <http://127.0.0.1:8000/docs> for the API, and <http://127.0.0.1:8000/health> for the process health endpoint.

## API reference

Interactive OpenAPI documentation is available at `/docs` when the application is running. All protected endpoints require `Authorization: Bearer <access_token>`.

### Authentication

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Register a regular member account. Passwords must contain at least 12 characters. |
| `POST` | `/api/auth/login` | Public | Verify credentials and return a short-lived JWT. |
| `GET` | `/api/auth/me` | Signed-in user | Return the current account profile. |

## Roles and document access

| Account/access | What it means |
| --- | --- |
| Administrator | A separate global role created by the local operator command. Admin status does not reveal document contents. The administrator can review audit activity at `/admin`. |
| Regular member | The role assigned at public registration. A member owns documents they upload. |
| Owner | The member who uploaded a specific document. The owner can read, edit, share, revoke, and delete that document. |
| Read access | A named registered member can see the document in “Shared with me”, view supported previews, and download it. |
| Edit access | Includes Read and allows document title/category changes and file replacement. It does not allow sharing, revoking, or deleting. |

## Document API

Document endpoints are scoped to the signed-in account. The server checks ownership or a current document grant on each request; knowing a document ID does not grant access.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/documents` | Signed-in user | Upload a PDF, DOCX, or UTF-8 TXT file using multipart form data; accepts optional `title` and `category`. |
| `GET` | `/api/documents` | Signed-in user | List and search documents the user owns. Supports `name`, `owner`, `category`, `date_from`, `date_to`, `limit`, and `offset`. |
| `GET` | `/api/documents/shared` | Signed-in user | List/search active documents shared with the user, including access level. |
| `GET` | `/api/documents/sharing-status` | Owner | List the signed-in owner's documents and active named recipients; documents without grants are shown as private. |
| `GET` | `/api/documents/{document_id}` | Owner or active Read/Edit grantee | Retrieve document metadata. |
| `GET` | `/api/documents/{document_id}/view` | Owner or active Read/Edit grantee | Preview an authorized document. |
| `GET` | `/api/documents/{document_id}/download` | Owner or active Read/Edit grantee | Download an authorized document. |
| `PATCH` | `/api/documents/{document_id}` | Owner or active Edit grantee | Update document metadata. |
| `PUT` | `/api/documents/{document_id}/file` | Owner or active Edit grantee | Replace the document file; the prior file is retained as a version. |
| `DELETE` | `/api/documents/{document_id}` | Owner | Delete the document. |
| `GET` | `/api/documents/{document_id}/permissions` | Owner | List the document's permission grants. |
| `POST` | `/api/documents/{document_id}/permissions` | Owner | Grant Read or Edit access to an existing account by email. Optional timezone-aware `expires_at`; omit it for “Until I revoke.” |
| `DELETE` | `/api/documents/{document_id}/permissions/{grant_id}` | Owner | Revoke a grant. Subsequent requests check the current database grant and are denied. |
| `GET` | `/api/documents/{document_id}/versions` | Owner or active Read/Edit grantee | List document versions. |
| `GET` | `/api/documents/{document_id}/versions/{version_id}/download` | Owner or active Read/Edit grantee | Download a version after the standard document access check. |
| `POST` | `/api/documents/{document_id}/versions/{version_id}/restore` | Owner | Restore a version as a new version, preserving the current file in history. |
| `GET` | `/api/documents/{document_id}/sharing-suggestions` | Owner | List pending suggestions based on the owner's sharing history. |
| `POST` | `/api/documents/{document_id}/sharing-suggestions` | Owner | Generate local, history-based suggestions. This feature does not read document contents or call an external AI service. |
| `POST` | `/api/documents/{document_id}/sharing-suggestions/{suggestion_id}/decision` | Owner | Approve a suggestion at Read/Edit level or dismiss it. Only approval creates a permission, and the grant is audited. |

Successful uploads, metadata/file changes, downloads/previews, deletion, and permission changes are recorded in `audit_events`. Authorization denials for document operations are also recorded. Each new event is HMAC-sealed and linked to a locked database checkpoint; `/api/admin/audit-integrity` verifies the chain. Events from before migration `0004` remain marked as legacy/unsealed. Keep the HMAC key outside MySQL. This detects database-only edits but not a fully compromised application host; production should also restrict database writer privileges and retain signed checkpoints or immutable backups off-database. The admin page shows repeated-denial alerts, audit-chain status, activity filters, and pagination.

## Administration API

Every endpoint in this section requires an administrator account. The `/admin` page is the activity dashboard; its data requests are still authorized by the API.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/overview` | Return account/document counts and seven days of daily activity. |
| `GET` | `/api/admin/activity` | Search and paginate activity. Supports `action`, `outcome`, `search`, `date_from`, `date_to`, `limit`, and `offset`. |
| `GET` | `/api/admin/audit-integrity` | Verify the HMAC audit chain and return integrity status and counts. |
| `GET` | `/api/admin/users` | List/search accounts without exposing password hashes. |
| `PATCH` | `/api/admin/users/{user_id}/status` | Disable or enable an account. Disabling blocks sign-in and revokes its inbound/outbound grants; enabling does not restore grants. The active administrator and last active administrator cannot be disabled. |

## Security tests

The automated suite uses a temporary in-memory SQLite database, so it does not alter your MySQL data:

```powershell
python -m pytest -q
```

It checks IDOR attempts across metadata, file, permission, and version routes; Read/Edit boundaries; immediate revocation and expiry; version restore ownership; file integrity; audit tamper detection; repeated-denial alerts; admin-only activity access; admin/content separation; and signup role escalation.

The storage directory is local and private for development. It is created on the first successful upload and is never mounted as a static web directory. Backups, malware scanning, and cloud storage are not implemented yet. Before public deployment, set an upload-body limit at the reverse proxy/hosting layer as well as the application file limit.

Smart sharing suggestions are based on the signed-in owner's existing active permission history and category labels. They are deliberately advisory: there is no automatic grant, no document-content analysis, and no external AI provider in this feature.

An admin can be created from the activated VS Code terminal after the database migration:

```powershell
python -m app.cli create-admin
```

The password is prompted without echoing to the terminal. The command refuses to replace an existing account.

## Deployment preparation

Set `DATABASE_URL` and a new `JWT_SECRET` (at least 32 characters) in the hosting environment, then run `alembic upgrade head`. Start the app with Uvicorn on `0.0.0.0` and the port supplied by your host. Configure `STORAGE_DIR` to a persistent private disk; local document files must not be placed in the public static folder or an ephemeral deployment filesystem. Use HTTPS and a production MySQL service. This repository is ready for deployment configuration, but you still need to choose a host, configure its secrets/storage, and publish it to receive a live website URL.

## Configuration

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | API title |
| `ENVIRONMENT` | Environment label |
| `DATABASE_URL` | SQLAlchemy MySQL connection URL |
| `MIGRATION_DATABASE_URL` | Optional separate DDL-capable connection used only by Alembic migrations |
| `JWT_SECRET` | HS256 signing secret (32+ characters) |
| `AUDIT_HMAC_KEY` | Dedicated stable audit-signing secret (32+ characters); local fallback derives from JWT secret |
| `JWT_ALGORITHM` | Currently fixed to `HS256` |
| `ACCESS_TOKEN_MINUTES` | Access token lifetime (default 30 minutes) |
