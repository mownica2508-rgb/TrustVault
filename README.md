# TrustVault — Python Edition

TrustVault is a secure document management and sharing application built with FastAPI, SQLAlchemy, MySQL, JWT authentication, and a small HTML/CSS/JavaScript interface. This repository is being developed in stages; Day 1 delivers the project foundation, account registration, login, and authenticated identity lookup.

## Day 1 architecture decisions

- The backend is a modular FastAPI application. Routes, models, schemas, security helpers, and database configuration have separate modules.
- SQLAlchemy 2.x is used for database access and Alembic owns schema changes. The app does not silently create tables on startup.
- Passwords are hashed with Argon2. Raw passwords are never written to the database.
- JWTs are short-lived bearer access tokens. Protected routes validate the token and reload the user from MySQL on each request, so disabled accounts stop working immediately.
- Public registration always creates a member account. Admin accounts are created through a local operator command, never from a client-supplied role.
- `admin` is a global account role. Document ownership will be represented by the document's `owner_id`; read/edit access for other users will be document-level grants. This makes the effective owner/viewer/editor relationship specific to each document.
- The Day 1 browser page stores its short-lived token in `sessionStorage` for the demo flow. Later production deployment should use a carefully configured secure cookie or a dedicated frontend/backend origin with an explicit token lifecycle and CSP.

## Requirements

- Python 3.11 or later
- MySQL 8.x (or a compatible MySQL server)
- VS Code with the Python extension (recommended)

## Run locally in VS Code

Open this project folder in VS Code. In its integrated PowerShell terminal, run:

```powershell
py -3.11 -m venv .venv
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

Create a database and a least-privilege local account in MySQL (change the sample password):

```sql
CREATE DATABASE trustvault CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'trustvault'@'127.0.0.1' IDENTIFIED BY 'replace-with-a-local-password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP ON trustvault.* TO 'trustvault'@'127.0.0.1';
```

Use the same username/password and host in `DATABASE_URL`. Then apply the schema and start the server:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/> for the sign-in page, <http://127.0.0.1:8000/docs> for the API, and <http://127.0.0.1:8000/health> for the process health endpoint.

## Day 1 API

- `POST /api/auth/register` — create a member account; password must be at least 12 characters.
- `POST /api/auth/login` — validate credentials and return a short-lived JWT.
- `GET /api/auth/me` — return the authenticated user's account; requires `Authorization: Bearer <token>`.

An admin can be created from the activated VS Code terminal after the database migration:

```powershell
python -m app.cli create-admin
```

The password is prompted without echoing to the terminal. The command refuses to replace an existing account.

## Current scope and next steps

Day 1 covers setup, database configuration, registration, login, and current-user authentication. Document upload, search, document-level permissions, audit events, admin activity views, and the Pytest security suite are scheduled for later project days. No document file is currently accepted or served by this app.

## Configuration

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | API title |
| `ENVIRONMENT` | Environment label |
| `DATABASE_URL` | SQLAlchemy MySQL connection URL |
| `JWT_SECRET` | HS256 signing secret (32+ characters) |
| `JWT_ALGORITHM` | Currently fixed to `HS256` |
| `ACCESS_TOKEN_MINUTES` | Access token lifetime (default 30 minutes) |
