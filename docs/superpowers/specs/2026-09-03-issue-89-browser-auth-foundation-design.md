# Issue #89 Browser Authentication Foundation

## Scope

Issue #89 delivers the first usable browser authentication path for the paper-trading
operator. It includes the backend user/session foundation and minimal login/register
screens required by the issue acceptance criteria.

The following remain follow-up responsibilities: complete email verification delivery
and registration protection (#92), password recovery and full session revocation (#90),
paper-account ownership and legacy migration (#91), complete browser proxy and protected
page integration (#93), and deployment/end-to-end configuration (#94).

## Backend Design

Add application-wide SQLAlchemy models under `storage/model/` and export them through
`storage/model/__init__.py`:

- `User`: integer ID, normalized unique email, Argon2 password hash, nullable
  `email_verified_at`, `session_version`, and creation/update timestamps.
- `AuthToken`: user ID, purpose, hash of a random token, expiry, used timestamp, and
  creation timestamp. This model establishes the single-use token boundary for #92 and
  #90; this issue does not implement mail delivery or reset flows.

Use the existing `Base.metadata.create_all` and idempotent startup schema-upgrade
pattern. Do not introduce a new migration framework. Declare the Argon2 and PyJWT
runtime dependencies explicitly.

Add authentication helpers for:

- email normalization by trimming whitespace and lowercasing;
- password validation and Argon2 hashing/verification;
- JWT creation and validation using the user ID and `session_version`;
- session and CSRF cookie construction;
- resolving a browser user from the session cookie while preserving the static Bearer
  token as a separate system credential.

The minimum password policy is 12 characters and must contain at least one letter and
one number. Validation is shared by the API and frontend rules, while the backend is
authoritative.

Register `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, and
`POST /auth/logout` in the FastAPI application.

Registration creates an unverified user, stores only the Argon2 hash, and returns a safe
response. Duplicate normalized email addresses return `409`. Mail delivery and the
verification transition are deliberately deferred to #92.

Login requires a verified user. Unknown email, incorrect password, and unverified user
all return the same generic `401` response. A successful login sets an HttpOnly session
cookie with `SameSite=Lax` and a separate readable CSRF cookie. Cookie security is
configurable for local tests and secure by default in production.

`GET /auth/me` returns only safe identity fields: user ID, normalized email, and
verification status/timestamp. Missing, malformed, expired, or session-version-invalid
cookies return `401`.

Logout invalidates the current session version and clears the session and CSRF cookies.
The versioning helper is the extension point for #90's password-reset-wide revocation.
Cookie-authenticated state-changing requests require a matching `X-CSRF-Token`; static
Bearer-token automation remains compatible and exempt from browser CSRF handling.

No account ownership behavior changes in this issue. Existing paper-trading routes and
CLI/Airflow callers continue using `Authorization: Bearer <PAPER_TRADING_API_TOKEN>`.

## Frontend Design

Add `/login` and `/register` screens using the existing Next.js and component-test
conventions. Each form provides:

- properly associated accessible labels and inputs;
- browser/backend-compatible email and password validation;
- password visibility toggle;
- submit loading state and generic server-error state;
- navigation between login and registration.

Authentication requests use same-origin frontend routes and never expose the static
paper-trading token to browser code. This issue does not protect every existing business
page or complete the browser proxy migration; those behaviors belong to #93.

## Error and Security Rules

- Never persist, serialize, or log plaintext passwords, JWTs, CSRF values, or raw auth
  tokens.
- Invalid credentials use generic wording and timing-independent lookup/verification
  behavior as far as the selected password library permits.
- Invalid session cookies fail closed.
- Configuration must reject missing production JWT secrets or insecure production cookie
  settings rather than silently weakening the session.

## Verification

Backend HTTP tests cover normalized registration, strong-password rejection, duplicate
email handling, absence of plaintext password storage, verified login, cookie attributes,
generic invalid-credential responses, `/auth/me` success and `401` behavior, logout
invalidation, CSRF enforcement, and static Bearer-token compatibility.

Frontend component tests cover accessible fields, validation, loading and error states,
password visibility, and navigation between the two screens.

The final verification path is the repository's focused paper-trading tests followed by
Ruff, mypy, and the applicable full test runner.
