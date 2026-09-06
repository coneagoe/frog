# Shared Monitor Target Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated `/monitor` console and API for shared manual monitor-target CRUD and enable/disable operations.

**Architecture:** Dedicated storage methods make `workflow IS NULL` an atomic predicate for every console read and mutation. A restricted storage adapter gives that capability to `MonitorTargetService`, retaining its validation authority and leaving CLI, scheduling, generic storage, and workflow pause/resume unchanged. The Next.js console uses the existing proxy and CSRF mechanism.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/SQLite, Next.js, React, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-06-shared-monitor-target-console-design.md`

## Global Constraints

- Only targets with `workflow is None` are accessible from this API and console.
- Do not change database schema, migrations, CLI, scheduler, workflow pause/resume, ownership, tenancy, or recipient routing.
- Provide list/filter/create/edit/enable-disable/permanent-delete. Do not provide pause/resume.
- Browser writes use existing CSRF validation; bearer-token compatibility remains available through existing authentication.
- `MonitorTargetService` remains authoritative for detailed condition validation.
- Use `uv run` for Python and `tools/run_tests.sh` for PostgreSQL-dependent tests.

---

## File Structure

- `monitor/domain_enums.py`, `monitor/condition_validation.py`: condition enum and existing validation integration.
- `storage/storage_db.py`: atomic manual-only persistence operations.
- `monitor/monitor_target_service.py`: validated market and condition-type filters.
- `paper_trading/api/monitor_target_storage.py`: restricted storage adapter.
- `paper_trading/schemas/monitor_targets.py`: request/response contracts.
- `paper_trading/api/routers/monitor_targets.py`, `paper_trading/api/app.py`: protected API and router registration.
- `test/storage/test_forecast_ssf_candidate_storage.py`, `test/monitor/test_monitor_target_service.py`, `test/paper_trading/api/test_monitor_targets_api.py`: persistence, service, and API tests.
- `frontend/paper-trading/lib/types.ts`, `lib/api-client.ts`, `lib/api-error.ts`: typed client contracts and errors.
- `frontend/paper-trading/features/monitor/*`, `app/monitor/page.tsx`, `app/globals.css`: monitor UI and tests.
- `frontend/paper-trading/components/site-header.tsx`, `middleware.ts`, tests, and `docs/stock_monitor.md`: access wiring and documentation.

### Task 1: Establish manual-only persistence

**Files:**
- Modify: `monitor/domain_enums.py`, `monitor/condition_validation.py`, `storage/storage_db.py`
- Test: `test/monitor/test_condition_validation.py`, `test/storage/test_forecast_ssf_candidate_storage.py`

**Produces:** `MonitorConditionType` and dedicated manual-only methods:

```python
def list_manual_monitor_targets(
    self, *, frequency: str | None = None, enabled: bool | None = None,
    market: str | None = None, condition_type: str | None = None,
) -> list[StockMonitorTarget]: ...
def get_manual_monitor_target(self, target_id: int) -> StockMonitorTarget | None: ...
def create_manual_monitor_target(self, ...) -> StockMonitorTarget: ...
def update_manual_monitor_target(self, target_id: int, **updates: Any) -> StockMonitorTarget | None: ...
def delete_manual_monitor_target(self, target_id: int) -> bool: ...
```

- [ ] **Step 1: Write failing isolation tests**

Create manual and workflow-owned fixtures. Verify list/get/update/delete excludes workflow targets, leaves them unchanged, creation persists `workflow=None`, and frequency/enabled/market/condition-type filters compose.

```python
assert storage.get_manual_monitor_target(workflow_target.id) is None
assert storage.update_manual_monitor_target(workflow_target.id, note="blocked") is None
assert storage.delete_manual_monitor_target(workflow_target.id) is False
assert storage.get_monitor_target(workflow_target.id).note == original_note
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -k "manual_monitor_target" -v`

Expected: FAIL because scoped methods are absent.

- [ ] **Step 3: Implement enum and scoped storage**

Create `MonitorConditionType(StrEnum)` for the six existing condition strings and use it only to replace the current supported-types collection without changing semantics. Leave generic storage methods unchanged. Every new scoped list/get/update/delete query includes `StockMonitorTarget.workflow.is_(None)`; update selects the scoped row before mutation. Use portable JSON filtering:

```python
StockMonitorTarget.condition["type"].as_string() == condition_type
```

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest test/monitor/test_condition_validation.py test/storage/test_forecast_ssf_candidate_storage.py -k "manual_monitor_target or condition" -v`

Commit: `git commit -m "feat: add manual monitor target storage scope"`

### Task 2: Add service filters and storage capability adapter

**Files:**
- Modify: `monitor/monitor_target_service.py`, `test/monitor/test_monitor_target_service.py`
- Create: `paper_trading/api/monitor_target_storage.py`

**Consumes:** Task 1 manual-only storage methods.

**Produces:** Validated service list filters and an adapter limited to manual target operations.

- [ ] **Step 1: Write failing service tests**

Assert `market` and `condition_type` reach storage and invalid values return `VALIDATION_ERROR`; existing no-filter and frequency/enabled callers keep their envelopes.

```python
result = service.list_targets(market="A", condition_type="rsi")
assert result["success"] is True
storage.list_monitor_targets.assert_called_once_with(
    frequency=None, enabled=None, market="A", condition_type="rsi"
)
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest test/monitor/test_monitor_target_service.py -v`

Expected: FAIL because filters are absent.

- [ ] **Step 3: Implement filter forwarding and adapter**

Extend `list_targets()` and its public alias with optional `market` and `condition_type`, validating them through `MonitorMarket` and `MonitorConditionType`. Implement `ManualMonitorTargetStorage` with service-expected generic method names delegating exclusively to Task 1 methods. Reject non-null `condition["workflow"]` in creation with `TargetValidationError`.

```python
if condition.get("workflow") is not None:
    raise TargetValidationError("workflow-owned targets cannot be created here")
```

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest test/monitor/test_monitor_target_service.py -v`

Commit: `git commit -m "feat: scope monitor service to manual targets"`

### Task 3: Add protected monitor-target API

**Files:**
- Create: `paper_trading/schemas/monitor_targets.py`, `paper_trading/api/routers/monitor_targets.py`, `test/paper_trading/api/test_monitor_targets_api.py`
- Modify: `paper_trading/api/app.py`

**Consumes:** Task 2 adapter plus `require_browser_user` and `require_csrf`.

**Produces:** Protected endpoints at `/paper/monitor-targets`.

- [ ] **Step 1: Write failing HTTP tests**

Cover anonymous GET 401, authenticated browser GET 200, mutation without CSRF 403, bearer compatibility, manual-only list/filter/create/get/update/enable/delete, invalid condition 422, empty patch 422, note clearing, and workflow/missing ID 404 without side effects.

```python
response = client.patch(
    f"/paper/monitor-targets/{target.id}",
    headers=browser_headers_with_csrf,
    json={"note": None},
)
assert response.status_code == 200
assert response.json()["note"] is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest test/paper_trading/api/test_monitor_targets_api.py -v`

Expected: FAIL because the route is absent.

- [ ] **Step 3: Implement schemas and router**

Use existing market/frequency/reset enums, but `condition: dict[str, Any]`, and omit `workflow`/`paused` from schemas. Apply CSRF to POST, both PATCH routes, and DELETE. Use `model_dump(exclude_unset=True)` for patch so `note: null` clears notes; reject only an empty patch. Map service validation to 422 and not found to 404; delete returns 204.

```python
router = APIRouter(
    prefix="/paper/monitor-targets",
    tags=["monitor-targets"],
    dependencies=[Depends(require_browser_user)],
)
```

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest test/paper_trading/api/test_monitor_targets_api.py test/paper_trading/api/test_api_auth.py -v`

Commit: `git commit -m "feat: add protected monitor target api"`

### Task 4: Build typed frontend API contracts

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts`, `lib/api-client.ts`, `lib/api-client.test.ts`, `lib/api-error.ts`

**Consumes:** Task 3 API contract and existing `apiRequest()` behavior.

**Produces:** Typed target/condition contracts and client functions.

- [ ] **Step 1: Write failing client tests**

Assert URL/query encoding, verbs, bodies, CSRF, and that `enabled=false` is retained.

```typescript
await listMonitorTargets({ enabled: false, market: "HK" });
expect(fetch).toHaveBeenCalledWith(
  "/api/paper/monitor-targets?market=HK&enabled=false",
  expect.anything(),
);
```

- [ ] **Step 2: Run to confirm failure**

Run from `frontend/paper-trading`: `npm test -- lib/api-client.test.ts`

Expected: FAIL because monitor methods are absent.

- [ ] **Step 3: Implement types and client functions**

Create six-variant discriminated `MonitorCondition`, `MonitorTarget`, and list/create/update input types. Implement list/create/get/update/set-enabled/delete against `/api/paper/monitor-targets`, reusing `apiRequest()`. Extend error parsing for FastAPI string, object, and Pydantic-array `detail` payloads.

- [ ] **Step 4: Verify and commit**

Run from `frontend/paper-trading`: `npm test -- lib/api-client.test.ts`

Commit: `git commit -m "feat: add monitor target api client"`

### Task 5: Implement monitor feature UI

**Files:**
- Create: `frontend/paper-trading/app/monitor/page.tsx`, `features/monitor/condition-editor.tsx`, `features/monitor/monitor-target-form-modal.tsx`, `features/monitor/monitor-target-table.tsx`, `features/monitor/monitor-page.tsx`
- Test: `features/monitor/condition-editor.test.tsx`, `features/monitor/monitor-target-form-modal.test.tsx`, `features/monitor/monitor-page.test.tsx`
- Modify: `frontend/paper-trading/app/globals.css`

**Consumes:** Task 4 typed client and existing account-page UI conventions.

**Produces:** Filterable manual-target console with no workflow or pause controls.

- [ ] **Step 1: Write failing feature tests**

Test all six condition payloads, A/daily-only `close_cross_ma`, create/edit/note clearing, four filters, enable/disable refresh, confirmed delete, mutation error preservation, stale response protection, and no pause/resume control.

```tsx
render(<MonitorPage />);
await user.click(screen.getByRole("button", { name: /disable/i }));
expect(setMonitorTargetEnabled).toHaveBeenCalledWith(17, false);
expect(screen.queryByText(/pause/i)).not.toBeInTheDocument();
```

- [ ] **Step 2: Run to confirm failure**

Run from `frontend/paper-trading`: `npm test -- features/monitor/condition-editor.test.tsx features/monitor/monitor-target-form-modal.test.tsx features/monitor/monitor-page.test.tsx`

Expected: FAIL because feature files are absent.

- [ ] **Step 3: Implement editor, dialog, table, and page**

Switching condition types replaces the whole condition with deterministic defaults. Restrict `close_cross_ma` to `market === "A" && frequency === "daily"`; prevent invalid submission after scope changes. Add four filters, Create/Refresh/Edit/Enable/Disable/Delete actions, loading/empty/error states, request ID or cancellation to suppress stale responses, and permanent-delete confirmation. After successful mutations reload current filters; retain rows after errors and disable only the in-flight action.

- [ ] **Step 4: Add responsive scope-contained styles**

Add only monitor-specific CSS for controls, table actions, status, dialog, loading, and empty views; preserve existing console design patterns.

- [ ] **Step 5: Verify and commit**

Run the Task 5 test command.

Commit: `git commit -m "feat: add monitor target console"`

### Task 6: Wire shell, document, simplify, and verify

**Files:**
- Modify: `frontend/paper-trading/components/site-header.tsx`, `app/layout.test.tsx`, `middleware.ts`, `middleware.test.ts`, `app/api/paper/[...path]/route.test.ts`, `docs/stock_monitor.md`

**Consumes:** Task 5 page and generic proxy.

**Produces:** Discoverable protected route, regression coverage, and documented scope.

- [ ] **Step 1: Write failing navigation/proxy tests**

Assert Monitor link, anonymous redirect to `/login?return_to=%2Fmonitor`, authenticated pass-through, and proxy forwarding monitor query strings, cookie, PATCH/DELETE, and CSRF.

- [ ] **Step 2: Run to confirm failure**

Run from `frontend/paper-trading`: `npm test -- app/layout.test.tsx middleware.test.ts "app/api/paper/[...path]/route.test.ts"`

Expected: FAIL because monitor shell wiring is absent.

- [ ] **Step 3: Wire and document**

Add `<Link href="/monitor">Monitor</Link>`, `/monitor` protected prefix, and `/monitor/:path*` matcher. Do not create another proxy. Document authenticated manual-only scope, filtering/CRUD/enable-disable, workflow target isolation, and intentional absence of pause/resume.

- [ ] **Step 4: Run targeted verification**

Run: `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/paper_trading/api/test_monitor_targets_api.py -v`

Run: `tools/run_tests.sh test/storage/test_forecast_ssf_candidate_storage.py -k "manual_monitor_target" -v`

Run from `frontend/paper-trading`: `npm test -- lib/api-client.test.ts features/monitor/condition-editor.test.tsx features/monitor/monitor-target-form-modal.test.tsx features/monitor/monitor-page.test.tsx app/layout.test.tsx middleware.test.ts "app/api/paper/[...path]/route.test.ts" && npm run lint && npm run build`

- [ ] **Step 5: Run mandatory simplification review**

Invoke `simplify`; review only issue-touched code and apply only behavior-preserving, scope-contained clarity changes. Record no safe simplification if none is found.

- [ ] **Step 6: Run final gates and commit**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pre-commit run --all-files && tools/run_tests.sh`

Commit: `git commit -m "docs: document monitor console access"`
