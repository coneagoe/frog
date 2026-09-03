# Public Authentication and Account Isolation Design

## Goals

- Add real register and login flows to the paper-trading frontend and backend.
- Prevent unauthenticated visitors from modifying paper-trading data.
- Keep browser users isolated to the securities accounts they own.
- Preserve the existing `PAPER_TRADING_API_TOKEN` contract for CLI tools, Airflow, DAGs, and curl.
- Support email verification and email-based password recovery for the public deployment.

This design does not change the mutability of existing orders, trades, cash flows,
or position-change records. Record immutability is a separate follow-up concern.

## Authentication Model

The FastAPI backend is the only trust boundary for user identity. It validates a
JWT stored in an HttpOnly cookie and obtains the user ID from the token `sub`
claim. The Next.js proxy forwards the browser cookie and does not synthesize a
user identity header.

The existing static Bearer token remains a separate system-level credential. A
request authenticated with `PAPER_TRADING_API_TOKEN` is treated as internal
automation and may access all paper-trading accounts. CLI and Airflow callers do
not need cookies, login commands, or CSRF handling.

JWTs contain the user ID and `session_version`. They expire after one day by
default. Logout and password changes increment the user's session version, which
invalidates previously issued JWTs even if a copy of one was obtained.

Authentication configuration is explicit and environment-based:

- `AUTH_JWT_SECRET`
- `AUTH_JWT_EXPIRE_MINUTES`
- `AUTH_COOKIE_SECURE`
- `AUTH_REGISTRATION_ENABLED`
- `AUTH_OWNER_EMAIL`
- `AUTH_PUBLIC_BASE_URL`
- SMTP host, port, credentials, and sender settings
- Redis connection settings for rate limiting

Production requires an HTTPS `AUTH_PUBLIC_BASE_URL` and secure cookies.

## Backend Components

Add an application-wide SQLAlchemy user model under `storage/model/`, export it
from `storage/model/__init__.py`, and register it with the shared declarative
metadata. The `users` table contains:

- integer primary key
- normalized, unique email
- Argon2 password hash
- nullable email verification timestamp
- session version
- creation and update timestamps

Add a token table for email verification and password reset flows. Store only a
hash of each random token. Each token has a purpose, user ID, expiry, used time,
and creation time. Tokens are single-use and short-lived.

Add nullable `user_id` ownership to the existing paper-trading account model.
New accounts created through a user-authenticated request receive the current
user ID. Every account-scoped read and write checks ownership, including account
CRUD, deposits and withdrawals, position imports, fee changes, orders, order
cancellation, trades, analytics, snapshots, and related account data.

Existing databases use the repository's idempotent startup schema-upgrade
pattern. Existing accounts are migrated once to the user identified by
`AUTH_OWNER_EMAIL`. Migration fails when that configured user does not exist or
when ownership cannot be assigned safely; it never silently makes old accounts
public.

Add authentication helpers for password hashing, JWT creation and validation,
cookie handling, current-user resolution, and system-token detection. Add an
`auth` router with:

- `POST /auth/register`
- `GET /auth/verify-email`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

Registration is disabled unless `AUTH_REGISTRATION_ENABLED=true`. Registration
validates a strong password, normalizes the email, creates an unverified user,
and sends a verification email. Unverified users cannot log in. Login and reset
requests use generic responses that do not reveal whether an email exists.

Passwords are hashed with an explicitly declared Argon2 library. JWT handling
uses an explicitly declared PyJWT library. Redis is used for shared rate limits,
keyed by both IP and normalized email as appropriate for registration, login,
verification mail, and password-reset mail.

## Browser and CSRF Flow

The frontend adds `/login`, `/register`, `/verify-email`, `/forgot-password`, and
`/reset-password`. Forms include accessible labels, client-side validation,
loading states, server-error states, password visibility controls, and links to
the related auth flows.

The session cookie is HttpOnly, Secure in production, scoped to the application,
and uses `SameSite=Lax`. The backend also sets a readable CSRF cookie. Browser
state-changing requests must include the matching value in `X-CSRF-Token`.
The Next.js proxy checks this pairing and forwards both the session cookie and
CSRF header to FastAPI. Bearer-token requests from CLI and internal automation
are not subject to browser CSRF checks.

The existing `/api/paper/*` proxy must stop relying on the static server token
for browser identity. It forwards the browser credentials to FastAPI, while the
static token remains available only for explicitly configured internal callers.
Unauthenticated browser API responses are `401`; protected page entry points
redirect to `/login` while preserving a safe return path.

## Password Recovery

Forgot-password requests always return the same response regardless of whether
the email exists. For an existing verified user, the backend creates a random,
single-use reset token, stores only its hash, and sends a link built from the
explicit `AUTH_PUBLIC_BASE_URL`. It must not derive links from the request Host
header. The link expires quickly and is invalidated after use.

Resetting a password replaces the Argon2 hash and increments `session_version`,
invalidating all previous browser sessions.

## Compatibility and Deployment

`tools/paper_trading_cli.py`, Airflow, DAG tasks, and documented curl examples
continue to send `Authorization: Bearer <PAPER_TRADING_API_TOKEN>`. The CLI
continues to accept `--token` and `PAPER_TRADING_API_TOKEN`; no cookie-file or
browser-login mode is required for this scope.

Docker Compose, the environment example, and paper-trading documentation must
document authentication, SMTP, Redis, public URL, and migration settings. Auth
secrets, passwords, JWTs, reset tokens, and verification links must not be
written to logs.

## Error Handling

- Invalid credentials return `401` with generic wording.
- Duplicate normalized email returns `409` during registration.
- Invalid, expired, or already-used verification/reset tokens return a safe
  client error without exposing token state details.
- Missing or invalid CSRF credentials return `403` for browser mutations.
- Redis or SMTP outages fail closed for affected auth operations and return a
  generic server error; sensitive provider details stay in server logs only.
- Missing production secrets or an unsafe public URL fail startup/configuration
  validation rather than silently weakening security.

## Testing and Acceptance

Backend tests cover registration, duplicate and weak credentials, verification,
login, logout, `/auth/me`, JWT expiry/signature/session-version invalidation,
cookie attributes, CSRF, password reset token lifecycle, SMTP failures, Redis
rate limits, and static Bearer-token compatibility.

Account authorization tests prove that a user cannot read, modify, delete, or
trade against another user's account or any derived account data. Migration tests
cover successful binding of existing accounts and failure when
`AUTH_OWNER_EMAIL` is invalid.

Frontend tests cover every auth form, redirects, generic errors, proxy cookie and
CSRF forwarding, logout, and authenticated access to existing business pages.
Existing proxy and CLI tests must continue to pass with their Bearer-token
assertions.

Deployment acceptance requires a fresh database startup, an idempotent startup
against an existing database, correct secure-cookie behavior over HTTPS, and
working CLI/Airflow authentication without browser cookies.
