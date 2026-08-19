# Paper Trading Market-Qualified Security Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent state, replay, diagnostics, valuation, and round-trip analytics from mixing same-symbol paper-trading securities across `a_share` and `hk_connect` markets.

**Architecture:** Make `(account_id, market, symbol)` the identity passed through stateful repository and service operations. Add `market` to round trips and daily-bar diagnostics, migrate existing diagnostics to `a_share`, and retain market-qualified missing-security references in valuation-gap details. Preserve current API and CLI behavior, including the default `a_share` order market.

**Tech Stack:** Python 3.11+, SQLAlchemy ORM, PostgreSQL enum-governance migrations, SQLite unit tests, pytest, Ruff, mypy, uv.

## Global Constraints

- Scope is limited to existing `a_share` and `hk_connect` behavior; do not add `etf` to `Market` or change ETF-facing code.
- Use `uv run` for every Python command.
- Existing persisted A-share and HK Connect records must remain readable.
- All aggregate and stateful paper-trading paths use `(account_id, market, symbol)`.
- Daily-bar diagnostic identity is `(business_date, market, stock_id, adjust)`; existing diagnostics migrate to `a_share`.
- Keep valuation gaps unique by `(account_id, trade_date)` and retain the legacy `missing_symbols` list; `details` entries carry both `symbol` and `market`.
- Do not alter DAG schedules, task boundaries, or public API/CLI request contracts.
- Do not commit unless the user explicitly requests a commit.

---

## File Structure

- `storage/model/paper_trading.py`: ORM constraints and persisted `market` columns for positions, round trips, and daily-bar diagnostics.
- `storage/enum_migration.py`: Retains ownership of daily-bar adjustment/classification enums and JSON checks; it must continue to accept the market-qualified diagnostic table shape.
- `paper_trading/storage/enum_migration.py`: Paper-trading migration support for `paper_market` on round trips and diagnostics, legacy A-share diagnostic backfill, and position/diagnostic unique-constraint replacement with dependency-safe rollback.
- `paper_trading/storage/repository.py`: Market-required position/lot/round-trip/diagnostic repository methods and market-qualified rebuild aggregation.
- `paper_trading/services/order_service.py`: Market-qualified position and lot reads during order validation, reservation, and cancellation.
- `paper_trading/services/matching_service.py`: Market-qualified inventory changes and diagnostic writes while matching/cancelling/releasing orders.
- `paper_trading/services/order_delete_service.py`: Market-qualified sell-reservation restoration during historical replay.
- `paper_trading/services/round_trip_service.py`: Market-qualified open-cycle lookup and replay quantity accounting.
- `paper_trading/services/snapshot_service.py`: Stable market-qualified valuation-gap details for same-symbol positions.
- `test/paper_trading/storage/test_repository.py`: Repository identity, imported-lot rebuild, and diagnostic isolation tests.
- `test/paper_trading/storage/test_enum_migration.py`: PostgreSQL migration/backfill/rollback tests for paper-trading schema changes.
- `test/storage/test_storage_enum_migration.py`: PostgreSQL migration/backfill/rollback tests for daily-bar diagnostic schema changes.
- `test/paper_trading/services/test_order_service.py`: Same-symbol market-isolated reservation and sellability tests.
- `test/paper_trading/services/test_matching_service.py`: Same-symbol fills, frozen inventory, diagnostics, and realized-PnL isolation tests.
- `test/paper_trading/services/test_order_delete_service.py`: Historical replay reservation isolation tests.
- `test/paper_trading/services/test_round_trip_service.py`: Market-qualified round-trip creation and rebuild tests.
- `test/paper_trading/services/test_snapshot_service.py`: Same-symbol cross-market snapshot valuation-gap tests.
- `docs/paper_trading.md`: Update the paper-trading identity statement and diagnostic behavior only if code changes affect current user-facing documentation.

### Task 1: Add Market-Qualified ORM Schema And Migration Coverage

**Files:**
- Modify: `storage/model/paper_trading.py:120-158,260-287,400-422`
- Modify: `paper_trading/storage/enum_migration.py:103-267,488-597`
- Modify: `test/paper_trading/storage/test_enum_migration.py:66-90,142-169,389-398`
- Modify: `test/storage/test_storage_enum_migration.py`
- Modify: `test/paper_trading/storage/test_models.py`

**Interfaces:**
- Consumes: `Market` from `paper_trading.domain.enums` and the existing enum-governance adapter APIs.
- Produces: `PaperPosition` unique constraint `uq_paper_positions_account_market_symbol`; non-null `PaperPositionRoundTrip.market` and `DailyBarDiagnostic.market`, each defaulting to `a_share`; diagnostic unique constraint `uq_daily_bar_diagnostics_business_market_key`.

- [ ] **Step 1: Write failing SQLite model assertions**

Add tests asserting the exact ORM constraints and columns:

```python
def test_position_identity_is_qualified_by_market():
    constraints = {constraint.name: constraint for constraint in PaperPosition.__table__.constraints}
    assert tuple(constraints["uq_paper_positions_account_market_symbol"].columns.keys()) == (
        "account_id", "market", "symbol",
    )


def test_round_trip_and_diagnostic_persist_a_share_market_by_default(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    assert PaperPositionRoundTrip.__table__.c.market.server_default.arg == "a_share"
    assert DailyBarDiagnostic.__table__.c.market.server_default.arg == "a_share"
```

- [ ] **Step 2: Run the model tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_models.py -v`

Expected: FAIL because the old position unique constraint remains and round trips/diagnostics have no `market` column.

- [ ] **Step 3: Update ORM mappings minimally**

Replace the position constraint and add the two market columns using the established enum mapping:

```python
class PaperPosition(Base):
    __table_args__ = (
        UniqueConstraint("account_id", "market", "symbol", name="uq_paper_positions_account_market_symbol"),
    )


class PaperPositionRoundTrip(Base):
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class DailyBarDiagnostic(Base):
    __table_args__ = (
        UniqueConstraint(
            "business_date", "market", "stock_id", "adjust", name="uq_daily_bar_diagnostics_business_market_key"
        ),
    )
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )
```

- [ ] **Step 4: Extend migration declarations and operations**

Add the round-trip and `daily_bar_diagnostics.market` columns to `PAPER_TRADING_ENUM_GROUPS` under the existing `paper_market` type, including `ix_paper_position_round_trips_market` and `ix_daily_bar_diagnostics_market`. Add `DailyBarDiagnostic.__table__` to the paper adapter's governed tables so the existing `paper_market` owner adds/backfills its diagnostic column as `a_share` and verifies the type/default/index.

Extend the paper-trading migration to replace `uq_paper_positions_account_symbol` with `uq_paper_positions_account_market_symbol` and `uq_daily_bar_diagnostics_business_key` with `uq_daily_bar_diagnostics_business_market_key`. On rollback, restore each old key only after preflight confirms no cross-market collision would be collapsed. Keep `storage/enum_migration.py` unchanged except for compatibility assertions: it continues to govern diagnostic `adjust`, `classification`, and `provider_outcomes` checks, not `paper_market`.

- [ ] **Step 5: Add PostgreSQL migration tests before completing implementation**

Extend legacy schemas with the old constraints and diagnostic rows, then assert exact upgraded and rolled-back catalog/data behavior:

```python
connection.execute(
    text("INSERT INTO daily_bar_diagnostics (business_date, stock_id, adjust, classification, provider_outcomes) "
         "VALUES ('2026-08-10', '000001', 'bfq', 'downloaded', '[]'::jsonb)")
)
migrate_paper_trading_enums(connection)
assert connection.execute(text("SELECT market::text FROM daily_bar_diagnostics")).scalar_one() == "a_share"
assert _constraint_columns(connection, "paper_positions", "uq_paper_positions_account_market_symbol") == (
    "account_id", "market", "symbol",
)
```

Add rollback collision tests that insert same-symbol rows in both markets after upgrade and assert migration rollback refuses to collapse them.

- [ ] **Step 6: Run focused schema tests**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_enum_migration.py test/storage/test_storage_enum_migration.py -v`

Expected: PASS; PostgreSQL tests may be skipped only when `TEST_POSTGRESQL_URL` is unset.

### Task 2: Make Repository Identity APIs Market-Qualified

**Files:**
- Modify: `paper_trading/storage/repository.py:66-169,622-670,831-885,938-1055`
- Modify: `test/paper_trading/storage/test_repository.py:96-173,734-942,1117-1129`

**Interfaces:**
- Consumes: Task 1’s `market` columns and `(account_id, market, symbol)` uniqueness.
- Produces: `get_position(account_id: int, market: str, symbol: str)`, `get_lots(account_id: int, market: str, symbol: str)`, `get_open_round_trip(account_id: int, market: str, symbol: str)`, and market-qualified diagnostic methods.

- [ ] **Step 1: Write failing repository isolation tests**

```python
def test_positions_and_lots_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-collision", Decimal("100000"))
    repo.upsert_position(account.id, "a_share", "000001", 100, 10, Decimal("1000"))
    repo.upsert_position(account.id, "hk_connect", "000001", 200, 20, Decimal("2000"))

    assert repo.get_position(account.id, "a_share", "000001").total_quantity == 100
    assert repo.get_position(account.id, "hk_connect", "000001").total_quantity == 200


def test_diagnostics_with_same_symbol_are_isolated_by_market(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    a_share = repo.upsert_daily_bar_diagnostic(date(2026, 8, 10), "a_share", "000001", "bfq", "missing_exact_date", [], False)
    hk = repo.upsert_daily_bar_diagnostic(date(2026, 8, 10), "hk_connect", "000001", "bfq", "missing_exact_date", [], False)
    assert a_share.id != hk.id
```

- [ ] **Step 2: Run repository tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -v`

Expected: FAIL because repository signatures do not accept `market` and diagnostic conflict targets omit it.

- [ ] **Step 3: Change repository signatures and all filters**

Require `market` for stateful lookups and normalize it with `Market(market).value` at each repository boundary. Update every query and PostgreSQL/SQLite conflict target:

```python
def get_position(self, account_id: int, market: str, symbol: str) -> PaperPosition | None:
    return self.session.query(PaperPosition).filter(
        PaperPosition.account_id == account_id,
        PaperPosition.market == Market(market).value,
        PaperPosition.symbol == symbol,
    ).one_or_none()

def get_lots(self, account_id: int, market: str, symbol: str) -> list[PaperPositionLot]:
    return list(self.session.query(PaperPositionLot).filter(
        PaperPositionLot.account_id == account_id,
        PaperPositionLot.market == Market(market).value,
        PaperPositionLot.symbol == symbol,
    ).order_by(PaperPositionLot.buy_trade_date.asc(), PaperPositionLot.id.asc()).all())
```

Make `upsert_position`, `create_round_trip`, `get_open_round_trip`, `upsert_daily_bar_diagnostic`, and `has_unresolved_daily_bar_diagnostic` similarly market-explicit. Update the daily-bar delayed rebuild join to require `DailyBarDiagnostic.market == PaperOrder.market` and retain its A-share order filter.

- [ ] **Step 4: Rebuild imported state by market and symbol**

Replace `market_by_symbol`, `total_qty[symbol]`, and `total_cost[symbol]` with tuple-keyed maps:

```python
identity = (lot.market, lot.symbol)
total_qty[identity] += int(lot.remaining_quantity)
total_cost[identity] += Decimal(lot.cost_price) * int(lot.remaining_quantity)
...
for market, symbol in total_qty:
    self.session.add(PaperPosition(account_id=account_id, market=market, symbol=symbol, ...))
```

Remove the old conflicting-markets rejection. Replace its test with assertions that both imported positions are restored independently.

- [ ] **Step 5: Run repository tests to verify passing behavior**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -v`

Expected: PASS, including the two-market imported-lot rebuild and duplicate-symbol diagnostics.

### Task 3: Propagate Market Identity Through Orders, Matching, Replay, And Round Trips

**Files:**
- Modify: `paper_trading/services/order_service.py:180-239,362-378,427-554`
- Modify: `paper_trading/services/matching_service.py:145-181,208-317`
- Modify: `paper_trading/services/order_delete_service.py:226-274`
- Modify: `paper_trading/services/round_trip_service.py:12-70`
- Modify: `test/paper_trading/services/test_order_service.py`
- Modify: `test/paper_trading/services/test_matching_service.py`
- Modify: `test/paper_trading/services/test_order_delete_service.py`
- Modify: `test/paper_trading/services/test_round_trip_service.py`

**Interfaces:**
- Consumes: Task 2’s market-required repository methods.
- Produces: All order reservation, matching, replay, fill, and round-trip flows route inventory and cycles by an order/trade’s persisted `market`.

- [ ] **Step 1: Write failing same-symbol service tests**

Use one account with a deliberately shared bare symbol. Seed separate A-share and HK Connect positions/lots, then prove an HK sell cannot freeze or consume A-share inventory:

```python
def test_hk_sell_freezes_only_hk_position(sqlite_session):
    repo, service, account = make_market_collision_service(sqlite_session)
    order = service.place_order(account.id, "000001", OrderSide.SELL, 100, Decimal("10"), DATE, market="hk_connect")
    assert order.status == "accepted"
    assert repo.get_position(account.id, "hk_connect", "000001").frozen_quantity == 100
    assert repo.get_position(account.id, "a_share", "000001").frozen_quantity == 0
```

Add matching tests that fill a sell in one market and assert quantity, cost, lots, and realized PnL change only for that market. Add replay tests that restore an A-share and HK Connect sell reservation independently. Add round-trip tests that buy/sell the same symbol in two markets and create two independent cycles.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_round_trip_service.py -v`

Expected: FAIL at old two-argument repository calls or with cross-market quantity/freeze mutations.

- [ ] **Step 3: Pass market at every stateful service call**

Apply the order/trade market to repository reads and writes. The critical replacement shape is:

```python
position = self.repo.get_position(order.account_id, order.market, order.symbol)
lots = self.repo.get_lots(order.account_id, order.market, order.symbol)
self.repo.upsert_position(order.account_id, order.market, order.symbol, ...)
```

Update `OrderService` HK odd-lot checks, A-share/HK sell acceptance, and cancellation. Update `MatchingService` rejection, buy settlement, sell settlement, closed-position cleanup, and diagnostic methods. Update `OrderDeleteService._restore_single_reservation` to use `order.market` for positions/lots. Keep cash ledger behavior unchanged because cash is account-level rather than security-level.

- [ ] **Step 4: Make diagnostics and round trips market-qualified**

Use `order.market` in all matching diagnostic calls:

```python
self.repo.upsert_daily_bar_diagnostic(
    order.trade_date, order.market, order.symbol, "bfq", "missing_exact_date", outcomes, False
)
```

Within `RoundTripService`, use `trade.market` for open-cycle lookup/creation and key rebuild quantities by `(trade.market, trade.symbol)`:

```python
identity = (trade.market, trade.symbol)
current_quantity = quantities.get(identity, 0)
quantities[identity] = current_quantity
```

- [ ] **Step 5: Run targeted service tests to verify passing behavior**

Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_round_trip_service.py -v`

Expected: PASS. Existing single-market A-share/HK tests must still pass after adding explicit market arguments.

### Task 4: Preserve Market Identity In Snapshots And Valuation Gaps

**Files:**
- Modify: `paper_trading/services/snapshot_service.py:75-97`
- Modify: `test/paper_trading/services/test_snapshot_service.py:171-280`
- Modify: `test/paper_trading/services/test_matching_service.py:102-155`

**Interfaces:**
- Consumes: market-qualified positions from Task 2 and market-aware bar routing already used by `MarketDataProvider`.
- Produces: valuation gaps that retain an authoritative `{symbol, market, error}` entry per missing position, including same-symbol positions in distinct markets.

- [ ] **Step 1: Write a failing duplicate-symbol valuation-gap test**

```python
def test_snapshot_gap_retains_market_for_same_symbol_in_two_markets(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("snapshot-collision", Decimal("100000"))
    repo.upsert_position(account.id, "a_share", "000001", 100, 0, Decimal("900"))
    repo.upsert_position(account.id, "hk_connect", "000001", 200, 0, Decimal("1800"))

    gap = SnapshotService(repo, MissingBarProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 10)).valuation_gap
    assert gap.missing_symbols == ["000001", "000001"]
    assert {(item["market"], item["symbol"]) for item in gap.details} == {
        ("a_share", "000001"), ("hk_connect", "000001"),
    }
```

- [ ] **Step 2: Run snapshot tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py -v`

Expected: FAIL before repository identity calls are propagated or because legacy detail construction loses one market route.

- [ ] **Step 3: Preserve deterministic detailed identity**

Keep `missing_symbols` as a list of symbols for response compatibility, allowing duplicate symbols when two markets are missing. Build and sort `details` deterministically by `(market, symbol)` so cross-market references cannot collapse:

```python
details.append({"symbol": position.symbol, "market": position.market, "error": str(exc)})
details.sort(key=lambda item: (str(item["market"]), str(item["symbol"])))
```

Keep the existing resolved-gap path unchanged except that it clears the complete market-qualified details list.

- [ ] **Step 4: Run snapshot and matching regression tests**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py -v`

Expected: PASS, including market-aware daily-bar calls and resolved valuation gaps.

### Task 5: Run Broader Verification And Update Affected Documentation

**Files:**
- Modify: `docs/paper_trading.md:256-267,361-363,437-441` only if final behavior needs clarification.
- Test: `test/paper_trading/`
- Test: `test/storage/test_enum_governance.py`
- Test: `test/storage/test_enum_governance_smoke.py`

**Interfaces:**
- Consumes: Completed schema, repository, service, and regression test changes from Tasks 1-4.
- Produces: verified implementation and narrowly updated user documentation, if needed.

- [ ] **Step 1: Update documentation only for changed user-visible guarantees**

Add concise language stating that paper-trading position identity is market-qualified and that missing-bar/valuation diagnostics preserve market identity. Do not document ETF support or modify unrelated deployment procedures.

- [ ] **Step 2: Format and lint the changed code**

Run: `uv run ruff format storage/model/paper_trading.py storage/enum_migration.py paper_trading/storage/enum_migration.py paper_trading/storage/repository.py paper_trading/services/order_service.py paper_trading/services/matching_service.py paper_trading/services/order_delete_service.py paper_trading/services/round_trip_service.py paper_trading/services/snapshot_service.py test/paper_trading test/storage/test_storage_enum_migration.py`

Run: `uv run ruff check storage/model/paper_trading.py storage/enum_migration.py paper_trading/storage/enum_migration.py paper_trading/storage/repository.py paper_trading/services/order_service.py paper_trading/services/matching_service.py paper_trading/services/order_delete_service.py paper_trading/services/round_trip_service.py paper_trading/services/snapshot_service.py test/paper_trading test/storage/test_storage_enum_migration.py`

Expected: both commands exit zero.

- [ ] **Step 3: Run focused and schema-governance tests**

Run: `uv run pytest test/paper_trading test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/storage/test_storage_enum_migration.py -v`

Expected: PASS; PostgreSQL-dependent migration tests may be skipped only when `TEST_POSTGRESQL_URL` is not configured.

- [ ] **Step 4: Run type checks and inspect the final diff**

Run: `uv run mypy`

Run: `git diff --check`

Run: `git diff --stat`

Expected: mypy exits zero within the repository’s configured scope; no whitespace errors; diff contains only issue #42 implementation, focused tests, and affected documentation.
