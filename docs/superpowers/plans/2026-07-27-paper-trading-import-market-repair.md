# Paper Trading Imported Position Market Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve imported-position markets through import and replay, explicitly repair approved misclassified holdings, and make snapshot market-data failures return a persisted, diagnosable matching result rather than an unhandled HTTP 500.

**Architecture:** Add `market` to the imported lot—the durable source used for replay—and propagate it through the API, import service, repository, CSV CLI, and import UI. Validate that imported lots for one aggregate symbol agree on their market before mutating state. Snapshot market-data `KeyError` and `ValueError` become failed matching-run outcomes with diagnostic detail; no symbol-based market fallback is attempted.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/TimescaleDB, pytest, Ruff, mypy, Next.js/React, TypeScript.

## Global Constraints

- Run every project Python command through `uv run`.
- Keep `a_share` as the default when an existing JSON or CSV import omits `market`.
- Accept only existing market values: `a_share` and `hk_connect`.
- Never infer a market from a symbol, including five-digit symbols such as `00700`.
- Update existing holdings only through explicit account/symbol/market mappings; do not hard-code unconfirmed account IDs.
- Do not modify DAG schedules, dependencies, retries, task boundaries, or `tools/db_common.sh`; no table is added or removed.
- Catch only expected snapshot market-data absence/invalid-value errors; database and programming errors must remain visible.

---

## File Map

| File | Responsibility |
| --- | --- |
| `storage/model/paper_trading.py` | Add durable market metadata to `PaperPositionLot`. |
| `storage/storage_db.py` | Upgrade legacy `paper_position_lots` schema safely and idempotently. |
| `paper_trading/schemas/accounts.py` | Accept and default per-import-item market. |
| `paper_trading/services/account_service.py` | Validate import-market consistency and propagate it to persistence. |
| `paper_trading/storage/repository.py` | Persist lot market; validate and preserve it during rebuild; retain matching failure diagnostics. |
| `paper_trading/services/matching_service.py` | Turn snapshot market-data failures into failed matching-run results. |
| `paper_trading/schemas/matching.py` | Expose matching-run error detail. |
| `tools/paper_trading_cli.py` | Accept optional CSV market column. |
| `tools/repair_paper_position_markets.py` | Apply explicit, atomic, idempotent historical data corrections. |
| `frontend/paper-trading/lib/types.ts` | Extend import and matching response contracts. |
| `frontend/paper-trading/features/accounts/import-positions-modal.tsx` | Offer a per-row market selector, defaulting to A-share. |
| `frontend/paper-trading/app/globals.css` | Accommodate the additional import-form control without breaking mobile layout. |
| `docs/paper_trading.md` | Document import market fields, repair command, and matching failure behavior. |

### Task 1: Persist market metadata on position lots

**Files:**
- Modify: `storage/model/paper_trading.py:89-100`
- Modify: `storage/storage_db.py:2427-2447`
- Modify: `test/paper_trading/storage/test_models.py`
- Modify: `test/storage/test_storage_db.py:77-343`

**Consumes:** Existing `PaperPosition.market` default and `StorageDb.ensure_paper_trading_schema()` legacy-column upgrade pattern.

**Produces:** `PaperPositionLot.market: str`, non-null with ORM/server default `"a_share"`; schema upgrade creates and backfills the column.

- [ ] **Step 1: Write the failing model and upgrade tests**

Add model assertions proving `PaperPositionLot` has a non-null `market` column with default `a_share`. Extend the legacy-schema fixture so it contains an imported position lot before upgrade, then assert the upgrade adds the column, exposes `a_share` for the historical row, and succeeds twice.

```python
def test_position_lot_market_defaults_to_a_share(session):
    lot = PaperPositionLot(
        account_id=1,
        symbol="000001",
        buy_trade_date=date(2026, 7, 27),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("10.00"),
    )
    session.add(lot)
    session.flush()
    assert lot.market == "a_share"


def test_ensure_schema_adds_lot_market_to_legacy_rows(storage_db, legacy_lot_id):
    storage_db.ensure_paper_trading_schema()
    storage_db.ensure_paper_trading_schema()
    lot = storage_db.session.get(PaperPositionLot, legacy_lot_id)
    assert lot.market == "a_share"
```

- [ ] **Step 2: Run the focused tests and confirm they fail for the missing field**

Run:

```bash
uv run pytest test/paper_trading/storage/test_models.py test/storage/test_storage_db.py -q
```

Expected: failure because `PaperPositionLot` has no `market` attribute/column or the legacy schema is not upgraded.

- [ ] **Step 3: Add the lot field and schema migration**

In `PaperPositionLot`, add a `String(20)`, indexed, non-null `market` column with both ORM and server defaults set to `"a_share"`. Extend the existing market-column migration loop to include `tb_name_paper_position_lots`; use the established `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT 'a_share'` convention so pre-existing rows receive the default.

```python
market = Column(String(20), nullable=False, server_default="a_share", index=True)
```

- [ ] **Step 4: Run focused tests and confirm they pass**

Run:

```bash
uv run pytest test/paper_trading/storage/test_models.py test/storage/test_storage_db.py -q
```

Expected: PASS, including two consecutive schema-upgrade calls.

- [ ] **Step 5: Commit the isolated migration change**

```bash
git add storage/model/paper_trading.py storage/storage_db.py test/paper_trading/storage/test_models.py test/storage/test_storage_db.py
git commit -m "feat: preserve market on paper position lots"
```

### Task 2: Make position import market-aware

**Files:**
- Modify: `paper_trading/schemas/accounts.py:106-132`
- Modify: `paper_trading/services/account_service.py:94-127`
- Modify: `paper_trading/storage/repository.py:437-458`
- Modify: `test/paper_trading/schemas/test_accounts.py`
- Modify: `test/paper_trading/services/test_account_service.py`
- Modify: `test/paper_trading/api/test_accounts_api.py:180-212`

**Consumes:** Task 1 `PaperPositionLot.market`; `Market` enum from `paper_trading/domain/enums.py`.

**Produces:** `ImportPositionItem.market: Market = Market.A_SHARE`; `create_position_lot(..., market: str = "a_share")`; imported aggregate positions and lots use the explicit market.

- [ ] **Step 1: Write failing schema, service, and API tests**

Cover all of the following:

```python
def test_import_item_defaults_market_to_a_share():
    item = ImportPositionItem(
        symbol="000001", quantity=100, cost_price="10.00", buy_trade_date="2026-07-27"
    )
    assert item.market is Market.A_SHARE


def test_import_hk_position_persists_market_on_position_and_lot(service, repo, account):
    service.import_positions(account.id, [
        ImportPositionItem(
            symbol="00700", quantity=100, cost_price="400", buy_trade_date="2026-07-27", market="hk_connect"
        )
    ])
    assert repo.get_position(account.id, "00700").market == "hk_connect"
    assert repo.get_position_lots(account.id, "00700")[0].market == "hk_connect"


def test_import_rejects_duplicate_symbol_with_conflicting_markets_before_writes(service, repo, account):
    with pytest.raises(ValueError, match="conflicting markets for imported symbol: 00700"):
        service.import_positions(account.id, [a_share_00700, hk_connect_00700])
    assert repo.get_positions(account.id) == []
    assert repo.count_position_lots(account.id) == 0
```

At API level, assert HK input returns 200, omitted input remains A-share, and a conflicting duplicate payload returns 422 with no rows written.

- [ ] **Step 2: Run focused tests and confirm they fail because the import contract lacks market**

Run:

```bash
uv run pytest test/paper_trading/schemas/test_accounts.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py -q
```

Expected: failure because `market` is not accepted or is not persisted.

- [ ] **Step 3: Implement the minimal import propagation and validation**

Add `market: Market = Market.A_SHARE` to `ImportPositionItem`. Add a `market` argument to `create_position_lot` and set it on `PaperPositionLot`. Before creating any lots, construct `market_by_symbol`; if a later row names the same symbol with another market, raise `ValueError(f"conflicting markets for imported symbol: {symbol}")`. Pass `item.market.value` to lot creation and the validated symbol market to `upsert_position`.

```python
market_by_symbol: dict[str, Market] = {}
for item in positions:
    previous = market_by_symbol.setdefault(item.symbol, item.market)
    if previous != item.market:
        raise ValueError(f"conflicting markets for imported symbol: {item.symbol}")
```

- [ ] **Step 4: Run focused import tests and confirm they pass**

Run:

```bash
uv run pytest test/paper_trading/schemas/test_accounts.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py -q
```

Expected: PASS; old four-field request payloads still persist `a_share`.

- [ ] **Step 5: Commit the import contract change**

```bash
git add paper_trading/schemas/accounts.py paper_trading/services/account_service.py paper_trading/storage/repository.py test/paper_trading/schemas/test_accounts.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py
git commit -m "feat: retain imported position market"
```

### Task 3: Preserve market through replay and trade-lot creation

**Files:**
- Modify: `paper_trading/storage/repository.py:656-719`
- Modify: `paper_trading/services/matching_service.py:191-209`
- Modify: `test/paper_trading/storage/test_repository.py:559-701`
- Modify: `test/paper_trading/services/test_matching_service.py:241-360`
- Modify: `test/paper_trading/services/test_snapshot_service.py:154-190`

**Consumes:** Task 2 lot-market persistence and import market consistency rule.

**Produces:** `clear_account_rebuild_state()` validates market agreement before destructive operations and rebuilds imported aggregate positions using lot market; trade-created lots receive `order.market`.

- [ ] **Step 1: Write failing replay and routing tests**

```python
def test_rebuild_preserves_imported_hk_market(repo, account):
    repo.create_position_lot(..., symbol="00700", source="imported", market="hk_connect")
    repo.upsert_position(..., symbol="00700", source="imported", market="hk_connect")
    repo.clear_account_rebuild_state(account.id)
    assert repo.get_position(account.id, "00700").market == "hk_connect"


def test_rebuild_rejects_persisted_mixed_markets_before_clearing(repo, account):
    repo.create_position_lot(..., symbol="00700", source="imported", market="a_share")
    repo.create_position_lot(..., symbol="00700", source="imported", market="hk_connect")
    with pytest.raises(ValueError, match="conflicting markets for imported symbol: 00700"):
        repo.clear_account_rebuild_state(account.id)
    assert repo.get_position(account.id, "00700") is not None
```

Extend the snapshot routing test so an imported `00700`, after rebuild, calls `get_daily_bar(..., market="hk_connect")`. Extend the HK matching test to assert the trade-created lot uses `hk_connect`.

- [ ] **Step 2: Run focused tests and confirm they fail because rebuild and trade lots drop market**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q
```

Expected: the rebuilt position defaults to A-share and trade lots omit the market field.

- [ ] **Step 3: Implement prevalidation and reconstruction**

Load imported lots and form `market_by_symbol` before deleting positions or resetting state. Reject a symbol with multiple stored markets before any destructive action. When constructing rebuilt imported `PaperPosition` rows, set `market=market_by_symbol[symbol]`. Update `_settle_buy()` (or the current purchase-lot creation call) to pass `market=order.market`.

```python
markets = {lot.market for lot in imported_lots_for_symbol}
if len(markets) != 1:
    raise ValueError(f"conflicting markets for imported symbol: {symbol}")
```

- [ ] **Step 4: Run focused replay tests and confirm they pass**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit replay preservation**

```bash
git add paper_trading/storage/repository.py paper_trading/services/matching_service.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py
git commit -m "fix: preserve position markets during replay"
```

### Task 4: Add CSV and frontend import-market controls

**Files:**
- Modify: `tools/paper_trading_cli.py:479-533`
- Modify: `test/tools/test_paper_trading_cli.py`
- Modify: `frontend/paper-trading/lib/types.ts`
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.tsx:7-105`
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Modify: `frontend/paper-trading/app/globals.css`

**Consumes:** Task 2 import API contract.

**Produces:** CSV optional `market` column and import-row UI selector; both normalize omitted/blank values to `a_share`.

- [ ] **Step 1: Write failing CLI and UI tests**

CLI tests must prove four-column CSVs send `market: "a_share"`, an optional `hk_connect` value is forwarded, blank is defaulted, and unsupported values fail locally before invoking the API client. UI tests must prove every new/reset row defaults to A-share, selecting Hong Kong Connect sends `market: "hk_connect"`, and the existing submission shape includes the field.

```tsx
expect(await screen.findByLabelText("Market")).toHaveValue("a_share");
await user.selectOptions(screen.getByLabelText("Market"), "hk_connect");
expect(importPositions).toHaveBeenCalledWith(account.id, {
  positions: [expect.objectContaining({ symbol: "00700", market: "hk_connect" })],
});
```

- [ ] **Step 2: Run focused CLI and frontend tests and confirm they fail**

Run:

```bash
uv run pytest test/tools/test_paper_trading_cli.py -q
npm --prefix frontend/paper-trading test -- features/accounts/import-positions-modal.test.tsx features/accounts/accounts-page.test.tsx
```

Expected: missing market payload/control failures.

- [ ] **Step 3: Implement normalized CSV parsing and per-row selector**

Keep the existing four CSV columns required; read `row.get("market", "").strip() or "a_share"`, validate against `{ "a_share", "hk_connect" }`, and include the normalized value in each payload row. Update CLI help/docs text describing the optional column.

Define a shared `Market = "a_share" | "hk_connect"` frontend type, make `ImportPositionInput.market` required, add `market` to `ImportRow`, default it in `emptyRow()`, render an accessible native select, and add it to the existing payload mapping. Extend desktop import-grid styling for a sixth field while preserving the existing mobile single-column behavior.

- [ ] **Step 4: Run focused checks and confirm they pass**

Run:

```bash
uv run pytest test/tools/test_paper_trading_cli.py -q
npm --prefix frontend/paper-trading test -- features/accounts/import-positions-modal.test.tsx features/accounts/accounts-page.test.tsx
npm --prefix frontend/paper-trading run lint
```

Expected: PASS.

- [ ] **Step 5: Commit import clients**

```bash
git add tools/paper_trading_cli.py test/tools/test_paper_trading_cli.py frontend/paper-trading/lib/types.ts frontend/paper-trading/features/accounts/import-positions-modal.tsx frontend/paper-trading/features/accounts/import-positions-modal.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/app/globals.css
git commit -m "feat: select market when importing positions"
```

### Task 5: Add explicit historical market-repair command

**Files:**
- Create: `tools/repair_paper_position_markets.py`
- Create: `test/tools/test_repair_paper_position_markets.py`
- Modify: `docs/paper_trading.md`

**Consumes:** Task 1 lot field, exported storage helpers, and `conf.parse_config()`.

**Produces:** Repeatable command:

```bash
uv run tools/repair_paper_position_markets.py --mapping ACCOUNT_ID:00700:hk_connect
```

It atomically updates only explicitly named `paper_positions` and `source="imported"` lots.

- [ ] **Step 1: Write failing command-unit tests**

Test parsing, malformed/unsupported mapping rejection, conflicting duplicate mappings, prevalidation of every target before writes, updates limited to the requested aggregate position and imported lots, exclusion of unrelated/trade lots, atomic multi-mapping behavior, and idempotent second execution.

```python
def test_repair_updates_only_explicit_imported_hk_holding(session):
    result = repair_position_markets(session, [MarketRepairMapping(1, "00700", Market.HK_CONNECT)])
    assert result[0].position_rows_changed == 1
    assert result[0].lot_rows_changed == 1
    assert unrelated_position.market == "a_share"
    assert trade_lot.market == "a_share"
```

- [ ] **Step 2: Run the test file and confirm it fails because the command does not exist**

Run:

```bash
uv run pytest test/tools/test_repair_paper_position_markets.py -q
```

Expected: import/module failure.

- [ ] **Step 3: Implement a testable, atomic repair command**

Expose `MarketRepairMapping`, `MarketRepairResult`, `parse_mapping`, `repair_position_markets`, and `main`. Parse repeatable `--mapping ACCOUNT_ID:SYMBOL:MARKET`; reject malformed, unsupported, or conflicting requests. Prevalidate that every requested aggregate position exists before issuing updates. Use one transaction, explicit equality predicates, and `source == "imported"` for lot updates. Repeating a successful command must return zero changed counts without error. Initialize with `conf.parse_config()` and the repository’s exported storage/session helper; support `--json` plus concise normal output.

- [ ] **Step 4: Run command tests and confirm they pass**

Run:

```bash
uv run pytest test/tools/test_repair_paper_position_markets.py -q
```

Expected: PASS.

- [ ] **Step 5: Document the explicit production procedure and commit**

Document optional import market values, matching same-symbol consistency, the repair command, idempotency, and the explicit-only rule. Use an account-ID placeholder; never embed an account ID not supplied at deployment.

```bash
git add tools/repair_paper_position_markets.py test/tools/test_repair_paper_position_markets.py docs/paper_trading.md
git commit -m "feat: add explicit paper position market repair"
```

### Task 6: Make snapshot market-data failures a controlled matching outcome

**Files:**
- Modify: `paper_trading/services/matching_service.py:35-67`
- Modify: `paper_trading/storage/repository.py:494-512`
- Modify: `paper_trading/schemas/matching.py`
- Modify: `frontend/paper-trading/lib/types.ts`
- Modify: `test/paper_trading/services/test_matching_service.py`
- Create: `test/paper_trading/api/test_matching_api.py`

**Consumes:** Existing `MatchingRunStatus`, matching-run `failed` state, and snapshot service’s `KeyError`/`ValueError` market-data semantics.

**Produces:** Matching run response with `error_details`; snapshot `KeyError`/`ValueError` causes `status="failed"`, preserves the run, and creates no snapshot for that account.

- [ ] **Step 1: Write failing service and API regression tests**

At service level, make snapshot valuation raise `KeyError("No daily bar for 00700 on 2026-07-27")` after an order fills. Assert returned run is failed, its details identify account/date/exception, no snapshot exists, the filled order remains recorded, and no other market lookup is attempted. Repeat for invalid OHLC `ValueError`. Ensure a non-market-data exception still raises.

At API level, use dependency overrides to seed the scenario, POST `/paper/matching/runs`, and assert HTTP 200, persisted failed run detail, and no snapshot—not an uncaught 500.

```python
def test_snapshot_missing_bar_marks_matching_run_failed(matching_service, repo, account):
    run = matching_service.run(date(2026, 7, 27), account.id)
    assert run.status == MatchingRunStatus.FAILED.value
    assert "No daily bar for 00700" in run.error_details
    assert repo.get_snapshot(account.id, date(2026, 7, 27)) is None
```

- [ ] **Step 2: Run targeted tests and confirm the current code exposes the 500/exception**

Run:

```bash
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py -q
```

Expected: snapshot `KeyError`/`ValueError` escapes the service/router.

- [ ] **Step 3: Implement narrow failure recording**

Extend `update_matching_run_counts` to accept and save `error_details`. In `MatchingService.run`, wrap only each `snapshot_service.generate_snapshot` call in `except (KeyError, ValueError)`. Collect account-specific diagnostic text, continue attempting unrelated affected accounts, and finish the run as `FAILED` when any snapshot fails; otherwise preserve `COMPLETED`. Do not catch database or arbitrary runtime errors. Add nullable `error_details` to matching response schema and its frontend type.

```python
snapshot_errors: list[str] = []
for current_account_id in affected_accounts:
    try:
        self.snapshot_service.generate_snapshot(current_account_id, trade_date)
    except (KeyError, ValueError) as exc:
        snapshot_errors.append(f"account={current_account_id}, trade_date={trade_date}: {exc}")

status = MatchingRunStatus.FAILED.value if snapshot_errors else MatchingRunStatus.COMPLETED.value
```

- [ ] **Step 4: Run matching regression tests and confirm they pass**

Run:

```bash
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py test/paper_trading/api/test_accounts_api.py -q
```

Expected: PASS; missing market data produces a committed controlled failure result.

- [ ] **Step 5: Commit matching failure handling**

```bash
git add paper_trading/services/matching_service.py paper_trading/storage/repository.py paper_trading/schemas/matching.py frontend/paper-trading/lib/types.ts test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py
git commit -m "fix: record matching snapshot data failures"
```

### Task 7: Run complete verification and perform explicit operational correction

**Files:**
- Modify: `docs/paper_trading.md`
- Test: affected test files from Tasks 1–6

**Consumes:** Completed implementation and an externally supplied approved account ID for the known `00700` holding.

**Produces:** Evidence that imports/replay persist market metadata, missing market data never becomes an unclassified 500, and only explicit production records are repaired.

- [ ] **Step 1: Run formatting, linting, type checks, backend tests, and frontend checks**

Run:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest test/storage/test_storage_db.py test/paper_trading test/tools/test_paper_trading_cli.py test/tools/test_repair_paper_position_markets.py
uv run pre-commit run --all-files
uv run pytest test
npm --prefix frontend/paper-trading test
npm --prefix frontend/paper-trading run lint
npm --prefix frontend/paper-trading run build
```

Expected: all commands pass. If a broad suite failure is unrelated, record the exact command and evidence rather than masking it.

- [ ] **Step 2: Deploy schema-compatible service and inspect service health**

Run:

```bash
docker compose up -d paper-trading
docker compose ps
```

Expected: `paper-trading` is running. Startup executes the idempotent schema upgrade before repair is attempted.

- [ ] **Step 3: Require the exact account ID and preview only that holding**

Do not guess account IDs. With an approved `<ACCOUNT_ID>`, inspect the matching aggregate position and imported lots through a parameterized operational query/tool. Confirm the intended holding is `00700` and must be `hk_connect` before changing data.

- [ ] **Step 4: Apply and prove idempotent explicit repair**

Run:

```bash
uv run tools/repair_paper_position_markets.py --mapping <ACCOUNT_ID>:00700:hk_connect
uv run tools/repair_paper_position_markets.py --mapping <ACCOUNT_ID>:00700:hk_connect
```

Expected: first run changes only the selected position/imported lots; second run reports zero changed rows. Confirm both persisted records are now `hk_connect`.

- [ ] **Step 5: Verify matching through the normal API wrapper**

Run:

```bash
set -a; source .env; set +a; export PAPER_TRADING_API_BASE_URL="${PAPER_TRADING_API_BASE_URL:-http://localhost:8000}"; uv run tools/paper_trading_cli.py --json matching run --trade-date <VERIFICATION_DATE> --account-id <ACCOUNT_ID>
```

Expected: no HTTP 500. If HK daily data exists, matching completes and snapshots use `hk_connect`; if it does not, the API returns a persisted failed run with `error_details` and no misleading snapshot.

- [ ] **Step 6: Commit documentation-only verification adjustments if needed**

```bash
git add docs/paper_trading.md
git commit -m "docs: describe paper trading market repair workflow"
```

Only commit if Task 7 changes the documentation beyond Task 5.
