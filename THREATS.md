# TrustVault threat model

This threat model tracks the account, document, sharing, audit, and admin activity features implemented so far.

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
- New audit events include an HMAC over canonical event fields and the previous event hash; a locked singleton chain-head row is updated in the same transaction. The admin-only verification endpoint detects event edits, deletion/reordering, and checkpoint mismatch when the HMAC secret remains outside MySQL.
- Events present before migration `0004` remain explicitly reported as legacy/unsealed and are not retroactively claimed as verified.
- Migration `0004` records the exact legacy audit-row cutoff and count. The runtime DB role must not update those checkpoint fields; verification flags unsealed rows beyond the cutoff or a changed legacy count.
- HMAC is tamper-evident, not a defense against a compromised application host that can read the secret. Production separates the DDL-capable migration account from the runtime account; the runtime account receives no `UPDATE` or `DELETE` on `audit_events`, and can update only the rolling head columns in `audit_chain_state`. The migration-stamped legacy cutoff/count fields are immutable to the runtime account. Keep signing secrets outside MySQL and retain off-database signed checkpoints or immutable backups to detect full-ledger deletion by a database administrator.
- Each uploaded/replaced/restored file receives a numbered immutable snapshot. Downloads and restores compare bytes with the recorded SHA-256 before serving or restoring.
- Permission grants can expire. Every access and listing query checks current expiration and revocation state; no scheduled cleanup job or stale cache is needed to end access.
- Admin account disablement immediately blocks future requests because auth reloads the active account each time. It revokes grants the account received and grants it issued; re-enabling does not restore permissions. The last active administrator and the current admin cannot be disabled.

## Day 4 admin and verification controls

- Admin overview and activity APIs require the global admin role on the server. A regular member's attempt is denied and logged; an admin still cannot read document contents without an explicit document relationship.
- The admin page renders text with DOM `textContent`, paginates audit activity, and filters by actor/document search, action, outcome, and dates. It contains no privileged data without API access.
- Pytest uses an isolated in-memory SQLite database and verifies IDOR rejection, Read/Edit boundaries, revocation, admin role enforcement, admin/content separation, and signup role escalation.
- The audit UI is read-only. Audit rows have no edit/delete API, but a database administrator or compromised DB credential can still alter them; production should separate migration, application, and audit database privileges.
- The admin overview alerts when one account causes at least five denied events in one hour. This is a basic signal, not a full intrusion-detection system; alert delivery, source-IP analysis, and rate limiting remain future work.

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
| Insecure file exposure / IDOR | Routes check current ownership/grants for metadata and file operations, use random private storage names, and return 404 for users without access. Automated tests cover the main access boundaries and immediate revocation. |
| Audit tampering | New events are HMAC-chained. A least-privilege runtime account cannot update/delete audit rows; verification also detects changes made by a DB-only writer who lacks the HMAC secret. A DBA can still remove an entire ledger and its checkpoint; use off-database signed checkpoints/immutable backups. |
| Audit event edits or deletion | New events are HMAC-chained to a secret kept outside MySQL; the admin verification endpoint flags tampering. Pre-upgrade events are unsealed. A privileged host attacker can still erase the database and chain state; retain off-database signed checkpoints or immutable backups in production. |
| Audit key rotation | Changing `AUDIT_HMAC_KEY` makes earlier HMACs fail verification. Keep the key stable and backed up separately; key rotation needs a versioned keyring/migration plan before use. |
| Expired permission still works | Every document lookup and shared-document search filters grants by current expiry and revocation state. Tests cover expiration without relying on a cleanup job. |
| Departing user retains access | Admin account disablement rejects the next authenticated request and revokes grants where the person was recipient or grantor. Re-enable does not recreate grants. |
| Stored file changed outside the app | The app hashes file bytes on upload and verifies SHA-256 on download, version download, and restore. A mismatch is denied and audited. |
| Accidental overwrite | Replacements and restores create numbered snapshots. Restoring a prior file creates a new version and leaves newer snapshots recoverable. |

## Security assumptions

- The local development machine and MySQL service are trusted and access-controlled.
- HTTPS will be enabled before deployment outside localhost.
- Deployment secrets will be supplied by the hosting environment, not packaged into the repository.
- This development build still needs production database privilege separation, HTTPS, persistent private storage, off-database audit checkpoints, and deployment-specific configuration before it should be treated as production-ready.
