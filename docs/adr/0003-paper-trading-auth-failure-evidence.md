# ADR 0003: Paper-trading authentication failure evidence

- **Status:** Accepted
- **Date:** 2026-09-17
- **Issue:** #111

## Decision

Keep browser-visible authentication failures in a small, stable set of generic
responses, while recording separate server-side/deployment diagnostic evidence
available to the same project user through deployment logs.
Credential, account-state, and rate-limit failures therefore do not reveal which
condition occurred; dependency, configuration, and proxy failures are exposed
only as service unavailability. Session invalidation is a protected-endpoint
contract, not a login-error contract.

Interpret “single-user” as one application user without roles, permissions, or a
second identity/approval model. The distinction needed here is only between the
browser response and diagnostic evidence owned by the deployment.

## Rationale

Stable browser responses prevent account enumeration and avoid turning
operational details into an attack oracle. Structured, sanitized server evidence
still lets the same project user distinguish invalid credentials, rate limiting,
dependency/configuration faults, proxy misrouting, and invalid sessions. Keeping
the evidence out of a new database table, file, or metric avoids creating a
second retention and privacy system; one-line stdout remains compatible with
deployment log collection.

## Rejected alternatives

* **Different login messages or status details:** rejected because nonexistent,
  unverified, and invalid accounts must remain indistinguishable.
* **Request IDs on rejected login responses:** rejected because rejected login
  cases intentionally have no correlation identifier or retry hint.
* **A role/permission or operator identity model:** rejected because this is a
  single-user product and adds authorization semantics unrelated to evidence.
* **Persisting evidence in application tables/files or adding metrics:** rejected
  because deployment-owned structured logs provide the required retention without
  expanding the sensitive-data surface.
