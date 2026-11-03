# TrustVault threat model

This threat model tracks the account, document, sharing, and audit features implemented so far. The admin activity dashboard and automated security tests are planned for Day 4.

## Assets

- User email addresses and profile names.
- Password verifiers (Argon2 hashes), JWT signing secret, and database credentials.
- Private document contents, metadata, permission history, and audit events.
- Integrity and availability of account and role records.

## Trust boundaries

- Browser to FastAPI API: all request fields and headers are untrusted.
- FastAPI to MySQL: database credentials and SQL connections must remain private.
- Local operator terminal to the account database: admin creation is privileged.
- Environment files and source control: `.env` contains secrets and must remain untracked.

## Day 1 account controls

- Passwords are Argon2 hashed; login errors do not distinguish unknown email from a wrong password.
- Registration input is validated, email is normalized, and new public accounts are always members.
- JWTs are signed with HS256, expire after a short configured interval, and are accepted only for the expected token type and algorithm.
- Protected API requests reload the user record and reject inactive or missing accounts.
- Admin creation is local and interactive; it does not accept a role field from an HTTP request.
- MySQL table creation is migration-based. Configuration secrets are read from the environment and `.env` is ignored by Git.

## Day 2 document controls

- Only PDF, DOCX, and UTF-8 TXT are accepted, with a configurable 10 MB default limit. Extension allowlisting is combined with content/structure checks; client MIME headers are not trusted.
- Files use random internal names and live in a private directory outside the mounted static directory. Original filenames are sanitized and used only as metadata/download names.
- The backend never accepts a storage path from a request. Database storage keys are validated before opening a file.
- The browser renders document values with `textContent`; authorization remains server-side.
- Content checks do not replace antivirus scanning. A hosting proxy/body-size limit is also needed because multipart parsing may spool request data before the route applies its file-level cap.

## Day 3 sharing and audit controls

- Grants point to registered user IDs, not arbitrary client-supplied roles. A grant stores Read or Edit and a revocation timestamp; regranting creates a new grant history row.
- Every document detail, preview, download, metadata change, file replacement, and deletion route checks server-side ownership or a current grant. Read permits viewing/downloading; Edit also permits changes; only the owner can share, revoke, or delete. Admin status does not grant document content access.
- Permission state is queried from MySQL on each operation. No long-lived permission cache or signed share URL is used, so revocation blocks the next request.
- Owners receive a uniform not-found response when attempting another user's document ID. Denied document actions are committed to the audit table.
- Successful uploads, previews/downloads, metadata/file changes, deletion, and permission changes are recorded. The audit table has no update/delete API, and deletion events do not depend on the document row remaining present.
- Direct database writers can still alter audit records. Production needs a restricted audit-writer credential and monitoring/backup controls; the current local development account has broad migration privileges.
- The admin activity view and automated IDOR/revocation tests are not implemented until Day 4.

## Known risks and planned mitigations

| Threat | Current status / next control |
| --- | --- |
| Brute-force login attempts | No rate limiting yet. Add throttling/lockout policy and monitoring before public deployment. |
| JWT theft from the browser | Demo UI keeps a short-lived token in `sessionStorage`; use secure, HttpOnly, SameSite cookies with CSRF protection or a hardened separate frontend before production. |
| Weak or exposed JWT/database secrets | `.env.example` is only a template; replace values locally, restrict secret access, rotate exposed secrets, and never commit `.env`. |
| Privilege escalation at signup | Signup ignores all role input and hard-codes member status; administrator creation is an operator action. |
| Stale role/account state in a token | Only user ID is used as identity; account is reloaded per request and document authorization uses current database grants. |
| SQL injection | Use SQLAlchemy parameterized queries. Avoid raw SQL built from request strings. |
| Email enumeration | Login response is generic. Registration currently returns a duplicate-account conflict, which can disclose account existence; assess a uniform registration response or email verification before deployment. |
| Cross-site scripting | UI renders API values with `textContent`; add a restrictive Content Security Policy when deployment headers are configured. |
| Insecure file exposure / IDOR | Routes check current ownership/grants for metadata and file operations, use random private storage names, and return 404 for users without access. Automated IDOR/revocation tests are planned for Day 4. |
| Audit tampering | Successful document/permission actions and authorization denials are recorded; no user-facing update/delete route exists. Direct DB writers can still alter records until deployment uses a restricted audit-writer credential. |

## Security assumptions

- The local development machine and MySQL service are trusted and access-controlled.
- HTTPS will be enabled before deployment outside localhost.
- Deployment secrets will be supplied by the hosting environment, not packaged into the repository.
- This development build still needs Day 4 automated security tests, admin activity UI, and a deployment review before it should be treated as production-ready.
