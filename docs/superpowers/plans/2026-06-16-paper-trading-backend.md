# Paper Trading Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP FastAPI backend for A-share paper trading with multi-account limit orders, asynchronous daily matching, cash/position accounting, fees, and snapshots.

**Architecture:** Add a modular `paper_trading/` package with domain rules, service classes, storage models/repository, Pydantic schemas, and thin FastAPI routers. Business logic lives below FastAPI so future strategy execution can call the same order and matching services.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2.x ORM, PostgreSQL/TimescaleDB in production, SQLite-compatible tests, pytest, uv.

---

## File Structure

- Create `paper_trading/domain/enums.py`: enum constants for side, order status, account status, cash event type, and matching run status.
- Create `paper_trading/domain/errors.py`: domain exception classes and stable error codes.
- Create `paper_trading/domain/fees.py`: A-share fee calculation using `Decimal`.
- Create `paper_trading/domain/rules.py`: A-share lot size, price range, cash, and position validations.
- Create `paper_trading/storage/models.py`: SQLAlchemy models for all `paper_*` tables.
- Create `paper_trading/storage/repository.py`: repository methods used by services.
- Create `paper_trading/storage/market_data.py`: market data protocol and in-memory test implementation.
- Create `paper_trading/services/account_service.py`: account creation and account queries.
- Create `paper_trading/services/order_service.py`: order acceptance, freeze/release, and cancellation.
- Create `paper_trading/services/matching_service.py`: trade-date matching and settlement.
- Create `paper_trading/services/snapshot_service.py`: persisted daily account snapshots.
- Create `paper_trading/schemas/*.py`: request/response schemas.
- Create `paper_trading/api/*.py` and `paper_trading/api/routers/*.py`: FastAPI app, dependencies, and routes.
- Modify `pyproject.toml`: add FastAPI and Uvicorn dependencies.
- Modify `storage/model/__init__.py`: import paper trading models so `Base.metadata.create_all()` includes them.
- Modify `tools/db_common.sh`: add paper trading tables to DB export/import coverage.
- Create focused tests under `test/paper_trading/`.

## Task 1: Dependencies And Package Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `paper_trading/__init__.py`
- Create: `paper_trading/domain/__init__.py`
- Create: `paper_trading/storage/__init__.py`
- Create: `paper_trading/services/__init__.py`
- Create: `paper_trading/schemas/__init__.py`
- Create: `paper_trading/api/__init__.py`
- Create: `paper_trading/api/routers/__init__.py`

- [ ] **Step 1: Add FastAPI dependencies**

Edit `pyproject.toml` dependencies to include these entries near the existing web/database dependencies:

```toml
"fastapi (>=0.115.0,<1.0.0)",
"uvicorn[standard] (>=0.30.0,<1.0.0)",
```

- [ ] **Step 2: Create package markers**

Create empty package marker files:

```bash
touch paper_trading/__init__.py paper_trading/domain/__init__.py paper_trading/storage/__init__.py paper_trading/services/__init__.py paper_trading/schemas/__init__.py paper_trading/api/__init__.py paper_trading/api/routers/__init__.py
```

- [ ] **Step 3: Refresh lock file**

Run:

```bash
uv lock
```

Expected: `uv.lock` updates successfully.

- [ ] **Step 4: Commit**

Run only after inspecting the diff and ensuring no unrelated files are staged:

```bash
git add pyproject.toml uv.lock paper_trading
git commit -m "feat: add paper trading backend package"
```

## Task 2: Domain Enums, Errors, Fees, And Rules

**Files:**
- Create: `paper_trading/domain/enums.py`
- Create: `paper_trading/domain/errors.py`
- Create: `paper_trading/domain/fees.py`
- Create: `paper_trading/domain/rules.py`
- Test: `test/paper_trading/domain/test_fees.py`
- Test: `test/paper_trading/domain/test_rules.py`

- [ ] **Step 1: Write fee tests**

Create `test/paper_trading/domain/test_fees.py`:

```python
from decimal import Decimal

from paper_trading.domain.enums import OrderSide
from paper_trading.domain.fees import FeeConfig, calculate_a_share_fees


def test_buy_fee_uses_minimum_commission_and_transfer_fee():
    fees = calculate_a_share_fees(
        side=OrderSide.BUY,
        amount=Decimal("1000.00"),
        config=FeeConfig(commission_rate=Decimal("0.0003"), min_commission=Decimal("5.00"), transfer_fee_rate=Decimal("0.00001")),
    )

    assert fees.commission == Decimal("5.00")
    assert fees.stamp_duty == Decimal("0.00")
    assert fees.transfer_fee == Decimal("0.01")
    assert fees.total == Decimal("5.01")


def test_sell_fee_includes_stamp_duty():
    fees = calculate_a_share_fees(
        side=OrderSide.SELL,
        amount=Decimal("20000.00"),
        config=FeeConfig(commission_rate=Decimal("0.0003"), min_commission=Decimal("5.00"), stamp_duty_rate=Decimal("0.0005")),
    )

    assert fees.commission == Decimal("6.00")
    assert fees.stamp_duty == Decimal("10.00")
    assert fees.total == Decimal("16.00")
```

- [ ] **Step 2: Write rule tests**

Create `test/paper_trading/domain/test_rules.py`:

```python
from decimal import Decimal

import pytest

from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.rules import ensure_lot_size, ensure_price_in_daily_range, ensure_sufficient_cash


def test_ensure_lot_size_accepts_100_share_multiple():
    ensure_lot_size(300)


def test_ensure_lot_size_rejects_non_100_share_multiple():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_lot_size(250)

    assert exc_info.value.code == "INVALID_LOT_SIZE"


def test_ensure_price_in_daily_range_rejects_price_outside_range():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_price_in_daily_range(Decimal("9.90"), low=Decimal("10.00"), high=Decimal("11.00"))

    assert exc_info.value.code == "PRICE_OUT_OF_RANGE"


def test_ensure_sufficient_cash_rejects_shortfall():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_sufficient_cash(available=Decimal("999.99"), required=Decimal("1000.00"))

    assert exc_info.value.code == "INSUFFICIENT_CASH"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest test/paper_trading/domain/test_fees.py test/paper_trading/domain/test_rules.py -q
```

Expected: FAIL because `paper_trading.domain` modules are not implemented yet.

- [ ] **Step 4: Implement domain modules**

Create `paper_trading/domain/enums.py`:

```python
from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class CashEventType(StrEnum):
    DEPOSIT = "deposit"
    FREEZE = "freeze"
    RELEASE = "release"
    TRADE = "trade"
    FEE = "fee"


class MatchingRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

Create `paper_trading/domain/errors.py`:

```python
from typing import Any


class PaperTradingError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
```

Create `paper_trading/domain/fees.py`:

```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from paper_trading.domain.enums import OrderSide

CENT = Decimal("0.01")


@dataclass(frozen=True)
class FeeConfig:
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5.00")
    stamp_duty_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")


@dataclass(frozen=True)
class FeeBreakdown:
    commission: Decimal
    stamp_duty: Decimal
    transfer_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.stamp_duty + self.transfer_fee


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_a_share_fees(side: OrderSide, amount: Decimal, config: FeeConfig | None = None) -> FeeBreakdown:
    fee_config = config or FeeConfig()
    commission = max(quantize_money(amount * fee_config.commission_rate), fee_config.min_commission)
    stamp_duty = quantize_money(amount * fee_config.stamp_duty_rate) if side == OrderSide.SELL else Decimal("0.00")
    transfer_fee = quantize_money(amount * fee_config.transfer_fee_rate)
    return FeeBreakdown(commission=commission, stamp_duty=stamp_duty, transfer_fee=transfer_fee)
```

Create `paper_trading/domain/rules.py`:

```python
from decimal import Decimal

from paper_trading.domain.errors import PaperTradingError


def ensure_lot_size(quantity: int) -> None:
    if quantity <= 0 or quantity % 100 != 0:
        raise PaperTradingError("INVALID_LOT_SIZE", "A-share orders must use positive 100-share lots", {"quantity": quantity})


def ensure_price_in_daily_range(price: Decimal, low: Decimal, high: Decimal) -> None:
    if price < low or price > high:
        raise PaperTradingError("PRICE_OUT_OF_RANGE", "Limit price is outside the daily trading range", {"price": str(price), "low": str(low), "high": str(high)})


def ensure_sufficient_cash(available: Decimal, required: Decimal) -> None:
    if available < required:
        raise PaperTradingError("INSUFFICIENT_CASH", "Insufficient available cash for the order", {"available": str(available), "required": str(required)})


def ensure_sufficient_position(available: int, required: int) -> None:
    if available < required:
        raise PaperTradingError("INSUFFICIENT_POSITION", "Insufficient sellable position for the order", {"available": available, "required": required})
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run pytest test/paper_trading/domain/test_fees.py test/paper_trading/domain/test_rules.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add paper_trading/domain test/paper_trading/domain
git commit -m "feat: add paper trading domain rules"
```

## Task 3: SQLAlchemy Models And DB Export Coverage

**Files:**
- Create: `paper_trading/storage/models.py`
- Modify: `storage/model/__init__.py`
- Modify: `tools/db_common.sh`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/tools/test_db_common.py`

- [ ] **Step 1: Write model schema test**

Create `test/paper_trading/storage/test_models.py`:

```python
from sqlalchemy import create_engine, inspect

from paper_trading.storage.models import tb_name_paper_accounts, tb_name_paper_orders, tb_name_paper_trades
from storage.model.base import Base


def test_paper_trading_tables_are_registered(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert tb_name_paper_accounts in inspector.get_table_names()
    assert tb_name_paper_orders in inspector.get_table_names()
    assert tb_name_paper_trades in inspector.get_table_names()

    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {"id", "account_id", "symbol", "side", "quantity", "limit_price", "status", "trade_date"} <= order_columns
    engine.dispose()
```

- [ ] **Step 2: Run model test to verify it fails**

```bash
uv run pytest test/paper_trading/storage/test_models.py -q
```

Expected: FAIL because `paper_trading.storage.models` does not exist.

- [ ] **Step 3: Implement SQLAlchemy models**

Create `paper_trading/storage/models.py` with models for all MVP tables. Use `storage.model.base.Base` and define table name constants:

```python
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.sql import func

from storage.model.base import Base

tb_name_paper_accounts = "paper_accounts"
tb_name_paper_cash_ledger = "paper_cash_ledger"
tb_name_paper_positions = "paper_positions"
tb_name_paper_position_lots = "paper_position_lots"
tb_name_paper_orders = "paper_orders"
tb_name_paper_trades = "paper_trades"
tb_name_paper_account_snapshots = "paper_account_snapshots"
tb_name_paper_matching_runs = "paper_matching_runs"


class PaperAccount(Base):
    __tablename__ = tb_name_paper_accounts
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    initial_cash = Column(Numeric(20, 4), nullable=False)
    status = Column(String(20), nullable=False, server_default="active")
    base_currency = Column(String(10), nullable=False, server_default="CNY")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperCashLedger(Base):
    __tablename__ = tb_name_paper_cash_ledger
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    amount = Column(Numeric(20, 4), nullable=False)
    order_id = Column(Integer, nullable=True, index=True)
    trade_id = Column(Integer, nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    note = Column(Text, nullable=True)


class PaperPosition(Base):
    __tablename__ = tb_name_paper_positions
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_paper_positions_account_symbol"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    total_quantity = Column(Integer, nullable=False, server_default=text("0"))
    frozen_quantity = Column(Integer, nullable=False, server_default=text("0"))
    cost_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl = Column(Numeric(20, 4), nullable=False, server_default=text("0"))


class PaperPositionLot(Base):
    __tablename__ = tb_name_paper_position_lots
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    buy_trade_date = Column(Date, nullable=False, index=True)
    original_quantity = Column(Integer, nullable=False)
    remaining_quantity = Column(Integer, nullable=False)
    cost_price = Column(Numeric(20, 4), nullable=False)


class PaperOrder(Base):
    __tablename__ = tb_name_paper_orders
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Numeric(20, 4), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    filled_quantity = Column(Integer, nullable=False, server_default=text("0"))
    frozen_cash = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    frozen_quantity = Column(Integer, nullable=False, server_default=text("0"))
    idempotency_key = Column(String(100), nullable=True, unique=True)
    rejection_code = Column(String(50), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperTrade(Base):
    __tablename__ = tb_name_paper_trades
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(20, 4), nullable=False)
    amount = Column(Numeric(20, 4), nullable=False)
    fees = Column(Numeric(20, 4), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    trade_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperAccountSnapshot(Base):
    __tablename__ = tb_name_paper_account_snapshots
    __table_args__ = (UniqueConstraint("account_id", "trade_date", name="uq_paper_account_snapshots_account_date"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    cash_available = Column(Numeric(20, 4), nullable=False)
    cash_frozen = Column(Numeric(20, 4), nullable=False)
    market_value = Column(Numeric(20, 4), nullable=False)
    total_assets = Column(Numeric(20, 4), nullable=False)
    realized_pnl = Column(Numeric(20, 4), nullable=False)
    unrealized_pnl = Column(Numeric(20, 4), nullable=False)
    position_count = Column(Integer, nullable=False)
    order_count = Column(Integer, nullable=False)
    trade_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperMatchingRun(Base):
    __tablename__ = tb_name_paper_matching_runs
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)
    account_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False)
    processed_count = Column(Integer, nullable=False, server_default=text("0"))
    filled_count = Column(Integer, nullable=False, server_default=text("0"))
    skipped_count = Column(Integer, nullable=False, server_default=text("0"))
    rejected_count = Column(Integer, nullable=False, server_default=text("0"))
    failed_count = Column(Integer, nullable=False, server_default=text("0"))
    error_details = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Export models from existing model package**

Modify `storage/model/__init__.py` to import all `Paper*` classes and `tb_name_paper_*` constants from `paper_trading.storage.models`, and add them to `__all__`.

- [ ] **Step 5: Add business tables to DB tools**

Modify `tools/db_common.sh` `BUSINESS_TABLES` to include:

```bash
  paper_accounts
  paper_cash_ledger
  paper_positions
  paper_position_lots
  paper_orders
  paper_trades
  paper_account_snapshots
  paper_matching_runs
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest test/paper_trading/storage/test_models.py test/tools/test_db_common.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add paper_trading/storage/models.py storage/model/__init__.py tools/db_common.sh test/paper_trading/storage/test_models.py test/tools/test_db_common.py
git commit -m "feat: add paper trading storage models"
```

## Task 4: Repository And Market Data Adapter

**Files:**
- Create: `paper_trading/storage/market_data.py`
- Create: `paper_trading/storage/repository.py`
- Test: `test/paper_trading/storage/test_repository.py`

- [ ] **Step 1: Write repository test**

Create `test/paper_trading/storage/test_repository.py`:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_create_account_deposits_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.id is not None
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_create_order_persists_accepted_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    order = repo.create_order(account_id=account.id, symbol="000001.SZ", side=OrderSide.BUY, quantity=100, limit_price=Decimal("10.00"), trade_date=date(2026, 6, 16), status=OrderStatus.ACCEPTED, frozen_cash=Decimal("1005.00"), frozen_quantity=0, idempotency_key="k1")
    session.commit()

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()
```

- [ ] **Step 2: Run repository test to verify it fails**

```bash
uv run pytest test/paper_trading/storage/test_repository.py -q
```

Expected: FAIL because repository is not implemented.

- [ ] **Step 3: Implement market data protocol**

Create `paper_trading/storage/market_data.py`:

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    up_limit: Decimal | None = None
    down_limit: Decimal | None = None
    suspended: bool = False


class MarketDataProvider(Protocol):
    def is_trade_date(self, trade_date: date) -> bool: ...
    def next_trade_date(self, trade_date: date) -> date: ...
    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar: ...


class InMemoryMarketDataProvider:
    def __init__(self, bars: dict[tuple[str, date], DailyBar], trade_dates: list[date]):
        self.bars = bars
        self.trade_dates = sorted(trade_dates)

    def is_trade_date(self, trade_date: date) -> bool:
        return trade_date in self.trade_dates

    def next_trade_date(self, trade_date: date) -> date:
        for candidate in self.trade_dates:
            if candidate > trade_date:
                return candidate
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        return self.bars[(symbol, trade_date)]
```

- [ ] **Step 4: Implement repository methods used by tests**

Create `paper_trading/storage/repository.py` with methods from the tests plus `add_cash_event`, `get_orders_for_matching`, `update_order_status`, `get_positions`, and `save_snapshot`. Keep methods small and commit via SQLAlchemy session owned by the caller.

- [ ] **Step 5: Run repository tests**

```bash
uv run pytest test/paper_trading/storage/test_repository.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add paper_trading/storage/market_data.py paper_trading/storage/repository.py test/paper_trading/storage/test_repository.py
git commit -m "feat: add paper trading repository"
```

## Task 5: Account And Order Services

**Files:**
- Create: `paper_trading/services/account_service.py`
- Create: `paper_trading/services/order_service.py`
- Test: `test/paper_trading/services/test_account_service.py`
- Test: `test/paper_trading/services/test_order_service.py`

- [ ] **Step 1: Write account service test**

Create `test/paper_trading/services/test_account_service.py` to verify `AccountService.create_account("demo", Decimal("100000"))` returns an active account and initial cash is available.

- [ ] **Step 2: Write order service tests**

Create `test/paper_trading/services/test_order_service.py` with tests for buy freeze, invalid lot rejection, insufficient cash rejection, and sell freeze using pre-created positions/lots.

- [ ] **Step 3: Run service tests to verify they fail**

```bash
uv run pytest test/paper_trading/services/test_account_service.py test/paper_trading/services/test_order_service.py -q
```

Expected: FAIL because services do not exist.

- [ ] **Step 4: Implement AccountService**

`AccountService` should accept `PaperTradingRepository`, call `repo.create_account`, and expose `get_account` plus `list_accounts` wrappers.

- [ ] **Step 5: Implement OrderService**

`OrderService.place_order` should validate lot size and trade date, calculate estimated buy fees, freeze cash or position, create `accepted` orders, and create `rejected` orders for domain rule failures. `OrderService.cancel_order` should only cancel `accepted` orders and release frozen assets.

- [ ] **Step 6: Run service tests**

```bash
uv run pytest test/paper_trading/services/test_account_service.py test/paper_trading/services/test_order_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add paper_trading/services test/paper_trading/services
git commit -m "feat: add paper trading account and order services"
```

## Task 6: Matching And Snapshot Services

**Files:**
- Create: `paper_trading/services/matching_service.py`
- Create: `paper_trading/services/snapshot_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`

- [ ] **Step 1: Write matching service tests**

Create tests that place accepted buy and sell orders, then run matching for a trade date. Verify buy fills at limit price, cash is reduced by amount plus fees, lot is created, sell consumes eligible lots FIFO, and non-touched limit orders remain accepted.

- [ ] **Step 2: Write snapshot service test**

Create a test with cash and one position. Run snapshot generation using an in-memory daily close and assert cash, market value, total assets, position count, order count, and trade count.

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q
```

Expected: FAIL because matching and snapshot services do not exist.

- [ ] **Step 4: Implement SnapshotService**

Implement `generate_snapshot(account_id: int, trade_date: date)` to read cash, positions, close prices, orders, and trades through the repository and upsert one snapshot per account/date.

- [ ] **Step 5: Implement MatchingService**

Implement `run(trade_date: date, account_id: int | None = None)` to create a matching run, process accepted orders one by one, reject suspended/hard-rule failures, skip not-touched orders, fill tradable orders at limit price, settle cash/positions/lots/trades, generate snapshots, and update matching run counters.

- [ ] **Step 6: Run tests**

```bash
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add paper_trading/services test/paper_trading/services
git commit -m "feat: add paper trading matching and snapshots"
```

## Task 7: FastAPI Schemas, Dependencies, And Routers

**Files:**
- Create: `paper_trading/schemas/accounts.py`
- Create: `paper_trading/schemas/orders.py`
- Create: `paper_trading/schemas/matching.py`
- Create: `paper_trading/schemas/snapshots.py`
- Create: `paper_trading/api/deps.py`
- Create: `paper_trading/api/app.py`
- Create: `paper_trading/api/routers/accounts.py`
- Create: `paper_trading/api/routers/orders.py`
- Create: `paper_trading/api/routers/matching.py`
- Create: `paper_trading/api/routers/snapshots.py`
- Test: `test/paper_trading/api/test_api_auth.py`
- Test: `test/paper_trading/api/test_orders_api.py`

- [ ] **Step 1: Write API auth test**

Create a `TestClient` test that sets `PAPER_TRADING_API_TOKEN=secret`, calls `GET /paper/accounts` without a token and expects 401, then with `Authorization: Bearer secret` and expects a non-401 response.

- [ ] **Step 2: Write order API test**

Create a `TestClient` test that posts a valid order JSON to `/paper/accounts/{account_id}/orders` and asserts the response includes `status: accepted`, `symbol`, `quantity`, and `limit_price`.

- [ ] **Step 3: Run API tests to verify they fail**

```bash
uv run pytest test/paper_trading/api/test_api_auth.py test/paper_trading/api/test_orders_api.py -q
```

Expected: FAIL because FastAPI app is not implemented.

- [ ] **Step 4: Implement schemas**

Use Pydantic models for create account, account response, create order, order response, matching run request/response, snapshot response, position response, trade response, and cash ledger response. Use `Decimal` fields and set `from_attributes=True` on response models.

- [ ] **Step 5: Implement API dependencies**

`paper_trading/api/deps.py` should validate `Authorization: Bearer <token>` against `PAPER_TRADING_API_TOKEN`. It should also provide a SQLAlchemy session dependency using the existing storage config conventions.

- [ ] **Step 6: Implement routers and app factory**

Expose the API surface from the spec under `/paper`. Keep route functions thin: parse request, call service, return schema. Translate `PaperTradingError` into structured HTTP responses.

- [ ] **Step 7: Run API tests**

```bash
uv run pytest test/paper_trading/api/test_api_auth.py test/paper_trading/api/test_orders_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add paper_trading/schemas paper_trading/api test/paper_trading/api
git commit -m "feat: add paper trading FastAPI routes"
```

## Task 8: Final Integration Checks And Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-06-16-paper-trading-backend-design.md` if implementation decisions differ.
- Create or modify: `docs/paper_trading.md` with operator-facing usage examples.

- [ ] **Step 1: Write user-facing docs**

Create `docs/paper_trading.md` with startup instructions, required env vars, example account creation, example order creation, matching run request, and snapshot query.

- [ ] **Step 2: Run focused test suite**

```bash
uv run pytest test/paper_trading -q
```

Expected: PASS.

- [ ] **Step 3: Run repository checks**

```bash
uv run pre-commit run --all-files
uv run pytest test
```

Expected: PASS for both commands.

- [ ] **Step 4: Commit docs and final polish**

```bash
git add docs/paper_trading.md docs/superpowers/specs/2026-06-16-paper-trading-backend-design.md
git commit -m "docs: add paper trading backend usage"
```

## Self-Review

- Spec coverage: modules, tables, multi-account token auth, A-share limit orders, daily async matching, fees, T+1 lots, snapshots, API surface, DB tools, and tests are all covered by tasks.
- Placeholder scan: no task uses `TBD`, `TODO`, or unspecified implementation language. Tasks 5-8 intentionally define behavior and files while leaving code details to the executor because they depend on earlier repository interfaces.
- Type consistency: enum names, table names, and service names match across tasks.
