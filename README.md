# TrustVault — Python Edition

TrustVault is a secure document management and sharing application built with FastAPI, SQLAlchemy, MySQL, JWT authentication, and an HTML/CSS/JavaScript interface. It provides registration, private document upload and search, per-document Read/Edit sharing with optional expiry, file version history, integrity-checked downloads, immediate revocation, and a tamper-evident activity chain.

The member interface separates the workspace overview, owned document library, outgoing shares, and incoming shared documents into dedicated responsive screens. The sign-in, member workspace, and administrator activity console share a dark blue theme. Owners can see which files are private, who has an active grant, and each recipient's Read/Edit level from “Shared by me.”

## Day 1 architecture decisions

- The backend is a modular FastAPI application. Routes, models, schemas, security helpers, and database configuration have separate modules.
- SQLAlchemy 2.x is used for database access and Alembic owns schema changes. The app does not silently create tables on startup.
- Passwords are hashed with Argon2. Raw passwords are never written to the database.
- JWTs are short-lived bearer access tokens. Protected routes validate the token and reload the user from MySQL on each request, so disabled accounts stop working immediately.
- Public registration always creates a member account. Admin accounts are created through a local operator command, never from a client-supplied role.
- `admin` is a global account role. Document ownership will be represented by the document's `owner_id`; read/edit access for other users will be document-level grants. This makes the effective owner/viewer/editor relationship specific to each document.
- The Day 1 browser page stores its short-lived token in `sessionStorage` for the demo flow. Later production deployment should use a carefully configured secure cookie or a dedicated frontend/backend origin with an explicit token lifecycle and CSP.
- Documents are stored under randomly generated names in `private_storage/`, which is outside the public static directory and excluded from Git. Original filenames are metadata only.
- The upload allowlist is PDF, DOCX, and UTF-8 TXT, with a 10 MB default limit. The backend checks file structure/content and does not trust the browser's MIME type.
- Document access is checked against the current owner or active per-document grant on every request. Owners can share with registered accounts. Read grants permit metadata/view/download; Edit also permits metadata changes and file replacement. Only the owner can grant/revoke access or delete a document. A non-owner without access receives the same 404 as a missing document.

## Requirements

- Python 3.11 or later
- MySQL 8.x (or a compatible MySQL server)
- VS Code with the Python extension (recommended)

## Run locally in VS Code

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

For a deployed environment, use a separate schema-migration account in `MIGRATION_DATABASE_URL` and keep `DATABASE_URL` as the app's runtime account. Grant the runtime account only the DML each table needs; specifically, allow `SELECT, INSERT` on `audit_events` and `SELECT` plus column-level `UPDATE(last_event_id,last_hash)` on `audit_chain_state`. Do not grant runtime `UPDATE`/`DELETE` on `audit_events`, or `INSERT`/`DELETE` or update access to the legacy checkpoint fields on `audit_chain_state`. Migration `0004` creates and seeds the singleton state row. Apply Alembic with the migration account, then run the server with the least-privilege runtime account.

Open <http://127.0.0.1:8000/> for the sign-in page, <http://127.0.0.1:8000/docs> for the API, and <http://127.0.0.1:8000/health> for the process health endpoint.

## Authentication API

- `POST /api/auth/register` — create a member account; password must be at least 12 characters.
- `POST /api/auth/login` — validate credentials and return a short-lived JWT.
- `GET /api/auth/me` — return the authenticated user's account; requires `Authorization: Bearer <token>`.

## Roles and document access

| Account/access | What it means |
| --- | --- |
| Administrator | A separate global role created by the local operator command. Admin status does not reveal document contents. The administrator can review audit activity at `/admin`. |
| Regular member | The role assigned at public registration. A member owns documents they upload. |
| Owner | The member who uploaded a specific document. The owner can read, edit, share, revoke, and delete that document. |
| Read access | A named registered member can see the document in “Shared with me”, view supported previews, and download it. |
| Edit access | Includes Read and allows document title/category changes and file replacement. It does not allow sharing, revoking, or deleting. |

## Document API

All document routes require a bearer token. Ownership and active grants are checked in the backend. Public registration always creates a regular member; users own files they upload and can be readers/editors of files shared with them.

- `POST /api/documents` — upload a PDF, DOCX, or UTF-8 TXT file as multipart form data; optional `title` and `category` fields.
- `GET /api/documents` — list/search the current user's documents. Optional filters: `name`, `owner`, `category`, `date_from`, and `date_to`; results are paginated with `limit` and `offset`.
- `GET /api/documents/{id}` — retrieve document metadata.
- `GET /api/documents/shared` — list/search active documents shared with the signed-in member, including access level.
- `GET /api/documents/sharing-status` — list the signed-in owner's documents with active recipient names and Read/Edit levels; documents without active grants are shown as private. It never lists another owner's documents.
- `GET /api/documents/{id}/view` and `/download` — preview/download after an owner or active Read/Edit grant check.
- `PATCH /api/documents/{id}` and `PUT /api/documents/{id}/file` — update metadata or replace a file as owner or Edit grantee.
- `DELETE /api/documents/{id}` — delete only as the owner.
- `GET/POST /api/documents/{id}/permissions` — owner lists grants or shares with an existing account by email at Read/Edit level.
- `POST /api/documents/{id}/permissions` accepts optional timezone-aware `expires_at`; expired grants are denied on the next request and removed from the recipient's shared list.
- `DELETE /api/documents/{id}/permissions/{grant_id}` — owner revokes a grant. Checks use the live database grant, so the next request is denied.
- `GET /api/documents/{id}/versions` and `GET /api/documents/{id}/versions/{version_id}/download` — list or download a version after the normal document access check.
- `POST /api/documents/{id}/versions/{version_id}/restore` — owner-only restore; it creates a new version so the current file remains recoverable.

Successful uploads, metadata/file changes, downloads/previews, deletion, and permission changes are recorded in `audit_events`. Authorization denials for document operations are also recorded. Each new event is HMAC-sealed and linked to a locked database checkpoint; `/api/admin/audit-integrity` verifies the chain. Events from before migration `0004` remain marked as legacy/unsealed. Keep the HMAC key outside MySQL. This detects database-only edits but not a fully compromised application host; production should also restrict database writer privileges and retain signed checkpoints or immutable backups off-database. The admin page shows repeated-denial alerts, audit-chain status, activity filters, and pagination.

## Admin activity API

- `GET /api/admin/overview` — administrator-only counts and seven days of daily activity.
- `GET /api/admin/activity` — administrator-only activity list. Optional filters: `action`, `outcome`, `search`, `date_from`, `date_to`, `limit`, and `offset`.
- `GET /api/admin/audit-integrity` — administrator-only HMAC-chain verification summary; returns integrity status and counts, never event contents.
- `GET /api/admin/users` — administrator-only account list/search; exposes no password hashes.
- `PATCH /api/admin/users/{id}/status` — administrator-only account disable/enable. Disabling blocks sign-in immediately and revokes inbound and outbound grants; re-enabling does not restore them. The active admin cannot disable themself or the last active admin.
- `/admin` — administrator activity dashboard. The HTML page itself contains no privileged data; its API requests still require an administrator token.

## Security tests

The automated suite uses a temporary in-memory SQLite database, so it does not alter your MySQL data:

```powershell
python -m pytest -q
```

It checks IDOR attempts across metadata, file, permission, and version routes; Read/Edit boundaries; immediate revocation and expiry; version restore ownership; file integrity; audit tamper detection; repeated-denial alerts; admin-only activity access; admin/content separation; and signup role escalation.

The storage directory is local and private for development. It is created on the first successful upload and is never mounted as a static web directory. Backups, malware scanning, and cloud storage are not implemented yet. Before public deployment, set an upload-body limit at the reverse proxy/hosting layer as well as the application file limit.

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
