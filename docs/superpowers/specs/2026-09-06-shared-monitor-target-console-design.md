# Shared Monitor Target Console Design

## Purpose

Issue #96 adds a protected console for managing the shared, manually created
stock-monitor targets. It must not change ownership, tenancy, recipient
routing, scheduled monitoring, CLI behavior, or workflow-owned targets.

## Scope

Authenticated users can list, filter, create, edit, enable or disable, and
permanently delete shared targets whose `workflow` field is `None`.

The console does not expose pause or resume controls. Existing workflow-only
pause and resume behavior remains unchanged and is not surfaced in this UI.

## Backend

Add a monitor-target FastAPI router to the paper-trading API and register it
from `paper_trading/api/app.py`. Its endpoints use the existing browser-user
authentication dependency. POST, PATCH, and DELETE endpoints also use the
existing CSRF dependency.

The router calls `MonitorTargetService` and shared storage directly, rather
than account-scoped paper-trading repositories. API list queries return only
targets with `workflow is None`. Lookup, update, enable/disable, and deletion
must reject workflow-owned targets, preventing the console from mutating data
owned by scheduled workflows.

The service remains the authority for condition validation and its existing
response codes. The HTTP layer maps validation failures to 422, missing or
excluded targets to 404, unauthenticated reads to 401, and invalid browser
CSRF mutations to 403. Existing bearer-token compatibility remains intact.

No existing CLI, scheduler, storage schema, or workflow pause/resume endpoint
is modified by this work.

## Frontend

Add a protected `/monitor` page to the Next.js console. Extend the existing
typed API client and type definitions for monitor-target requests, responses,
conditions, and filter values. The existing generic paper API proxy continues
to forward cookies, CSRF headers, and the required HTTP verbs.

The page presents only manual shared targets. It supports filtering by market,
frequency, enabled state, and condition type; creation and editing; an
enable/disable action; and a confirmed permanent-delete action. It has no
workflow target view and no pause/resume action.

The condition editor limits obvious invalid combinations where practical, but
surfaces backend validation errors as the final source of truth. In particular,
`close_cross_ma` remains limited to daily A-share targets under the existing
service rules.

Add a Monitor link to the site header and protect `/monitor` through the
existing middleware route policy.

## Data Flow and Isolation

Browser -> Next.js generic proxy -> authenticated FastAPI monitor router ->
`MonitorTargetService` -> shared monitor-target storage.

The router boundary enforces manual-target isolation. The service owns target
and condition validation. The frontend renders typed data and does not infer
authorization or workflow ownership from client state.

## Error Handling

- Anonymous access is rejected by the existing authentication dependency.
- Browser mutations without a valid CSRF token are rejected by the existing
  CSRF dependency.
- Invalid target inputs preserve service validation details and return 422.
- Missing targets and workflow-owned targets requested through this manual-only
  API return 404.
- Client-side mutation failures remain visible and leave the current target
  list intact until a successful reload or optimistic reconciliation.

## Verification

Add focused backend API tests for authentication, CSRF, manual-only list and
mutation isolation, create/update/delete, enable/disable, and validation error
mapping. Preserve and run the existing service and condition-validation tests.

Add frontend tests for navigation, `/monitor` route protection, and monitor
page loading and mutation behavior. Run the frontend test, lint, and build
commands. Run targeted Python checks first, then appropriate repository-wide
format, lint, type, and integration checks after the final implementation.
