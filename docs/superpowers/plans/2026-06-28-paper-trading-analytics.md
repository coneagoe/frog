# Paper Trading Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-backed paper trading analytics dashboard with QuantStats-style metrics and full-position round-trip trade quality statistics.

**Architecture:** Persist round-trip position cycles in the backend, compute analytics through a dedicated service and API, then render the analytics page from that API. Keep metric calculation server-side so win rate, payoff ratio, profit factor, execution statistics, and drawdown use one tested source of truth.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy ORM, Pydantic v2, pytest, Next.js 15, React 19, TypeScript, Vitest, Testing Library.

## Global Constraints

- Use `uv run` for Python commands in this repository.
- Do not run bare `python` or `python3` for project tasks.
- Do not commit unless the user explicitly asks for a commit.
- Storage table changes must update `tools/db_common.sh`.
- Round-trip metrics use full-position cycles: a cycle opens when symbol quantity moves from zero to positive and closes when it returns to zero.
- Partial exits do not count toward win rate, payoff ratio, profit factor, or consecutive win/loss metrics.
- Return `null` plus an explicit reason for unavailable metrics instead of misleading zeros.
- Keep changes focused on paper trading analytics; do not change DAG schedules, task boundaries, or unrelated frontend navigation behavior.

---

## File Structure

- Modify `storage/model/paper_trading.py`: add the `PaperPositionRoundTrip` ORM model and table name constant.
- Modify `paper_trading/storage/models.py`: re-export `PaperPositionRoundTrip` with the existing paper trading ORM imports.
- Modify `paper_trading/storage/repository.py`: add round-trip CRUD/query helpers and account deletion cleanup.
- Modify `tools/db_common.sh`: include `paper_position_round_trips` in `BUSINESS_TABLES`.
- Create `paper_trading/services/round_trip_service.py`: own open/update/close and rebuild logic for full-position cycles.
- Create `paper_trading/services/analytics_service.py`: compute activity, execution, trade quality, and risk/drawdown metrics.
- Create `paper_trading/schemas/analytics.py`: Pydantic API response schemas.
- Create `paper_trading/api/routers/analytics.py`: expose `GET /paper/accounts/{account_id}/analytics`.
- Modify `paper_trading/api/app.py`: include the analytics router.
- Modify `paper_trading/services/matching_service.py`: call `RoundTripService` after buy/sell fills.
- Add backend tests under `test/paper_trading/storage/`, `test/paper_trading/services/`, and `test/paper_trading/api/`.
- Modify `frontend/paper-trading/lib/types.ts`: add analytics response types.
- Modify `frontend/paper-trading/lib/api-client.ts`: add `getAnalytics(accountId)`.
- Modify files under `frontend/paper-trading/features/analytics/`: render the new analytics sections.
- Modify `frontend/paper-trading/features/analytics/analytics-page.test.tsx`: cover new analytics rendering and unavailable metric states.
- Update `docs/paper_trading.md`: document the analytics endpoint and round-trip metric口径.

---

### Task 1: Add Round-Trip Storage

**Files:**
- Modify: `storage/model/paper_trading.py:18`
- Modify: `paper_trading/storage/models.py:1`
- Modify: `paper_trading/storage/repository.py:1`
- Modify: `tools/db_common.sh:35`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Consumes: existing `PaperTradingRepository`, SQLAlchemy `Session`, and `Base.metadata.create_all()` test setup.
- Produces: `PaperPositionRoundTrip` ORM model and repository methods `create_round_trip()`, `get_open_round_trip()`, `update_round_trip()`, `list_round_trips()`, and `delete_round_trips()`.

- [ ] **Step 1: Write failing repository storage tests**

Append tests to `test/paper_trading/storage/test_repository.py`:

```python
from datetime import date
from decimal import Decimal


def test_round_trip_repository_creates_and_lists_closed_cycle(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))

    cycle = repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=1,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )
    repo.update_round_trip(
        cycle,
        close_trade_id=2,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        realized_pnl=Decimal("90.0000"),
        return_pct=Decimal("0.090000"),
        holding_days=4,
        status="closed",
    )
    sqlite_session.commit()

    rows = repo.list_round_trips(account.id)
    assert len(rows) == 1
    assert rows[0].symbol == "000001.SZ"
    assert rows[0].status == "closed"
    assert rows[0].realized_pnl == Decimal("90.0000")
```

Add a second test:

```python
def test_delete_account_removes_round_trips(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("delete-round-trips", Decimal("100000.00"))
    repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=1,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    assert repo.delete_account(account.id) is True
    sqlite_session.commit()

    assert repo.list_round_trips(account.id) == []
```

- [ ] **Step 2: Run the repository tests and verify failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: FAIL with an error that `PaperTradingRepository` has no `create_round_trip` method or the round-trip table does not exist.

- [ ] **Step 3: Add the ORM model**

In `storage/model/paper_trading.py`, add the table constant near the other `tb_name_paper_*` constants:

```python
tb_name_paper_position_round_trips = "paper_position_round_trips"
```

Add the model after `PaperTrade` and before `PaperAccountSnapshot`:

```python
class PaperPositionRoundTrip(Base):
    __tablename__ = tb_name_paper_position_round_trips

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    open_trade_id = Column(Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=False, index=True)
    close_trade_id = Column(Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=True, index=True)
    open_trade_date = Column(Date, nullable=False, index=True)
    close_trade_date = Column(Date, nullable=True, index=True)
    entry_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    exit_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    fees = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    return_pct = Column(Numeric(20, 6), nullable=True)
    holding_days = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, server_default="open", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: Export the model and update table list**

In `paper_trading/storage/models.py`, add `PaperPositionRoundTrip` to the import/export list that currently re-exports paper trading ORM classes.

In `tools/db_common.sh`, insert `paper_position_round_trips` after `paper_trades`:

```bash
  paper_trades
  paper_position_round_trips
  paper_account_snapshots
```

- [ ] **Step 5: Add repository methods**

In `paper_trading/storage/repository.py`, import `PaperPositionRoundTrip` and add it to `delete_account()` before deleting the account:

```python
self.session.query(PaperPositionRoundTrip).filter(PaperPositionRoundTrip.account_id == account_id).delete(
    synchronize_session=False
)
```

Add these methods to `PaperTradingRepository`:

```python
def create_round_trip(
    self,
    account_id: int,
    symbol: str,
    open_trade_id: int,
    open_trade_date: date,
    entry_amount: Decimal,
    fees: Decimal,
) -> PaperPositionRoundTrip:
    cycle = PaperPositionRoundTrip(
        account_id=account_id,
        symbol=symbol,
        open_trade_id=open_trade_id,
        open_trade_date=open_trade_date,
        entry_amount=entry_amount,
        fees=fees,
        status="open",
    )
    self.session.add(cycle)
    self.session.flush()
    return cycle

def get_open_round_trip(self, account_id: int, symbol: str) -> PaperPositionRoundTrip | None:
    return cast(
        PaperPositionRoundTrip | None,
        self.session.query(PaperPositionRoundTrip)
        .filter(
            PaperPositionRoundTrip.account_id == account_id,
            PaperPositionRoundTrip.symbol == symbol,
            PaperPositionRoundTrip.status == "open",
        )
        .order_by(PaperPositionRoundTrip.id.desc())
        .one_or_none(),
    )

def update_round_trip(self, cycle: PaperPositionRoundTrip, **values: Any) -> PaperPositionRoundTrip:
    for key, value in values.items():
        setattr(cycle, key, value)
    cycle.updated_at = datetime.now(timezone.utc)
    self.session.flush()
    return cycle

def list_round_trips(self, account_id: int) -> list[PaperPositionRoundTrip]:
    return list(
        self.session.query(PaperPositionRoundTrip)
        .filter(PaperPositionRoundTrip.account_id == account_id)
        .order_by(PaperPositionRoundTrip.open_trade_date.asc(), PaperPositionRoundTrip.id.asc())
        .all()
    )

def delete_round_trips(self, account_id: int) -> int:
    deleted = self.session.query(PaperPositionRoundTrip).filter(
        PaperPositionRoundTrip.account_id == account_id
    ).delete(synchronize_session=False)
    self.session.flush()
    return int(deleted)
```

- [ ] **Step 6: Run focused repository tests**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: PASS for the new round-trip tests and existing repository tests.

---

### Task 2: Track Round Trips During Matching

**Files:**
- Create: `paper_trading/services/round_trip_service.py`
- Modify: `paper_trading/services/matching_service.py:18`
- Test: `test/paper_trading/services/test_round_trip_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: repository methods from Task 1 and `PaperTrade` rows created by `repo.create_trade()`.
- Produces: `RoundTripService.record_fill(trade, post_position_quantity)` and persisted open/closed round-trip rows.

- [ ] **Step 1: Write failing service tests**

Create `test/paper_trading/services/test_round_trip_service.py` with these tests:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'round_trip.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_record_buy_opens_round_trip(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.FILLED)
    trade = repo.create_trade(order.id, account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), Decimal("1000.0000"), Decimal("5.0000"), date(2026, 6, 16))

    RoundTripService(repo).record_fill(trade, post_position_quantity=100)
    session.commit()

    cycle = repo.get_open_round_trip(account.id, "000001.SZ")
    assert cycle is not None
    assert cycle.entry_amount == Decimal("1000.0000")
    assert cycle.fees == Decimal("5.0000")
    engine.dispose()


def test_record_full_sell_closes_round_trip(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    buy_order = repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.FILLED)
    buy_trade = repo.create_trade(buy_order.id, account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), Decimal("1000.0000"), Decimal("5.0000"), date(2026, 6, 16))
    service = RoundTripService(repo)
    service.record_fill(buy_trade, post_position_quantity=100)
    sell_order = repo.create_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("11.00"), date(2026, 6, 20), OrderStatus.FILLED)
    sell_trade = repo.create_trade(sell_order.id, account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("11.00"), Decimal("1100.0000"), Decimal("6.0000"), date(2026, 6, 20))

    service.record_fill(sell_trade, post_position_quantity=0)
    session.commit()

    cycle = repo.list_round_trips(account.id)[0]
    assert cycle.status == "closed"
    assert cycle.exit_amount == Decimal("1100.0000")
    assert cycle.fees == Decimal("11.0000")
    assert cycle.realized_pnl == Decimal("89.0000")
    assert cycle.return_pct == Decimal("0.089000")
    assert cycle.holding_days == 4
    engine.dispose()
```

- [ ] **Step 2: Run the service tests and verify failure**

Run: `uv run pytest test/paper_trading/services/test_round_trip_service.py -q`

Expected: FAIL with `ModuleNotFoundError` for `paper_trading.services.round_trip_service`.

- [ ] **Step 3: Implement `RoundTripService`**

Create `paper_trading/services/round_trip_service.py`:

```python
from decimal import Decimal

from paper_trading.domain.enums import OrderSide
from paper_trading.storage.models import PaperTrade
from paper_trading.storage.repository import PaperTradingRepository


class RoundTripService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def record_fill(self, trade: PaperTrade, post_position_quantity: int) -> None:
        side = OrderSide(str(trade.side))
        if side == OrderSide.BUY:
            self._record_buy(trade)
            return
        self._record_sell(trade, post_position_quantity)

    def _record_buy(self, trade: PaperTrade) -> None:
        cycle = self.repo.get_open_round_trip(trade.account_id, trade.symbol)
        if cycle is None:
            self.repo.create_round_trip(
                account_id=trade.account_id,
                symbol=trade.symbol,
                open_trade_id=trade.id,
                open_trade_date=trade.trade_date,
                entry_amount=Decimal(trade.amount).quantize(Decimal("0.0001")),
                fees=Decimal(trade.fees).quantize(Decimal("0.0001")),
            )
            return
        self.repo.update_round_trip(
            cycle,
            entry_amount=(Decimal(cycle.entry_amount or 0) + Decimal(trade.amount)).quantize(Decimal("0.0001")),
            fees=(Decimal(cycle.fees or 0) + Decimal(trade.fees)).quantize(Decimal("0.0001")),
        )

    def _record_sell(self, trade: PaperTrade, post_position_quantity: int) -> None:
        cycle = self.repo.get_open_round_trip(trade.account_id, trade.symbol)
        if cycle is None:
            return
        exit_amount = (Decimal(cycle.exit_amount or 0) + Decimal(trade.amount)).quantize(Decimal("0.0001"))
        fees = (Decimal(cycle.fees or 0) + Decimal(trade.fees)).quantize(Decimal("0.0001"))
        realized_pnl = (exit_amount - Decimal(cycle.entry_amount or 0) - fees).quantize(Decimal("0.0001"))
        values = {
            "close_trade_id": trade.id,
            "close_trade_date": trade.trade_date,
            "exit_amount": exit_amount,
            "fees": fees,
            "realized_pnl": realized_pnl,
        }
        if post_position_quantity == 0:
            entry_amount = Decimal(cycle.entry_amount or 0)
            values["return_pct"] = (realized_pnl / entry_amount).quantize(Decimal("0.000001")) if entry_amount else None
            values["holding_days"] = (trade.trade_date - cycle.open_trade_date).days
            values["status"] = "closed"
        self.repo.update_round_trip(cycle, **values)
```

- [ ] **Step 4: Integrate matching service**

In `paper_trading/services/matching_service.py`, import `RoundTripService` and initialize it in `MatchingService.__init__`:

```python
from paper_trading.services.round_trip_service import RoundTripService
```

```python
self.round_trip_service = RoundTripService(repo)
```

After `_settle_buy(...)`, call:

```python
position = self.repo.get_position(order.account_id, order.symbol)
self.round_trip_service.record_fill(trade, post_position_quantity=0 if position is None else int(position.total_quantity or 0))
```

After `_settle_sell(...)`, call the same snippet so the sell can close the cycle when the post-settlement quantity is zero.

- [ ] **Step 5: Add matching integration test**

Append to `test/paper_trading/services/test_matching_service.py`:

```python
def test_matching_closes_round_trip_when_position_returns_to_zero(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("round-trip-demo", Decimal("100000.00"))
    order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    matching_service.run(trade_date)
    next_date = date(2026, 6, 17)
    order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.50"), next_date)
    matching_service.run(next_date)
    session.commit()

    cycles = repo.list_round_trips(account.id)
    assert len(cycles) == 1
    assert cycles[0].status == "closed"
    assert cycles[0].close_trade_date == next_date
    engine.dispose()
```

Before running this new test, update `_services()` in the same file so the `FakeHistoryStorage` DataFrame for `"000001"` includes a second row for `2026-06-17`:

```python
COL_STOCK_ID: ["000001", "000001"],
COL_DATE: ["2026-06-16", "2026-06-17"],
COL_OPEN: [9.5, 10.2],
COL_HIGH: [10.5, 10.8],
COL_LOW: [9.0, 10.0],
COL_CLOSE: [10.0, 10.5],
```

- [ ] **Step 6: Run focused matching tests**

Run: `uv run pytest test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py -q`

Expected: PASS.

---

### Task 3: Add Historical Rebuild

**Files:**
- Modify: `paper_trading/services/round_trip_service.py`
- Test: `test/paper_trading/services/test_round_trip_service.py`

**Interfaces:**
- Consumes: `repo.list_trades(account_id)`, `repo.delete_round_trips(account_id)`, and `RoundTripService.record_fill()`.
- Produces: `RoundTripService.rebuild_account(account_id: int) -> list[PaperPositionRoundTrip]`.

- [ ] **Step 1: Write failing rebuild test**

Append to `test/paper_trading/services/test_round_trip_service.py`:

```python
def test_rebuild_account_recreates_multiple_closed_cycles(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("rebuild-demo", Decimal("100000.00"))
    for idx, side, price, amount, fees, trade_date in [
        (1, OrderSide.BUY, "10.00", "1000.0000", "5.0000", date(2026, 6, 16)),
        (2, OrderSide.SELL, "11.00", "1100.0000", "6.0000", date(2026, 6, 20)),
        (3, OrderSide.BUY, "9.00", "900.0000", "5.0000", date(2026, 6, 21)),
        (4, OrderSide.SELL, "8.00", "800.0000", "5.0000", date(2026, 6, 25)),
    ]:
        order = repo.create_order(account.id, "000001.SZ", side, 100, Decimal(price), trade_date, OrderStatus.FILLED)
        repo.create_trade(order.id, account.id, "000001.SZ", side, 100, Decimal(price), Decimal(amount), Decimal(fees), trade_date)

    cycles = RoundTripService(repo).rebuild_account(account.id)
    session.commit()

    assert [cycle.status for cycle in cycles] == ["closed", "closed"]
    assert cycles[0].realized_pnl == Decimal("89.0000")
    assert cycles[1].realized_pnl == Decimal("-110.0000")
    engine.dispose()
```

- [ ] **Step 2: Run rebuild test and verify failure**

Run: `uv run pytest test/paper_trading/services/test_round_trip_service.py::test_rebuild_account_recreates_multiple_closed_cycles -q`

Expected: FAIL because `rebuild_account` does not exist.

- [ ] **Step 3: Implement rebuild logic**

Add to `RoundTripService`:

```python
def rebuild_account(self, account_id: int):
    self.repo.delete_round_trips(account_id)
    quantities: dict[str, int] = {}
    trades = sorted(self.repo.list_trades(account_id), key=lambda trade: (trade.trade_date, trade.id))
    for trade in trades:
        side = OrderSide(str(trade.side))
        current_quantity = quantities.get(trade.symbol, 0)
        if side == OrderSide.BUY:
            current_quantity += int(trade.quantity)
        else:
            current_quantity -= int(trade.quantity)
        quantities[trade.symbol] = current_quantity
        self.record_fill(trade, post_position_quantity=current_quantity)
    return self.repo.list_round_trips(account_id)
```

- [ ] **Step 4: Run round-trip tests**

Run: `uv run pytest test/paper_trading/services/test_round_trip_service.py -q`

Expected: PASS.

---

### Task 4: Add Analytics Service and API

**Files:**
- Create: `paper_trading/schemas/analytics.py`
- Create: `paper_trading/services/analytics_service.py`
- Create: `paper_trading/api/routers/analytics.py`
- Modify: `paper_trading/api/app.py:3`
- Test: `test/paper_trading/services/test_analytics_service.py`
- Test: `test/paper_trading/api/test_analytics_api.py`

**Interfaces:**
- Consumes: orders, trades, snapshots, accounts, and round trips from `PaperTradingRepository`.
- Produces: `AnalyticsService.get_account_analytics(account_id: int) -> AnalyticsResponse` and `GET /paper/accounts/{account_id}/analytics`.

- [ ] **Step 1: Write failing analytics service tests**

Create `test/paper_trading/services/test_analytics_service.py` with tests for execution, trade quality, and drawdown:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_analytics_computes_execution_and_trade_quality(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))
    repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.FILLED)
    repo.create_order(account.id, "000002.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.REJECTED, rejection_code="INSUFFICIENT_CASH", rejection_reason="Insufficient cash")
    win = repo.create_round_trip(account.id, "000001.SZ", 1, date(2026, 6, 16), Decimal("1000.0000"), Decimal("5.0000"))
    repo.update_round_trip(win, close_trade_id=2, close_trade_date=date(2026, 6, 20), exit_amount=Decimal("1100.0000"), fees=Decimal("11.0000"), realized_pnl=Decimal("89.0000"), return_pct=Decimal("0.089000"), holding_days=4, status="closed")

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.execution.fill_rate == Decimal("0.500000")
    assert analytics.execution.rejection_rate == Decimal("0.500000")
    assert analytics.execution.reject_reasons[0].reason == "INSUFFICIENT_CASH"
    assert analytics.trade_quality.win_rate.value == Decimal("1.000000")
    assert analytics.trade_quality.profit_factor.reason == "no_losses"
    engine.dispose()
```

Add a drawdown test:

```python
def test_analytics_computes_total_return_and_drawdown(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("risk-demo", Decimal("100000.00"))
    repo.save_snapshot(account_id=account.id, trade_date=date(2026, 6, 16), cash_available=Decimal("100000.0000"), cash_frozen=Decimal("0"), market_value=Decimal("0"), total_assets=Decimal("100000.0000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), position_count=0, order_count=0, trade_count=0)
    repo.save_snapshot(account_id=account.id, trade_date=date(2026, 6, 17), cash_available=Decimal("110000.0000"), cash_frozen=Decimal("0"), market_value=Decimal("0"), total_assets=Decimal("110000.0000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), position_count=0, order_count=0, trade_count=0)
    repo.save_snapshot(account_id=account.id, trade_date=date(2026, 6, 18), cash_available=Decimal("99000.0000"), cash_frozen=Decimal("0"), market_value=Decimal("0"), total_assets=Decimal("99000.0000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), position_count=0, order_count=0, trade_count=0)

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("-0.010000")
    assert analytics.risk.max_drawdown.value == Decimal("-0.100000")
    assert analytics.risk.current_drawdown.value == Decimal("-0.100000")
    assert analytics.risk.sharpe.reason == "insufficient_data"
    engine.dispose()
```

- [ ] **Step 2: Run analytics service tests and verify failure**

Run: `uv run pytest test/paper_trading/services/test_analytics_service.py -q`

Expected: FAIL because `paper_trading.services.analytics_service` does not exist.

- [ ] **Step 3: Add analytics schemas**

Create `paper_trading/schemas/analytics.py` with Pydantic models:

```python
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MetricValue(BaseModel):
    value: Decimal | None = None
    reason: str | None = None


class ActivityBucket(BaseModel):
    period: str
    order_count: int
    trade_count: int
    filled_count: int
    rejected_count: int


class RejectReasonBucket(BaseModel):
    reason: str
    count: int


class OverviewAnalytics(BaseModel):
    total_assets: Decimal | None = None
    cash_available: Decimal | None = None
    market_value: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    total_return: MetricValue


class ExecutionAnalytics(BaseModel):
    order_count: int
    filled_count: int
    rejected_count: int
    fill_rate: Decimal | None
    rejection_rate: Decimal | None
    reject_reasons: list[RejectReasonBucket]


class RoundTripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    open_trade_date: date
    close_trade_date: date | None
    entry_amount: Decimal
    exit_amount: Decimal
    fees: Decimal
    realized_pnl: Decimal
    return_pct: Decimal | None
    holding_days: int | None
    status: str


class TradeQualityAnalytics(BaseModel):
    closed_count: int
    win_rate: MetricValue
    avg_win: MetricValue
    avg_loss: MetricValue
    payoff_ratio: MetricValue
    profit_factor: MetricValue
    consecutive_wins: int
    consecutive_losses: int
    avg_holding_days: MetricValue
    round_trips: list[RoundTripResponse]


class RiskAnalytics(BaseModel):
    max_drawdown: MetricValue
    current_drawdown: MetricValue
    sharpe: MetricValue
    sortino: MetricValue
    calmar: MetricValue


class AnalyticsResponse(BaseModel):
    overview: OverviewAnalytics
    activity_daily: list[ActivityBucket]
    activity_weekly: list[ActivityBucket]
    activity_monthly: list[ActivityBucket]
    execution: ExecutionAnalytics
    trade_quality: TradeQualityAnalytics
    risk: RiskAnalytics
```

- [ ] **Step 4: Implement analytics service**

Create `paper_trading/services/analytics_service.py`. Implement these exact public methods:

```python
class AnalyticsService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def get_account_analytics(self, account_id: int) -> AnalyticsResponse:
        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        orders = self.repo.list_orders(account_id)
        trades = self.repo.list_trades(account_id)
        snapshots = self.repo.list_snapshots(account_id)
        round_trips = self.repo.list_round_trips(account_id)
        return AnalyticsResponse(
            overview=self._overview(account.initial_cash, snapshots),
            activity_daily=self._activity(orders, trades, "daily"),
            activity_weekly=self._activity(orders, trades, "weekly"),
            activity_monthly=self._activity(orders, trades, "monthly"),
            execution=self._execution(orders),
            trade_quality=self._trade_quality(round_trips),
            risk=self._risk(snapshots),
        )
```

Use helper methods inside the same file. Quantize ratio metrics with `Decimal("0.000001")`. Return `MetricValue(value=None, reason="insufficient_data")` when a metric requires data that is missing. Return `MetricValue(value=None, reason="no_losses")` for `profit_factor` when closed round trips exist and no losing round trips exist.

- [ ] **Step 5: Add API router and app registration**

Create `paper_trading/api/routers/analytics.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from paper_trading.api.auth import require_api_token
from paper_trading.api.deps import get_session
from paper_trading.schemas.analytics import AnalyticsResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", tags=["paper-analytics"], dependencies=[Depends(require_api_token)])


@router.get("/{account_id}/analytics", response_model=AnalyticsResponse)
def get_account_analytics(account_id: int, session: Session = Depends(get_session)) -> AnalyticsResponse:
    repo = PaperTradingRepository(session)
    try:
        return AnalyticsService(repo).get_account_analytics(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

Modify `paper_trading/api/app.py`:

```python
from paper_trading.api.routers import accounts, analytics, matching, orders, snapshots
```

```python
app.include_router(analytics.router)
```

- [ ] **Step 6: Write API test**

Create `test/paper_trading/api/test_analytics_api.py`:

```python
from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_get_account_analytics_returns_execution_group(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-analytics", Decimal("100000.00"))
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["order_count"] == 0
    assert payload["trade_quality"]["closed_count"] == 0
    assert payload["risk"]["sharpe"]["reason"] == "insufficient_data"
```

- [ ] **Step 7: Run backend analytics tests**

Run: `uv run pytest test/paper_trading/services/test_analytics_service.py test/paper_trading/api/test_analytics_api.py -q`

Expected: PASS.

---

### Task 5: Render Frontend Analytics Dashboard

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:71`
- Modify: `frontend/paper-trading/lib/api-client.ts:2`
- Modify: `frontend/paper-trading/features/analytics/analytics-page.tsx:6`
- Modify: `frontend/paper-trading/features/analytics/analytics-summary.tsx:4`
- Modify: `frontend/paper-trading/features/analytics/analytics-tables.tsx:1`
- Test: `frontend/paper-trading/features/analytics/analytics-page.test.tsx`

**Interfaces:**
- Consumes: `GET /paper/accounts/{account_id}/analytics` response from Task 4.
- Produces: `getAnalytics(accountId: number): Promise<AnalyticsResponse>` and five analytics UI sections.

- [ ] **Step 1: Write failing frontend tests**

Modify `frontend/paper-trading/features/analytics/analytics-page.test.tsx` imports and API mock to include `getAnalytics`:

```tsx
import { getAnalytics, listAccounts, listCashLedger, listSnapshots, listTrades } from "@/lib/api-client";
```

```tsx
getAnalytics: vi.fn(),
```

Add this mock setup:

```tsx
const getAnalyticsMock = vi.mocked(getAnalytics);

const analyticsPayload = {
  overview: {
    total_assets: "106000.0000",
    cash_available: "90000.0000",
    market_value: "15000.0000",
    realized_pnl: "6000.0000",
    unrealized_pnl: "500.0000",
    total_return: { value: "0.060000", reason: null }
  },
  activity_daily: [{ period: "2026-06-16", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  activity_weekly: [{ period: "2026-W25", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  activity_monthly: [{ period: "2026-06", order_count: 3, trade_count: 2, filled_count: 2, rejected_count: 1 }],
  execution: {
    order_count: 3,
    filled_count: 2,
    rejected_count: 1,
    fill_rate: "0.666667",
    rejection_rate: "0.333333",
    reject_reasons: [{ reason: "INSUFFICIENT_CASH", count: 1 }]
  },
  trade_quality: {
    closed_count: 1,
    win_rate: { value: "1.000000", reason: null },
    avg_win: { value: "89.0000", reason: null },
    avg_loss: { value: null, reason: "no_losses" },
    payoff_ratio: { value: null, reason: "no_losses" },
    profit_factor: { value: null, reason: "no_losses" },
    consecutive_wins: 1,
    consecutive_losses: 0,
    avg_holding_days: { value: "4", reason: null },
    round_trips: [{ id: 1, symbol: "000001.SZ", open_trade_date: "2026-06-16", close_trade_date: "2026-06-20", entry_amount: "1000.0000", exit_amount: "1100.0000", fees: "11.0000", realized_pnl: "89.0000", return_pct: "0.089000", holding_days: 4, status: "closed" }]
  },
  risk: {
    max_drawdown: { value: "-0.100000", reason: null },
    current_drawdown: { value: "-0.050000", reason: null },
    sharpe: { value: null, reason: "insufficient_data" },
    sortino: { value: null, reason: "insufficient_data" },
    calmar: { value: null, reason: "insufficient_data" }
  }
};
```

In `beforeEach`, add:

```tsx
getAnalyticsMock.mockResolvedValue(analyticsPayload);
```

Add tests:

```tsx
it("renders QuantStats-style analytics sections", async () => {
  listSnapshotsMock.mockResolvedValue([]);

  render(<AnalyticsPage />);

  expect(await screen.findByText("Activity")).toBeInTheDocument();
  expect(screen.getByText("Execution")).toBeInTheDocument();
  expect(screen.getByText("Trade Quality")).toBeInTheDocument();
  expect(screen.getByText("Risk & Drawdown")).toBeInTheDocument();
  expect(screen.getByText("INSUFFICIENT_CASH")).toBeInTheDocument();
  expect(screen.getByText("000001.SZ")).toBeInTheDocument();
});

it("shows insufficient data reason for unavailable risk metrics", async () => {
  listSnapshotsMock.mockResolvedValue([]);

  render(<AnalyticsPage />);

  expect(await screen.findAllByText("insufficient_data")).not.toHaveLength(0);
});
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run in `frontend/paper-trading`: `npm run test -- analytics-page.test.tsx`

Expected: FAIL because `getAnalytics` and analytics sections do not exist.

- [ ] **Step 3: Add frontend analytics types and client**

In `frontend/paper-trading/lib/types.ts`, add `MetricValue`, `ActivityBucket`, `RejectReasonBucket`, `RoundTrip`, `OverviewAnalytics`, `ExecutionAnalytics`, `TradeQualityAnalytics`, `RiskAnalytics`, and `AnalyticsResponse` matching `paper_trading/schemas/analytics.py` field names.

In `frontend/paper-trading/lib/api-client.ts`, import `AnalyticsResponse` and add:

```ts
export function getAnalytics(accountId: number): Promise<AnalyticsResponse> {
  return apiGet<AnalyticsResponse>(`/accounts/${accountId}/analytics`);
}
```

- [ ] **Step 4: Add display helpers**

In `frontend/paper-trading/lib/format.ts`, add:

```ts
export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return "-";
  }
  return `${(numericValue * 100).toFixed(2)}%`;
}
```

- [ ] **Step 5: Render analytics sections**

In `analytics-page.tsx`, load analytics with `getAnalytics(accountId)` in `loadAccountData()`. Add `analytics` state:

```tsx
const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
```

Include `getAnalytics(accountId)` in `Promise.allSettled`, clear it when switching accounts, and pass it to new section components.

In `analytics-summary.tsx`, allow rendering from `analytics.overview` when present, falling back to the latest snapshot during partial-load states.

In `analytics-tables.tsx`, add tables for activity buckets, reject reason buckets, and round trips using the existing `DataTable` component.

Use section headings exactly:

```tsx
<section className="panel"><h2>Activity</h2>...</section>
<section className="panel"><h2>Execution</h2>...</section>
<section className="panel"><h2>Trade Quality</h2>...</section>
<section className="panel"><h2>Risk & Drawdown</h2>...</section>
```

- [ ] **Step 6: Run focused frontend tests**

Run in `frontend/paper-trading`: `npm run test -- analytics-page.test.tsx`

Expected: PASS.

---

### Task 6: Documentation and Verification

**Files:**
- Modify: `docs/paper_trading.md`
- Verify: backend and frontend focused tests

**Interfaces:**
- Consumes: implemented backend endpoint and frontend UI from Tasks 1-5.
- Produces: documented analytics endpoint and final verification evidence.

- [ ] **Step 1: Update paper trading docs**

In `docs/paper_trading.md`, add a short section named `Analytics` that documents:

```markdown
### Analytics

`GET /paper/accounts/{account_id}/analytics` returns account-level analytics for the paper trading dashboard.

The response includes:

- Activity: daily, weekly, and monthly order/trade frequency.
- Execution: fill rate, rejection rate, and reject reason distribution.
- Trade quality: full-position round-trip win rate, payoff ratio, profit factor, average win/loss, consecutive wins/losses, and holding days.
- Risk: total return, max drawdown, current drawdown, and optional Sharpe, Sortino, and Calmar metrics.

Round-trip metrics use full-position cycles. A cycle opens when an account's symbol quantity moves from zero to positive and closes when that symbol returns to zero. Partial exits update the open cycle but do not count as closed round trips.
```

- [ ] **Step 2: Run focused backend tests**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_analytics_service.py test/paper_trading/api/test_analytics_api.py -q`

Expected: PASS.

- [ ] **Step 3: Run focused frontend tests**

Run in `frontend/paper-trading`: `npm run test -- analytics-page.test.tsx`

Expected: PASS.

- [ ] **Step 4: Run lint/type checks only if focused tests pass**

Run: `uv run ruff check paper_trading test/paper_trading storage/model/paper_trading.py`

Expected: PASS.

Run in `frontend/paper-trading`: `npm run lint`

Expected: PASS or report existing unrelated lint failures separately from analytics changes.

- [ ] **Step 5: Inspect final diff**

Run: `git diff -- storage/model/paper_trading.py paper_trading storage/model tools/db_common.sh frontend/paper-trading docs/paper_trading.md docs/superpowers/plans/2026-06-28-paper-trading-analytics.md docs/superpowers/specs/2026-06-28-paper-trading-analytics-design.md`

Expected: Diff only contains paper trading analytics, table export, docs, and tests.

---

## Plan Review

- Spec coverage: Tasks 1-3 cover persisted full-position round trips and historical rebuild; Task 4 covers analytics API and metric definitions; Task 5 covers the five frontend sections; Task 6 covers docs and verification.
- Red-flag scan: no deferred implementation wording remains in this plan; every task lists exact files, public interfaces, commands, and expected outcomes.
- Type consistency: backend uses `PaperPositionRoundTrip`, `RoundTripService`, `AnalyticsService`, and `AnalyticsResponse` consistently; frontend uses `AnalyticsResponse` and `getAnalytics(accountId)` consistently.
