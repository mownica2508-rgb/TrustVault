# TrustVault threat model

This threat model is scoped to the Day 1 account and application foundation. It will be expanded as uploads, sharing, and audit features are added.

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
| Insecure file exposure / IDOR | No file endpoints exist yet. Future document APIs must authorize every object lookup and stream only from private storage after permission checks. |
| Audit tampering or missing denied events | Audit logging is not implemented yet. Design append-only permissions and record successful and denied actions in the later audit phase. |

## Security assumptions

- The local development machine and MySQL service are trusted and access-controlled.
- HTTPS will be enabled before deployment outside localhost.
- Deployment secrets will be supplied by the hosting environment, not packaged into the repository.
- This Day 1 foundation is not production-ready until later security controls and the planned automated security tests are implemented and reviewed.
