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
