# TrustVault threat model

This threat model tracks the account and document features implemented so far. It will be expanded as sharing, audit, and administration features are added.

## Assets

- User email addresses and profile names.
- Password verifiers (Argon2 hashes), JWT signing secret, and database credentials.
- Integrity and availability of account and role records.

## Trust boundaries

- Browser to FastAPI API: all request fields and headers are untrusted.
- FastAPI to MySQL: database credentials and SQL connections must remain private.
- Local operator terminal to the account database: admin creation is privileged.
- Environment files and source control: `.env` contains secrets and must remain untracked.

## Day 1 controls

- Passwords are Argon2 hashed; login errors do not distinguish unknown email from a wrong password.
- Registration input is validated, email is normalized, and new public accounts are always members.
- JWTs are signed with HS256, expire after a short configured interval, and are accepted only for the expected token type and algorithm.
- Protected API requests reload the user record and reject inactive or missing accounts.
- Admin creation is local and interactive; it does not accept a role field from an HTTP request.
- MySQL table creation is migration-based. Configuration secrets are read from the environment and `.env` is ignored by Git.

## Day 2 document handling controls

- Only PDF, DOCX, and UTF-8 TXT are accepted, with a configurable 10 MB default limit. Extension allowlisting is combined with content/structure checks; client MIME headers are not trusted.
- Files use random internal names and live in a private directory outside the mounted static directory. Original filenames are sanitized and used only as metadata/download names.
- The backend never accepts a storage path from a request. Database storage keys are validated before opening a file.
- Document routes scope IDs to the authenticated owner and return 404 for non-owner access, including direct-ID requests. Downloads use attachment disposition, `nosniff`, and `private, no-store` caching. Inline previews are limited to PDF/TXT and receive a restrictive sandbox CSP.
- The browser renders document values with `textContent` and submits bearer credentials to the API; authorization remains server-side.
- The content checks do not replace antivirus scanning. Scanning, audit records, sharing, and automated IDOR/revocation tests remain future work.
- The application rejects stored file copies above its configured limit. A hosting proxy/body-size limit is also needed because multipart parsing may spool request data before the route applies its file-level cap.

## Known risks and planned mitigations

| Threat | Current status / next control |
| --- | --- |
| Brute-force login attempts | No rate limiting yet. Add throttling/lockout policy and monitoring before public deployment. |
| JWT theft from the browser | Demo UI keeps a short-lived token in `sessionStorage`; use secure, HttpOnly, SameSite cookies with CSRF protection or a hardened separate frontend before production. |
| Weak or exposed JWT/database secrets | `.env.example` is only a template; replace values locally, restrict secret access, rotate exposed secrets, and never commit `.env`. |
| Privilege escalation at signup | Signup ignores all role input and hard-codes member status; administrator creation is an operator action. |
| Stale role/account state in a token | Only user ID is used as identity; account is reloaded per request and authorization should use current database relationships. |
| SQL injection | Use SQLAlchemy parameterized queries. Avoid raw SQL built from request strings. |
| Email enumeration | Login response is generic. Registration currently returns a duplicate-account conflict, which can disclose account existence; assess a uniform registration response or email verification before deployment. |
| Cross-site scripting | Day 1 UI renders API data with `textContent`; avoid inserting untrusted strings as HTML and add a restrictive Content Security Policy when deployment headers are configured. |
| Insecure file exposure / IDOR | Day 2 routes check ownership for metadata and file operations, use random private storage names, and return 404 for non-owner IDs. Sharing-specific authorization and automated IDOR tests are still pending. |
| Audit tampering or missing denied events | Audit logging is not implemented yet. Design append-only permissions and record successful and denied actions in the later audit phase. |

## Security assumptions

- The local development machine and MySQL service are trusted and access-controlled.
- HTTPS will be enabled before deployment outside localhost.
- Deployment secrets will be supplied by the hosting environment, not packaged into the repository.
- This Day 1 foundation is not production-ready until later security controls and the planned automated security tests are implemented and reviewed.
