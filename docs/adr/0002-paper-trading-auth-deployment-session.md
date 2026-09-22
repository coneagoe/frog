# ADR 0002: Paper-trading authentication deployment and session consistency

- **Status:** Accepted
- **Date:** 2026-09-16
- **Issue:** #108

## Decision

Expose paper-trading browser access only through one stable HTTPS origin at the
Next.js frontend, with FastAPI private behind it. Run stateless, non-sticky
frontend and backend replicas that share PostgreSQL, Redis, and a centrally
managed JWT key set. Browser sessions remain one-hour, host-only cookie JWTs;
logout and password reset atomically revoke all sessions for the user.

Use a remotely managed Cloudflare Tunnel with redundant connectors per network
location, but keep application identity in the paper-trading service. Enforce
explicit ingress/Host trust, same-origin browser access, strict Origin plus CSRF
for browser writes, configuration/readiness gates, N/N-1 auth-release
compatibility, and automatic rollback on failed authentication rollout checks.

## Rationale

The existing same-origin proxy and database-backed session version support
replica-independent authorization without exposing the API or widening Cookie
scope. Central configuration, key overlap, readiness checks, and end-to-end
cross-replica validation prevent a rolling deploy or Tunnel restart from
turning configuration drift into intermittent browser authentication failures.

## Rejected alternatives

* **Public FastAPI or browser CORS:** rejected because it adds a second browser
  origin and weakens the existing Cookie/CSRF boundary.
* **Sticky sessions or single replica:** rejected because correctness would
  depend on routing and future scale-out would change authentication semantics.
* **Cloudflare Access as a second user identity system:** rejected because it
  duplicates application login, logout, recovery, and session semantics.
* **Local per-host `.env` configuration:** rejected because it cannot prove
  replica consistency or support auditable, safe secret rotation.
