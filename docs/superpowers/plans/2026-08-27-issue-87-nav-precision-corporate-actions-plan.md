# Issue #87: NAV Precision and Corporate Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the paper-trading accounting contract with 12-decimal Decimal precision, auditable cash-flow rounding residuals, transactional internal corporate actions, API and analytics audit exposure, bounded snapshot recalculation, frontend rendering, migration compatibility, and documentation.

**Architecture:** Extend the existing `PaperTradingRepository`/SQLAlchemy ledger and snapshot model rather than adding a parallel accounting store. Add a focused `CorporateActionService` that validates and applies one account/security event under account and position locks, persists an immutable audit row plus derived ledger/position changes in the caller transaction, and invokes bounded snapshot recalculation after commit. Keep analytics event-series entries auxiliary: corporate-action and cash-flow events are auditable, while only valid snapshots feed NAV metrics and charts.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL/SQLite, Pydantic v2, Decimal, pytest, Ruff, mypy, pre-commit, Next.js 15 App Router, React 19, TypeScript, Vitest, Testing Library, Playwright, Docker Compose.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3`.
- Internal NAV, share, quantity, price, and money calculations use `Decimal`.
- Persisted accounting values use 12 decimal places (`Numeric(30, 12)`); existing display formatting remains unchanged.
- Cash-flow share rounding uses the repository's explicit documented rounding mode; residual equals requested amount minus persisted share delta multiplied by effective NAV.
- Existing ledger rows receive a zero residual during migration; historical amounts and snapshots are not rewritten.
- Corporate actions are single-security events entered through the application; no external-provider synchronization is included.
- Supported corporate-action types are `dividend`, `split`, `reverse_split`, `bonus_share`, and `rights_issue`.
- A successful event and all resulting ledger/position changes commit in one transaction; invalid input, insufficient cash, invalid holdings, and idempotency conflicts roll back fully and leave no rejected business-event row.
- Replaying identical idempotency content returns the original result without applying it twice; reusing the key with different content is a conflict.
- Corporate-action timestamps must be timezone-aware, normalized to UTC for persistence and ordering, and ordered with `(event_at, id)`.
- Corporate actions do not alter external deposit/withdrawal totals or create external TWR cash-flow adjustments.
- Only valid NAV snapshots are chart points; corporate-action and other auxiliary audit events never become chart points.
- Existing display precision, legacy repair markers, snapshots, valuation gaps, analytics availability decisions, and historical financial values remain semantically unchanged unless the spec explicitly requires new derived results.
- `tools/db_common.sh` must include every new persistent table so database export/import stays synchronized.
- PostgreSQL and SQLite startup upgrades must be additive, repeatable, and preserve legacy rows; PostgreSQL enum changes must use the governed enum migration path.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLAs.
- No unrelated refactoring, automatic provider synchronization, or new persistent diagnostic surface is in scope.

## File Map

- `storage/model/paper_trading.py`
  - Widen persisted account, ledger, position/lot, order/trade, and snapshot accounting columns to `Numeric(30, 12)` where they represent NAV, shares, quantity-derived cost, price, fees, or money; add `rounding_residual` to `PaperCashLedger`; add `PaperCorporateAction` and its table/index constants.
- `paper_trading/domain/enums.py`
  - Add governed `CorporateActionType` and `CashEventType.CORPORATE_ACTION`; retain existing enum values.
- `paper_trading/domain/errors.py`
  - Add typed domain errors for idempotency conflict, invalid corporate-action input, insufficient corporate-action cash, and invalid holding state so API mapping is deterministic.
- `paper_trading/domain/precision.py`
  - Own the shared Decimal quantization constants, explicit rounding mode, finite-value validation, and persisted-value helpers used by cash flows and corporate actions.
- `paper_trading/domain/corporate_actions.py`
  - Add pure Decimal validation/calculation functions for five event types and their impact summaries.
- `paper_trading/storage/models.py`
  - Re-export `PaperCorporateAction` and its table name.
- `paper_trading/storage/repository.py`
  - Add Decimal quantization helpers, cash-flow residual persistence, locked corporate-action lookup/create/list methods, locked target-position lookup, corporate-action ledger helpers, and account deletion cleanup.
- `paper_trading/storage/enum_migration.py`
  - Govern the new corporate-action enum/event type and verify the table/index/column upgrade state.
- `storage/storage_db.py`
  - Add additive PostgreSQL/SQLite startup upgrade handling for widened precision, `rounding_residual`, and the corporate-action table while preserving existing snapshot-series and repair behavior.
- `tools/db_common.sh`
  - Add `paper_corporate_actions` to `BUSINESS_TABLES` and its enum mappings.
- `paper_trading/services/cash_service.py`
  - Use the shared precision/rounding contract and persist `rounding_residual` for deposits and withdrawals.
- `paper_trading/services/corporate_action_service.py`
  - Validate, idempotently apply, audit, and return one corporate action with accounting impact and recalculation result.
- `paper_trading/services/snapshot_recalculation_service.py`
  - Expose a bounded account/date recalculation result usable by the corporate-action service without losing explicit valuation gaps or historical event timestamps.
- `paper_trading/services/analytics_service.py`
  - Include corporate-action audit events, exclude them from external cash-flow/TWR adjustments, and preserve the valid-snapshot-only NAV series.
- `paper_trading/schemas/accounts.py`
  - Expose `rounding_residual` in `CashLedgerResponse`.
- `paper_trading/schemas/corporate_actions.py`
  - Define strict request, persisted-event, impact, recalculation, and list-response schemas with type-specific validation.
- `paper_trading/schemas/analytics.py`
  - Add the discriminated `CorporateActionAnalyticsEvent` and include it in `AnalyticsEvent`.
- `paper_trading/api/routers/corporate_actions.py`
  - Add account-scoped create/list routes and deterministic domain-error mapping.
- `paper_trading/api/app.py`
  - Include the corporate-action router and preserve startup schema bootstrap.
- `frontend/paper-trading/lib/types.ts`
  - Add corporate-action request/response, impact, recalculation, ledger residual, and analytics event types.
- `frontend/paper-trading/lib/api-client.ts`
  - Add `createCorporateAction()` and `listCorporateActions()` helpers with query filters.
- `frontend/paper-trading/features/accounts/corporate-action-modal.tsx`
  - Add a type-aware create form for dividend, split/reverse split, bonus share, and rights issue actions.
- `frontend/paper-trading/features/accounts/accounts-page.tsx`
  - Open the corporate-action modal for the selected account and refresh account/position state after success.
- `frontend/paper-trading/features/trading/trading-tables.tsx`
  - Render residuals and corporate-action ledger labels without changing existing display precision.
- `frontend/paper-trading/features/analytics/asset-chart.tsx`
  - Keep only valid snapshot events as chart points, including when the event series contains corporate-action audit events.
- `frontend/paper-trading/features/analytics/analytics-tables.tsx`
  - Render the auxiliary corporate-action audit event details.
- `frontend/paper-trading/features/analytics/analytics-page.tsx`
  - Pass the enriched event series to chart/audit UI without treating auxiliary events as snapshots.
- `docs/paper_trading.md`
  - Document precision, rounding residuals, corporate-action API/semantics, timestamps, ordering, idempotency, internal cash, valuation gaps, recalculation, and limitations.
- `docs/todo/paper_trading-nav-baseline-analysis.md`
  - Replace stale baseline conclusions with the implemented initial snapshot and corporate-action/NAV contract.
- `test/paper_trading/domain/test_corporate_actions.py`
  - Test pure Decimal event validation and impact calculations.
- `test/paper_trading/storage/test_repository.py`
  - Test widened persistence, residuals, event ordering, idempotency lookup, and deletion cleanup.
- `test/paper_trading/storage/test_corporate_action_migration.py`
  - Test PostgreSQL/SQLite additive upgrades, enum/table/index/precision changes, repeatability, rollback, and history preservation.
- `test/paper_trading/services/test_cash_service.py`
  - Test both cash-flow rounding directions and residual reconciliation.
- `test/paper_trading/services/test_corporate_action_service.py`
  - Test all event types, locks/idempotency, rollback, no-holding behavior, cost basis, and recalculation.
- `test/paper_trading/services/test_snapshot_recalculation_service.py`
  - Test event-date/later-date bounds, gaps, stale valuation metadata, and preserved event ordering.
- `test/paper_trading/services/test_analytics_service.py`
  - Test corporate-action audit events, TWR exclusion, valid snapshot-only NAV inputs, and continuity.
- `test/paper_trading/api/test_corporate_actions_api.py`
  - Test create/list schemas, filters, ordering, timezone validation, errors, impact, and recalculation responses.
- `test/paper_trading/api/test_accounts_api.py`
  - Extend cash-ledger response assertions for residuals.
- `test/paper_trading/api/test_analytics_api.py`
  - Extend analytics event-series assertions for corporate actions and chart-point invariants.
- `frontend/paper-trading/lib/api-client.test.ts`
  - Test corporate-action request encoding and list query filters.
- `frontend/paper-trading/features/accounts/corporate-action-modal.test.tsx`
  - Test each form mode, validation, submission, errors, and successful completion.
- `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
  - Test modal opening and account/position refresh after application.
- `frontend/paper-trading/features/trading/trading-tables.test.tsx`
  - Test residual and corporate-action label rendering.
- `frontend/paper-trading/features/analytics/asset-chart.test.tsx`
  - Test auxiliary events are ignored and invalid/non-snapshot events never become chart points.
- `frontend/paper-trading/features/analytics/analytics-page.test.tsx`
  - Test audit-event rendering and enriched event-series handling.

## Task 1: Establish Precision and Rounding Contracts

**Files:**
- Modify: `storage/model/paper_trading.py:84-180,312-374`
- Modify: `paper_trading/domain/enums.py:33-40`
- Create: `paper_trading/domain/precision.py`
- Modify: `paper_trading/storage/repository.py:464-509`
- Modify: `paper_trading/services/cash_service.py:9-119`
- Modify: `paper_trading/schemas/accounts.py:105-116,154-173`
- Test: `test/paper_trading/services/test_cash_service.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces `MONEY_QUANTUM = Decimal("0.000000000001")`, `NAV_QUANTUM = Decimal("0.000000000001")`, `SHARES_QUANTUM = Decimal("0.000000000001")`, and `ROUNDING_MODE` in `paper_trading/domain/precision.py`.
- Produces `quantize_account_money(value: Decimal) -> Decimal`, `quantize_nav(value: Decimal) -> Decimal`, `quantize_shares(value: Decimal) -> Decimal`, and `require_finite(value: Decimal, field_name: str) -> Decimal` from `paper_trading/domain/precision.py`.
- Produces `PaperTradingRepository.add_cash_event(..., rounding_residual: Decimal = Decimal("0")) -> PaperCashLedger`.
- Produces `CashService.deposit(...) -> CashFlowResult` and `CashService.withdraw(...) -> CashFlowResult` where `ledger.rounding_residual` reconciles requested amount with persisted share delta and effective NAV.
- Keeps `CashEventType.DEPOSIT`, `WITHDRAWAL`, `FREEZE`, `RELEASE`, `TRADE`, and `FEE`; adds `CORPORATE_ACTION = "corporate_action"` for later tasks.

- [ ] **Step 1: Write failing precision and residual tests**

Add tests that use amounts/NAVs requiring rounding in both directions. Assert the persisted share delta is quantized to 12 decimals, the residual is signed, and the reconciliation identity holds:

```python
requested = Decimal("10.000000000000")
represented = ledger.share_delta * ledger.net_asset_value
assert ledger.rounding_residual == requested - represented
```

Also assert an existing ledger row created before the field is present reads as `Decimal("0.000000000000")` after startup upgrade and that account/position/snapshot values retain their historical numeric value.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py -q`

Expected: FAIL because the residual field, 12-decimal persistence, and shared rounding contract do not exist.

- [ ] **Step 3: Implement the minimal precision contract**

Use `Decimal` inputs throughout the cash-flow path; reject non-finite values before quantization; use the repository's documented rounding mode explicitly; widen the persisted accounting columns to `Numeric(30, 12)` without changing display serializers; add `rounding_residual` with a zero server default; and calculate residual from the requested signed amount minus `share_delta * effective_nav` after persisted quantization. Do not alter cumulative external deposit/withdrawal totals for residuals.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py -q`

Expected: PASS, including both positive and negative residual cases and zero residual for exact representations.

- [ ] **Step 5: Commit the precision slice**

```bash
git add storage/model/paper_trading.py paper_trading/domain/enums.py paper_trading/storage/repository.py paper_trading/services/cash_service.py paper_trading/schemas/accounts.py test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py
git commit -m "feat(paper-trading): widen NAV precision and audit cash rounding"
```

## Task 2: Add Corporate-Action Domain Semantics

**Files:**
- Create: `paper_trading/domain/corporate_actions.py`
- Modify: `paper_trading/domain/enums.py:33-40`
- Modify: `paper_trading/domain/errors.py`
- Test: `test/paper_trading/domain/test_corporate_actions.py`

**Interfaces:**
- Produces `CorporateActionType(StrEnum)` with values `DIVIDEND`, `SPLIT`, `REVERSE_SPLIT`, `BONUS_SHARE`, and `RIGHTS_ISSUE`.
- Produces immutable `CorporateActionInput` with `event_type`, `parameters`, and Decimal-normalized values.
- Produces `CorporateActionImpact` with `cash_delta`, `quantity_delta`, `before_quantity`, `after_quantity`, `before_cost_amount`, `after_cost_amount`, `before_cash_available`, `after_cash_available`, and `affected_start_date`/`affected_end_date`.
- Produces `validate_corporate_action_parameters(event_type: CorporateActionType, parameters: Mapping[str, Decimal]) -> None`.
- Produces `calculate_corporate_action_impact(event_type: CorporateActionType, eligible_quantity: Decimal, cost_amount: Decimal, cash_available: Decimal, parameters: Mapping[str, Decimal]) -> CorporateActionImpact`.

- [ ] **Step 1: Write failing pure-domain tests**

Cover exact semantics:

```python
def test_split_preserves_total_cost_basis():
    impact = calculate_corporate_action_impact(
        CorporateActionType.SPLIT, Decimal("100"), Decimal("1000.00"), Decimal("0"), {"ratio": Decimal("2")}
    )
    assert impact.after_quantity == Decimal("200.000000000000")
    assert impact.after_cost_amount == Decimal("1000.000000000000")
    assert impact.cash_delta == Decimal("0.000000000000")
```

Add tests for dividend cash, reverse split factor below one, bonus dilution, full rights subscription, insufficient rights cash, zero eligible quantity, non-finite values, zero/negative parameters, and invalid reverse-split ratios.

- [ ] **Step 2: Run the domain tests to verify they fail**

Run: `uv run pytest test/paper_trading/domain/test_corporate_actions.py -q`

Expected: FAIL because the domain module, enum, impact type, and validation errors do not exist.

- [ ] **Step 3: Implement the pure Decimal calculations**

Implement only deterministic validation/calculation here. Dividend uses eligible pre-event quantity times `per_share_amount`; split and reverse split multiply quantity by `ratio` and preserve total cost; bonus share adds quantity by `bonus_ratio` and preserves total cost; rights issue adds `eligible_quantity * subscription_ratio`, subtracts that quantity times `subscription_price` from cash, and rejects insufficient cash. Require finite, strictly positive applicable values and permit zero eligible quantity to produce zero impact.

- [ ] **Step 4: Run the domain tests to verify they pass**

Run: `uv run pytest test/paper_trading/domain/test_corporate_actions.py -q`

Expected: PASS for all five event types and validation branches.

- [ ] **Step 5: Commit the domain slice**

```bash
git add paper_trading/domain/corporate_actions.py paper_trading/domain/enums.py paper_trading/domain/errors.py test/paper_trading/domain/test_corporate_actions.py
git commit -m "feat(paper-trading): define corporate action semantics"
```

## Task 3: Add Corporate-Action Persistence and Governed Migration

**Files:**
- Modify: `storage/model/paper_trading.py:49-70,84-180`
- Modify: `paper_trading/storage/models.py:1-63`
- Modify: `paper_trading/storage/repository.py:426-493,1094-1121`
- Modify: `paper_trading/storage/enum_migration.py:10-50,129-350,724-829`
- Modify: `storage/storage_db.py:365-427,390-420,4040-4280`
- Modify: `tools/db_common.sh:5-89`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/storage/test_corporate_action_migration.py`

**Interfaces:**
- Produces ORM `PaperCorporateAction` with account/security identity, `event_type`, UTC `event_at`, `idempotency_key`, JSON `parameters`, processing metadata, before/after quantity/cost/cash summaries, and affected date range.
- Produces `PaperTradingRepository.get_corporate_action_by_idempotency_key(account_id: int, key: str) -> PaperCorporateAction | None`.
- Produces `PaperTradingRepository.create_corporate_action(**values) -> PaperCorporateAction` and `list_corporate_actions(account_id, symbol=None, event_type=None, start_at=None, end_at=None) -> list[PaperCorporateAction]` ordered by `(event_at, id)`.
- Produces `PaperTradingRepository.lock_position(account_id: int, market: str | Market, symbol: str) -> PaperPosition | None`.
- Produces table name `tb_name_paper_corporate_actions = "paper_corporate_actions"` and unique account/key index `uq_paper_corporate_actions_account_idempotency`.

- [ ] **Step 1: Write failing model/repository tests**

Assert the event row persists all parameters and before/after summaries, the account/key uniqueness constraint exists, list filters and `(event_at, id)` ordering are deterministic, account deletion removes corporate-action rows, and cash-ledger residuals are exposed through `CashLedgerResponse`.

- [ ] **Step 2: Write failing migration tests**

In `test/paper_trading/storage/test_corporate_action_migration.py`, create reduced legacy PostgreSQL and SQLite schemas, then assert startup/migration adds the event table, governed enum labels, indexes, widened numeric types, and zero residual default. Invoke the upgrade twice and assert the second run makes no semantic changes. Insert legacy account, ledger, snapshot, and repair-marker rows and assert their values remain unchanged.

- [ ] **Step 3: Run storage tests to verify they fail**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py -q`

Expected: FAIL because the model, repository methods, migration declarations, startup DDL, and export table are absent.

- [ ] **Step 4: Add the model and repository methods**

Define the corporate-action table with foreign key to `paper_accounts`, indexed `account_id`, `symbol`, and `event_at`, a unique `(account_id, idempotency_key)` constraint/index, UTC-aware timestamp storage, JSON parameters/metadata, and Decimal summary columns. Use `session.flush()` but leave transaction ownership to the service/router. Extend `delete_account()` before deleting the account.

- [ ] **Step 5: Add governed PostgreSQL and additive SQLite upgrades**

Register the enum labels and new table in the governed migration structures, ensure table creation occurs after account dependencies, add precision/residual column upgrades with existing data untouched, use `DEFAULT 0` only for the new residual, preserve old repair/snapshot behavior, and make all DDL existence/index checks repeatable. Add the new table to `BUSINESS_TABLES`; add only the enum/table associations required by `business_enum_is_needed()` and drop rules.

- [ ] **Step 6: Run storage and migration tests to verify they pass**

Run: `tools/run_tests.sh test/paper_trading/storage/test_corporate_action_migration.py -v`

Then run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: PASS on SQLite-focused repository tests and PostgreSQL integration migration tests; repeatability, indexes, unique constraint, zero residual, and legacy preservation are all demonstrated.

- [ ] **Step 7: Commit the persistence slice**

```bash
git add storage/model/paper_trading.py paper_trading/storage/models.py paper_trading/storage/repository.py paper_trading/storage/enum_migration.py storage/storage_db.py tools/db_common.sh test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py
git commit -m "feat(paper-trading): persist corporate action events"
```

## Task 4: Implement Transactional Corporate-Action Processing

**Files:**
- Create: `paper_trading/services/corporate_action_service.py`
- Modify: `paper_trading/services/snapshot_recalculation_service.py:22-90`
- Modify: `paper_trading/storage/repository.py:317-321,664-682,720-750,822-859,1094-1121`
- Test: `test/paper_trading/services/test_corporate_action_service.py`
- Test: `test/paper_trading/services/test_snapshot_recalculation_service.py`

**Interfaces:**
- Produces `CorporateActionService.apply(account_id: int, symbol: str, event_type: CorporateActionType, event_at: datetime, idempotency_key: str, parameters: Mapping[str, Decimal], market: Market = Market.A_SHARE) -> CorporateActionResult`.
- Produces `CorporateActionResult(event: PaperCorporateAction, impact: CorporateActionImpact, recalculation: SnapshotRecalculationResult)`.
- Produces `CorporateActionService.list(...) -> list[PaperCorporateAction]` through the repository filter contract.
- Consumes `calculate_corporate_action_impact()`, locked account/position repository methods, and `SnapshotRecalculationService.recalculate(account_id, affected_start, affected_end)`.

- [ ] **Step 1: Write failing service tests**

Use isolated SQLite sessions and deterministic fake market data. Test dividend credits internal cash with `CashEventType.CORPORATE_ACTION`; split/reverse split and bonus update quantity/cost without cash ledger entries; rights issue fully subscribes and deducts cash; no holding creates an auditable zero-impact event; insufficient cash and invalid holdings leave account, position, ledger, event, snapshots, and gaps unchanged; identical idempotency replay returns the original event/result; changed content under the same key raises a conflict.

Include a transaction test that forces snapshot recalculation failure and asserts the event and all accounting writes roll back, then a successful test asserting event-date and later existing snapshot/gap dates are recalculated while unrelated dates and explicit gaps remain intact.

- [ ] **Step 2: Run service tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_corporate_action_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q`

Expected: FAIL because the service and lock/recalculation integration do not exist.

- [ ] **Step 3: Implement idempotency and validation before writes**

Normalize the event timestamp to UTC and canonicalize the parameter payload before comparing idempotency content. Lock the account, look up the existing key, return it only when canonical content matches, and raise `CorporateActionIdempotencyConflict` otherwise. Validate active account, market/symbol identity, finite positive parameters, and holding quantities before creating any row.

- [ ] **Step 4: Implement one-transaction accounting application**

Read eligible pre-event quantity and cost, calculate impact using Decimal, update the position and its lots consistently, add only the dividend/rights internal corporate-action ledger entry required by semantics, update account cash/NAV state without changing external deposit/withdrawal totals, write the event audit row, and flush all changes. Do not catch errors in a way that commits rejected rows; the caller transaction must roll back on any exception.

- [ ] **Step 5: Implement bounded recalculation and ordering preservation**

Determine the affected range from `event_at.date()` through the latest existing snapshot or valuation-gap date; call the recalculation service after the accounting writes are flushed but before the outer transaction commits; preserve each existing trading snapshot's `event_at` and `(event_at, id)` order; retain explicit valuation gaps and existing quality rules. Return updated, unavailable, failed, and error-date lists in the result.

- [ ] **Step 6: Run service tests to verify they pass**

Run: `uv run pytest test/paper_trading/services/test_corporate_action_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q`

Expected: PASS for all five event types, all rollback/idempotency branches, zero-impact auditing, cost-basis continuity, and bounded recalculation.

- [ ] **Step 7: Commit the processing slice**

```bash
git add paper_trading/services/corporate_action_service.py paper_trading/services/snapshot_recalculation_service.py paper_trading/storage/repository.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
git commit -m "feat(paper-trading): apply corporate actions transactionally"
```

## Task 5: Expose Corporate Actions Through API and Analytics Audit Events

**Files:**
- Create: `paper_trading/schemas/corporate_actions.py`
- Create: `paper_trading/api/routers/corporate_actions.py`
- Modify: `paper_trading/schemas/accounts.py:105-116`
- Modify: `paper_trading/schemas/analytics.py:99-130`
- Modify: `paper_trading/services/analytics_service.py:7-181`
- Modify: `paper_trading/api/app.py:6-37`
- Test: `test/paper_trading/api/test_corporate_actions_api.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/paper_trading/api/test_analytics_api.py`
- Test: `test/paper_trading/services/test_analytics_service.py`

**Interfaces:**
- Produces `POST /paper/accounts/{account_id}/corporate-actions` with `CorporateActionCreateRequest` and `CorporateActionCreateResponse` containing persisted event, `CorporateActionImpactResponse`, and `SnapshotRecalculationResponse`.
- Produces `GET /paper/accounts/{account_id}/corporate-actions` with optional `symbol`, `event_type`, `start_at`, and `end_at` filters; response order is `(event_at, id)`.
- Produces `CorporateActionAnalyticsEvent(event_type: Literal["corporate_action"], id, event_at, symbol, action_type, parameters, impact, created_at)` and includes it in the discriminated `AnalyticsEvent` union.
- Extends `CashLedgerResponse` with `rounding_residual: Decimal`.

- [ ] **Step 1: Write failing schema/API tests**

Test valid create payloads for all five types, reject timezone-naive `event_at`, reject zero/negative/non-finite applicable values, reject unknown fields, map account-not-found to 404, invalid domain input/insufficient cash to 422, idempotency conflict to 409, and return impact plus recalculation arrays. Test list filters, inclusive event-time bounds, and stable same-timestamp ordering.

- [ ] **Step 2: Write failing analytics tests**

Assert analytics interleaves snapshots, external deposit/withdrawal audit events, and `corporate_action` events by UTC `(event_at, priority, id)`; dividend/rights internal cash is not emitted as external cash-flow adjustment; corporate-action events are present for audit; invalid snapshots and every non-snapshot event are excluded from `_nav_series()`.

- [ ] **Step 3: Run API and analytics tests to verify they fail**

Run: `uv run pytest test/paper_trading/api/test_corporate_actions_api.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_analytics_api.py test/paper_trading/services/test_analytics_service.py -q`

Expected: FAIL because schemas/routes/event union handling are absent.

- [ ] **Step 4: Implement strict schemas and route mapping**

Use Pydantic Decimal fields and validators for finite positive values, type-specific parameter requirements, maximum idempotency-key length, and timezone-aware timestamps. Instantiate `CorporateActionService` with the existing session and market-data/recalculation dependencies, commit only after the service succeeds, and translate domain errors without committing the failed request.

- [ ] **Step 5: Implement audit-event serialization and TWR separation**

Add repository corporate-action rows to `AnalyticsService._event_series()` with a distinct sort priority. Keep `CashFlowAnalyticsEvent` limited to external `deposit`/`withdrawal`; keep internal corporate-action cash out of cumulative external cash-flow totals and NAV return adjustments. Preserve the current valid initial snapshot requirement and chart-point-only snapshot invariant.

- [ ] **Step 6: Run API and analytics tests to verify they pass**

Run: `uv run pytest test/paper_trading/api/test_corporate_actions_api.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_analytics_api.py test/paper_trading/services/test_analytics_service.py -q`

Expected: PASS with documented response shapes, error statuses, filters, ordering, audit events, and unchanged analytics availability/quality behavior.

- [ ] **Step 7: Commit the API/analytics slice**

```bash
git add paper_trading/schemas/corporate_actions.py paper_trading/api/routers/corporate_actions.py paper_trading/schemas/accounts.py paper_trading/schemas/analytics.py paper_trading/services/analytics_service.py paper_trading/api/app.py test/paper_trading/api/test_corporate_actions_api.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_analytics_api.py test/paper_trading/services/test_analytics_service.py
git commit -m "feat(paper-trading): expose corporate action audit APIs"
```

## Task 6: Add Frontend Corporate-Action Workflow and Audit Rendering

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:1-160,228-317`
- Modify: `frontend/paper-trading/lib/api-client.ts:26-139`
- Create: `frontend/paper-trading/features/accounts/corporate-action-modal.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx:6-292`
- Modify: `frontend/paper-trading/features/trading/trading-tables.tsx:219-237`
- Modify: `frontend/paper-trading/features/analytics/asset-chart.tsx:8-36`
- Modify: `frontend/paper-trading/features/analytics/analytics-tables.tsx`
- Modify: `frontend/paper-trading/features/analytics/analytics-page.tsx:6-145`
- Test: `frontend/paper-trading/lib/api-client.test.ts`
- Test: `frontend/paper-trading/features/accounts/corporate-action-modal.test.tsx`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Test: `frontend/paper-trading/features/trading/trading-tables.test.tsx`
- Test: `frontend/paper-trading/features/analytics/asset-chart.test.tsx`
- Test: `frontend/paper-trading/features/analytics/analytics-page.test.tsx`

**Interfaces:**
- Produces `CorporateActionInput`, `CorporateActionResult`, `CorporateActionImpact`, `CorporateActionEvent`, and `ListCorporateActionsParams` TypeScript types.
- Produces `createCorporateAction(accountId: number, input: CorporateActionInput): Promise<CorporateActionResult>`.
- Produces `listCorporateActions(accountId: number, params?: ListCorporateActionsParams): Promise<CorporateActionEvent[]>`.
- Produces `CorporateActionModal` props `{ account: Account | null; open: boolean; onClose: () => void; onCompleted: (result: CorporateActionResult) => void }`.

- [ ] **Step 1: Write failing client/component tests**

Test POST body encoding, optional query filters, mode-specific required fields, finite positive client validation, rights-issue cash warning/validation, backend error display, successful completion callback, account refresh, residual rendering, and audit-event rendering. Add chart tests with a valid snapshot, invalid snapshot, deposit, withdrawal, and `corporate_action`; assert only the valid snapshot reaches `series.setData()`.

- [ ] **Step 2: Run focused frontend tests to verify they fail**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx`

Expected: FAIL because the client helpers, modal, types, and audit rendering do not exist.

- [ ] **Step 3: Add types and API helpers**

Represent all backend Decimal values as strings. Encode only the selected action's parameters, preserve the timezone-bearing ISO `event_at`, pass `symbol`, `event_type`, `idempotency_key`, and optional `market`, and build list query strings from defined filters without serializing `undefined`.

- [ ] **Step 4: Add the account action modal and refresh flow**

Render a stable form for the five modes; require positive decimal fields and timezone-aware event time; show available cash for rights issues; call `createCorporateAction`; keep the modal open on `ApiError`; close and call `onCompleted(result)` only after success. Add an action button to the selected-account header and refresh accounts and positions after completion using the existing selected-account race protections.

- [ ] **Step 5: Add ledger/audit rendering and chart filtering**

Add a corporate-action label and `rounding_residual` column/value to the cash ledger table. Render corporate-action audit details in the analytics event surface. Keep `AssetChart`'s filter explicit: accept only `event_type === "snapshot"` or legacy `Snapshot` objects, require `quality_status === "valid"`, finite positive NAV, and valid timestamp, and never use total assets as fallback.

- [ ] **Step 6: Run focused frontend tests to verify they pass**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx`

Expected: PASS with no auxiliary event plotted and all account/audit interactions covered.

- [ ] **Step 7: Commit the frontend slice**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/lib/api-client.ts frontend/paper-trading/features/accounts/corporate-action-modal.tsx frontend/paper-trading/features/accounts/accounts-page.tsx frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/features/analytics/asset-chart.tsx frontend/paper-trading/features/analytics/analytics-tables.tsx frontend/paper-trading/features/analytics/analytics-page.tsx frontend/paper-trading/lib/api-client.test.ts frontend/paper-trading/features/accounts/corporate-action-modal.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/features/trading/trading-tables.test.tsx frontend/paper-trading/features/analytics/asset-chart.test.tsx frontend/paper-trading/features/analytics/analytics-page.test.tsx
git commit -m "feat(paper-trading): add corporate action frontend workflow"
```

## Task 7: Update Documentation and Baseline Analysis

**Files:**
- Modify: `docs/paper_trading.md`
- Modify: `docs/todo/paper_trading-nav-baseline-analysis.md`

**Interfaces:**
- Documents the public API response/request names from `paper_trading/schemas/corporate_actions.py` exactly.
- Documents UTC normalization, event-date/calendar interpretation, `(event_at, id)` ordering, idempotency replay/conflict behavior, 12-decimal internal precision, display precision, explicit rounding mode, and residual equation.
- Documents dividend, split, reverse split, bonus share, and rights issue semantics; internal corporate-action cash versus external TWR cash flows; no-holding zero-impact auditing; valuation gaps, stale prices, bounded recalculation, migration preservation, and data-quality limitations.

- [ ] **Step 1: Write documentation assertions as a review checklist**

Before editing, enumerate the required terms and verify each appears in the final documents: `UTC`, `event_at`, `idempotency`, `Numeric(30, 12)`, rounding mode, `rounding_residual`, all five action types, internal cash, external TWR, valuation gap, stale price, snapshot recalculation, migration, and data quality.

- [ ] **Step 2: Update the paper-trading reference documentation**

Add API examples for create/list, parameter tables and validation rules, CLI/API usage boundaries, event ordering/idempotency, accounting formulas, response impact/recalculation fields, and explicit statement that provider synchronization is out of scope. Preserve existing endpoint paths, display formats, repair-marker guidance, and DAG constraints.

- [ ] **Step 3: Correct the stale NAV baseline note**

Replace statements that account creation writes no initial snapshot with the current contract: account creation persists one valid initial point at NAV `1.000000`; later transaction/valuation snapshots retain real dates and NAV; invalid/non-snapshot events do not become chart points; corporate-action quantity changes preserve NAV continuity where specified.

- [ ] **Step 4: Review documentation for contradictions**

Run: `uv run pre-commit run --files docs/paper_trading.md docs/todo/paper_trading-nav-baseline-analysis.md`

Then search: `rg -n "no initial|total_assets.*NAV|provider.*corporate|rounding_residual|corporate_action|rights_issue|reverse_split" docs/paper_trading.md docs/todo/paper_trading-nav-baseline-analysis.md`

Expected: no stale claim contradicts the approved design and every required documented concept is present.

- [ ] **Step 5: Commit the documentation slice**

```bash
git add docs/paper_trading.md docs/todo/paper_trading-nav-baseline-analysis.md
git commit -m "docs(paper-trading): document precision and corporate actions"
```

## Task 8: Full Verification, Simplification, and Release Gate

**Files:**
- Modify: only the implementation/test/documentation files listed in Tasks 1-7 when a verification failure is reproduced in that file's owned behavior; do not add new files or touch unrelated paths.
- Test: all backend/frontend test files listed in this plan.

**Interfaces:**
- Verification claim: every approved design requirement is covered by a runnable test or an explicit migration/documentation check.
- Release boundary: no commit is made from this task until focused tests, PostgreSQL integration, frontend tests, lint/type checks, pre-commit, and the full test runner pass.

- [ ] **Step 1: Run focused backend domain/service/API tests**

Run: `uv run pytest test/paper_trading/domain/test_corporate_actions.py test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/services/test_analytics_service.py test/paper_trading/api/test_corporate_actions_api.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_analytics_api.py -q`

Expected: PASS; failures must be fixed in the owning task's files and rerun from that task's focused command.

- [ ] **Step 2: Run PostgreSQL migration and integration coverage**

Run: `tools/run_tests.sh test/paper_trading/storage/test_corporate_action_migration.py test/paper_trading/storage/test_enum_migration.py test/paper_trading/storage/test_nav_series_migration.py -v`

Expected: PASS with verified enum labels, numeric types, indexes, unique key, residual default, repeatability, rollback, and legacy snapshot/repair preservation.

- [ ] **Step 3: Run frontend tests, lint, and build checks**

Run: `cd frontend/paper-trading && npm run test -- --run && npm run lint && npm run build`

Expected: PASS; the chart test must demonstrate no non-snapshot event reaches the chart data.

- [ ] **Step 4: Run Python quality gates**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy`

Expected: PASS without adding the new modules to an excluded mypy area; if a new module is checked, include it in `[tool.mypy].files` according to repository convention in the implementation commit.

- [ ] **Step 5: Run pre-commit and the full suite**

Run: `uv run pre-commit run --all-files`

Then run: `tools/run_tests.sh`

Expected: PASS for every hook and the complete backend/integration suite.

- [ ] **Step 6: Perform the required simplify review**

Invoke the `simplify` skill against the touched implementation. Apply only behavior-preserving simplifications inside issue #87 scope, rerun the focused tests for changed files, and record in the implementation review that either a specific simplification was applied or no safe simplification was identified.

- [ ] **Step 7: Inspect the final diff and status**

Run: `git status --short && git diff --check && git diff --stat && git diff -- docs/superpowers/plans/2026-08-27-issue-87-nav-precision-corporate-actions-plan.md`

Expected: the implementation diff contains only issue #87 files, no generated secrets or unrelated changes, and the plan file itself remains the only file owned by this planning task.

## Risks and Mitigations

- **Precision widening changes persisted scale unexpectedly.** Verify catalog types on both PostgreSQL and SQLite, preserve old numeric values, and keep display formatting in existing response/frontend formatters.
- **Rounding residual sign or amount is wrong.** Test positive and negative cash-flow directions and assert the exact reconciliation identity using persisted, not pre-quantized, values.
- **Corporate-action replay duplicates accounting.** Enforce the account/key unique index, compare canonical event content before writes, and test identical replay plus conflicting reuse under separate sessions.
- **Partial writes survive rejected actions.** Keep service writes in the caller transaction, flush only for lock/identity checks, and force failures after each write boundary in rollback tests.
- **Position lots diverge from aggregate position.** Update eligible lots and aggregate totals in one transaction and assert aggregate quantity/cost equals the lot roll-up after every event type.
- **Internal dividend/rights cash contaminates TWR.** Use a dedicated `corporate_action` ledger event type and keep analytics external cash-flow serialization restricted to deposit/withdrawal.
- **Snapshot recalculation destroys explicit gaps or event order.** Recalculate only the event date through the latest existing snapshot/gap date, preserve historical snapshot `event_at`, and test unresolved and resolved gaps.
- **Chart treats audit events or invalid data as NAV points.** Keep the frontend discriminant and valid-snapshot checks explicit and test mixed event-series input.
- **Startup migration creates tables outside governance or is not repeatable.** Register the table/enum in the existing governance structures, test reduced schemas twice, and verify `tools/db_common.sh` export/import lists.
- **Frontend exposes stale account state after asynchronous completion.** Reuse existing selected-account/request identity guards and test switching accounts during completion callbacks.

## Self-Review Against Approved Spec

- [x] High-precision Decimal NAV/share/quantity/price/money calculations: Tasks 1-4.
- [x] `Numeric(30, 12)` persistence with unchanged display formatting: Tasks 1 and 3.
- [x] Explicit cash-flow rounding mode and persisted residual equation: Task 1, API/frontend exposure in Tasks 5-6, documentation in Task 7.
- [x] Zero residual migration default without historical rewrites: Task 3 and migration tests.
- [x] Single-security corporate-action identity, timezone-aware timestamp, type, key, and parameters: Tasks 2-5.
- [x] Dividend, split, reverse split, bonus share, and rights issue semantics: Task 2 pure tests and Task 4 transactional tests.
- [x] One-transaction success and complete rollback on invalid input, insufficient cash, invalid holdings, or conflict: Task 4 and API mapping in Task 5.
- [x] Idempotent replay and conflicting key behavior: Tasks 3-5.
- [x] Corporate-action model fields and account/security/event indexes: Task 3.
- [x] `corporate_action` analytics audit event and snapshot-only chart points: Tasks 5-6.
- [x] Required POST/GET routes, filters, ordering, validation, impact, and recalculation responses: Task 5.
- [x] Account/holding locks and `(event_at, id)` processing order: Task 4.
- [x] Bounded snapshot recalculation preserving gaps and data-quality rules: Task 4.
- [x] No external TWR discontinuity or external cash total change: Tasks 2, 4, and 5.
- [x] PostgreSQL/SQLite startup upgrades, governed enum migration, repeatability, rollback, and legacy preservation: Task 3 and Task 8.
- [x] Database export/import synchronization: Task 3.
- [x] UTC/calendar documentation, precision/rounding documentation, all action semantics, internal/external cash distinction, gap/stale/migration limitations: Task 7.
- [x] Backend, storage/migration, API, frontend, Ruff/mypy, pre-commit, and full-suite verification: Task 8.
- [x] Explicit exclusions for provider synchronization, unrelated refactoring, and DAG changes: Global Constraints and Task 7.

No placeholders remain in the task sequence; every implementation boundary names its files, symbols, tests, commands, and commit. The current checkout does not contain the approved spec file, so this plan treats the committed design from `a88c6a5` as authoritative and assumes no additional issue #87 acceptance criteria exist outside that document.
