# PROMPTS.md

This file records the implementation guidance used to shape TrustVault. It is a decision log, not executable configuration.

## Project brief

Build a Python edition of TrustVault from the Snovasys document management challenge. Use FastAPI, HTML/CSS/JavaScript, MySQL, SQLAlchemy, JWT authentication, and Pytest. Implement the project in stages without dropping working features. Enforce access on the server for every document operation, keep uploaded files private, stop access immediately after revocation, protect audit records, and document risks and decisions.

## Day 1 implementation decisions

- Use a modular monolith with separate API, model, schema, core/security, and web assets.
- Keep schema changes in Alembic migrations; do not create production tables implicitly at app startup.
- Hash passwords with Argon2 and use short-lived signed JWT access tokens.
- Public signup cannot set its own role. Create the first admin through a local operator command.
- Represent document ownership as a document-to-user relationship and sharing as a per-document permission grant. A user's ability to view or edit a document must come from that relationship, not a frontend flag or user-wide viewer role.
- Reload the account from the database on authenticated requests so account deactivation is effective without waiting for token expiry.
- Use a private storage directory outside the web root when uploads are implemented; persist only opaque storage identifiers in document metadata.
- Add Pytest coverage for authentication, authorization, IDOR, revocation, uploads, and audit immutability in the scheduled testing phase.

## Daily change log

### Day 1

Created the FastAPI foundation, MySQL/SQLAlchemy setup, initial Alembic migration, account registration/login/current-user endpoints, Argon2 password hashing, HS256 JWT bearer authentication, a local admin creation command, and a small browser sign-in/register page. Added setup and threat documentation. No document endpoints or file storage are present yet.

### Day 2

Added document metadata and an Alembic migration, owner-scoped upload/list/search/detail/preview/download/replace/update/delete routes, a private local storage helper, and an authenticated document workspace UI. Uploads are limited to PDF, DOCX, and UTF-8 TXT with a 10 MB default cap, random storage names, SHA-256 metadata, filename/path checks, and content-structure checks. Added `python-multipart` for multipart forms.

### Day 3

Added `document_permissions` grant history with Read/Edit access and revocation timestamps, plus an `audit_events` table. Owners share only with existing registered email addresses and can review or revoke active grants. Every metadata, preview, download, edit, replacement, delete, grant, and revoke route performs a server-side ownership/permission check using current database state. Read allows viewing/downloading; Edit also allows metadata and file changes; only owners can share, revoke, or delete. Added a Shared with me list and owner sharing dialog. Success events and document access denials are recorded. Audit rows have no update/delete API; database-level tamper resistance still depends on production database privilege separation and is a deployment hardening task. Day 4 admin activity UI and automated security tests remain outstanding and should not be described as complete until implemented and verified.

### Day 4

Added an admin-only API and `/admin` activity console with account/document/share counts, a seven-day activity chart, filters, pagination, actor/document labels, and allowed/denied results. Admin APIs require the global admin role; admins do not gain document-content access. Regular-member attempts to use admin APIs are added to the audit trail. Added an in-memory SQLite Pytest suite for IDOR boundaries, Read/Edit behavior, revocation, admin API protection, and role escalation at signup. Redesigned the member interface into separate Overview, My Documents, and Shared with Me screens with responsive navigation, library filters, recent file cards, upload guidance, and dedicated empty states. The tests run without touching the configured MySQL database. Added local test and deployment preparation instructions. A hosting account, production secrets/database/persistent storage, HTTPS configuration, and a live published URL still need to be supplied/configured by the project owner.

### 2026-11-05 — Security hardening and useful workflow upgrades

- **Prompt summary:** Harden the current TrustVault project, especially audit integrity and authorization, then add useful share expiry, file version history/restore, integrity checking, and admin security alerts without removing the existing UI or API features.
- **Produced:** Added HMAC-linked audit events and an admin-only chain verification endpoint; optional expiring grants; version snapshots, protected version download and owner-only restore; SHA-256 verification on stored file reads; repeated-denial alerts; administrator account disable/enable with grant revocation; security tests and updated threat documentation.
- **What needed review:** Existing audit rows predate the HMAC chain, so they cannot honestly be called verified. They are reported as legacy/unsealed. MySQL and SQLite can return timezone timestamps differently, so canonical audit hashing normalizes UTC and seconds. Version downloads and restores also need the same document authorization check as current-file downloads.
- **What I checked/fixed:** Kept the chain key outside MySQL (with a local compatibility fallback), linked each event to a locked chain-head row in the event transaction, migration-stamped the exact legacy audit cutoff/count, normalized UTC timestamps before hashing, scoped version IDs to the requested document, checked live grants including expiry, and verified file bytes before serving/restoring. A clean SQLite migration with legacy audit/document rows and version backfill, Python/JavaScript syntax checks, and all 13 Pytest security tests passed. Pytest needed `--basetemp outputs/pytest-tmp` because the sandbox's default temp directory is not writable.
- **Commit link:** Add the GitHub commit URL here after this change is uploaded and committed. This workspace has no Git remote metadata, so no commit URL is available to record yet.

## Reference review

### TrustVault Java reference

Reviewed the supplied `TrustVault-master.zip` as a behavior and documentation reference only; no Java source was copied. Its README describes registration, administrator/owner/viewer roles, document management, sharing and revocation, audit activity, and a Gemini assistant. Its own documentation identifies upload/download validation and comprehensive authorization testing as unfinished or requiring further verification.

For the Python edition, prioritize complete server-side document authorization, private and validated file handling, immediate revocation, useful audit records, and automated tests that demonstrate the boundaries. Keep AI integration out of scope unless the required security flows are finished and there is time to implement and verify it responsibly.
