# TrustVault — Python Edition

TrustVault is a secure document management and sharing application built with FastAPI, SQLAlchemy, MySQL, JWT authentication, and an HTML/CSS/JavaScript interface. It provides registration, private document upload and search, per-document Read/Edit sharing, revocation, and an activity record for document and permission actions.

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

Open <http://127.0.0.1:8000/> for the sign-in page, <http://127.0.0.1:8000/docs> for the API, and <http://127.0.0.1:8000/health> for the process health endpoint.

## Authentication API

- `POST /api/auth/register` — create a member account; password must be at least 12 characters.
- `POST /api/auth/login` — validate credentials and return a short-lived JWT.
- `GET /api/auth/me` — return the authenticated user's account; requires `Authorization: Bearer <token>`.

## Roles and document access

| Account/access | What it means |
| --- | --- |
| Administrator | A separate global role created by the local operator command. Admin status does not reveal document contents. The activity dashboard is planned for Day 4. |
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
- `GET /api/documents/{id}/view` and `/download` — preview/download after an owner or active Read/Edit grant check.
- `PATCH /api/documents/{id}` and `PUT /api/documents/{id}/file` — update metadata or replace a file as owner or Edit grantee.
- `DELETE /api/documents/{id}` — delete only as the owner.
- `GET/POST /api/documents/{id}/permissions` — owner lists grants or shares with an existing account by email at Read/Edit level.
- `DELETE /api/documents/{id}/permissions/{grant_id}` — owner revokes a grant. Checks use the live database grant, so the next request is denied.

Successful uploads, metadata/file changes, downloads/previews, deletion, and permission changes are recorded in `audit_events`. Authorization denials for document operations are also recorded. The application exposes no API for editing or deleting audit rows. The administrative activity screen and automated security tests are planned for Day 4.

The storage directory is local and private for development. It is created on the first successful upload and is never mounted as a static web directory. Backups, malware scanning, and cloud storage are not implemented yet. Before public deployment, set an upload-body limit at the reverse proxy/hosting layer as well as the application file limit.

An admin can be created from the activated VS Code terminal after the database migration:

```powershell
python -m app.cli create-admin
```

The password is prompted without echoing to the terminal. The command refuses to replace an existing account.

## Current scope and next steps

Day 1 covers setup and authentication. Day 2 covers private upload, validation, owner management, and search. Day 3 adds document sharing, revocation, backend permission checks, and audit records. Day 4 is reserved for the admin activity view, security-focused automated tests, cleanup, and deployment preparation. Upload validation is an application-level allowlist and content check; it is not a malware scanner. Apply migrations after updating the code: `alembic upgrade head`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | API title |
| `ENVIRONMENT` | Environment label |
| `DATABASE_URL` | SQLAlchemy MySQL connection URL |
| `JWT_SECRET` | HS256 signing secret (32+ characters) |
| `JWT_ALGORITHM` | Currently fixed to `HS256` |
| `ACCESS_TOKEN_MINUTES` | Access token lifetime (default 30 minutes) |
