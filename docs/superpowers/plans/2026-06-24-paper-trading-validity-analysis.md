# Paper Trading Validity Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class paper-trading validity analysis that preserves original orders, summarizes validity on orders, and stores detailed evidence per order.

**Architecture:** Add focused validity rules in the domain layer, persistence support in the SQLAlchemy model/repository, and a `TradeValidityService` called after order creation. API responses expose summary fields, and a new endpoint returns detailed evidence. Default same-day matching remains unchanged.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy ORM, SQLite-backed unit tests, Ruff, pytest, `uv run` for all Python commands.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3` for project tasks.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA.
- Storage tables: when adding or removing tables, update `tools/db_common.sh`.
- Preserve paper-trading order lifecycle semantics; validity status is separate from `status`.
- Default matching remains same-day and does not block on validity status.
- Initial limit-touch detection uses daily bars; minute and tick granularity are not implemented in this plan.
- Missing market data must preserve the original order and mark validity as `unchecked`.

---

## File Structure

- Modify `paper_trading/domain/enums.py`: add `TradeValidityStatus`.
- Modify `paper_trading/domain/rules.py`: add pure helpers for daily price range and daily limit-touch classification.
- Modify `storage/model/paper_trading.py`: add order summary columns and `PaperTradeValidityCheck` table.
- Modify `paper_trading/storage/models.py`: re-export the new model/table name.
- Modify `paper_trading/storage/repository.py`: add methods to update order validity and create/list validity checks.
- Create `paper_trading/services/trade_validity_service.py`: orchestrate market data lookup and analysis persistence.
- Modify `paper_trading/services/order_service.py`: call `TradeValidityService` after order persistence.
- Modify `paper_trading/schemas/orders.py`: expose order validity summary and detail response schema.
- Modify `paper_trading/api/routers/orders.py`: add validity detail endpoint.
- Modify `tools/db_common.sh`: include new table in export/import table list.
- Modify `docs/paper_trading.md`: document new positioning, statuses, and same-day matching semantics.
- Add/modify tests under `test/paper_trading/` for models, rules, repository, services, API, and matching regression.

---

### Task 1: Persistence Model And Repository

**Files:**
- Modify: `storage/model/paper_trading.py:1-146`
- Modify: `paper_trading/storage/models.py:1-37`
- Modify: `paper_trading/storage/repository.py:1-346`
- Modify: `tools/db_common.sh:35-43`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces: `PaperTradeValidityCheck` SQLAlchemy model.
- Produces: `tb_name_paper_trade_validity_checks = "paper_trade_validity_checks"`.
- Produces: `PaperTradingRepository.update_order_validity(order, status, reason) -> PaperOrder`.
- Produces: `PaperTradingRepository.create_trade_validity_check(**values) -> PaperTradeValidityCheck`.
- Produces: `PaperTradingRepository.list_trade_validity_checks(order_id: int) -> list[PaperTradeValidityCheck]`.

- [ ] **Step 1: Write failing model test**

Add assertions to `test/paper_trading/storage/test_models.py`:

```python
from paper_trading.storage.models import tb_name_paper_trade_validity_checks


def test_paper_trading_tables_are_registered(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert tb_name_paper_accounts in inspector.get_table_names()
    assert tb_name_paper_orders in inspector.get_table_names()
    assert tb_name_paper_trades in inspector.get_table_names()
    assert tb_name_paper_trade_validity_checks in inspector.get_table_names()

    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {"validity_status", "validity_reason", "validity_checked_at"} <= order_columns

    check_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trade_validity_checks)}
    assert {
        "id",
        "order_id",
        "account_id",
        "symbol",
        "trade_date",
        "side",
        "input_price",
        "daily_low",
        "daily_high",
        "limit_up_price",
        "limit_down_price",
        "touched_limit_up",
        "touched_limit_down",
        "price_in_range",
        "status",
        "reason_code",
        "reason_detail",
        "data_granularity",
        "created_at",
    } <= check_columns
```

- [ ] **Step 2: Run model test and confirm failure**

Run: `uv run pytest test/paper_trading/storage/test_models.py -v`

Expected: FAIL because `tb_name_paper_trade_validity_checks` or new columns do not exist.

- [ ] **Step 3: Add SQLAlchemy fields and table**

In `storage/model/paper_trading.py`, import `Boolean`, define `tb_name_paper_trade_validity_checks`, add validity summary columns to `PaperOrder`, and add:

```python
class PaperTradeValidityCheck(Base):
    __tablename__ = tb_name_paper_trade_validity_checks

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    side = Column(String(10), nullable=False)
    input_price = Column(Numeric(20, 4), nullable=False)
    daily_low = Column(Numeric(20, 4), nullable=True)
    daily_high = Column(Numeric(20, 4), nullable=True)
    limit_up_price = Column(Numeric(20, 4), nullable=True)
    limit_down_price = Column(Numeric(20, 4), nullable=True)
    touched_limit_up = Column(Boolean, nullable=True)
    touched_limit_down = Column(Boolean, nullable=True)
    price_in_range = Column(Boolean, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    reason_code = Column(String(50), nullable=False)
    reason_detail = Column(Text, nullable=True)
    data_granularity = Column(String(20), nullable=False, server_default="daily")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

Add to `PaperOrder`:

```python
validity_status = Column(String(20), nullable=True, index=True)
validity_reason = Column(String(50), nullable=True)
validity_checked_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Re-export model and table name**

Update `paper_trading/storage/models.py` imports and `__all__` to include `PaperTradeValidityCheck` and `tb_name_paper_trade_validity_checks`.

- [ ] **Step 5: Update export/import table list**

Insert `paper_trade_validity_checks` in `tools/db_common.sh` immediately after `paper_orders` so order-adjacent data exports together.

- [ ] **Step 6: Write failing repository test**

Add to `test/paper_trading/storage/test_repository.py`:

```python
def test_order_validity_summary_and_detail_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.ACCEPTED)

    repo.update_order_validity(order, "valid", "VALID")
    check = repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=Decimal("9.00"),
        daily_high=Decimal("10.50"),
        limit_up_price=Decimal("11.00"),
        limit_down_price=Decimal("9.00"),
        touched_limit_up=False,
        touched_limit_down=True,
        price_in_range=True,
        status="valid",
        reason_code="VALID",
        reason_detail="Price is inside daily range",
        data_granularity="daily",
    )
    session.commit()

    saved = repo.get_order(order.id)
    assert saved.validity_status == "valid"
    assert saved.validity_reason == "VALID"
    assert saved.validity_checked_at is not None
    assert repo.list_trade_validity_checks(order.id)[0].id == check.id
    engine.dispose()
```

- [ ] **Step 7: Run repository test and confirm failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py::test_order_validity_summary_and_detail_are_persisted -v`

Expected: FAIL because repository methods do not exist.

- [ ] **Step 8: Implement repository methods**

In `paper_trading/storage/repository.py`, import `PaperTradeValidityCheck` and add:

```python
def update_order_validity(self, order: PaperOrder, status: str, reason: str) -> PaperOrder:
    order.validity_status = status
    order.validity_reason = reason
    order.validity_checked_at = datetime.now(timezone.utc)
    order.updated_at = datetime.now(timezone.utc)
    self.session.flush()
    return order

def create_trade_validity_check(self, **values: Any) -> PaperTradeValidityCheck:
    check = PaperTradeValidityCheck(**values)
    self.session.add(check)
    self.session.flush()
    return check

def list_trade_validity_checks(self, order_id: int) -> list[PaperTradeValidityCheck]:
    return list(
        self.session.query(PaperTradeValidityCheck)
        .filter(PaperTradeValidityCheck.order_id == order_id)
        .order_by(PaperTradeValidityCheck.id.asc())
        .all()
    )
```

- [ ] **Step 9: Run storage tests**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py -v`

Expected: PASS.

---

### Task 2: Domain Validity Rules

**Files:**
- Modify: `paper_trading/domain/enums.py:1-34`
- Modify: `paper_trading/domain/rules.py:1-39`
- Test: `test/paper_trading/domain/test_rules.py`

**Interfaces:**
- Produces: `TradeValidityStatus` enum with `VALID`, `SUSPICIOUS`, `INVALID`, `UNCHECKED`.
- Produces: `class TradeValidityResult` dataclass.
- Produces: `evaluate_daily_trade_validity(side, price, low, high, limit_up, limit_down) -> TradeValidityResult`.

- [ ] **Step 1: Write failing rule tests**

Add tests to `test/paper_trading/domain/test_rules.py`:

```python
from paper_trading.domain.enums import OrderSide, TradeValidityStatus
from paper_trading.domain.rules import evaluate_daily_trade_validity


def test_daily_validity_rejects_price_below_low():
    result = evaluate_daily_trade_validity(OrderSide.BUY, Decimal("8.99"), Decimal("9.00"), Decimal("10.50"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "PRICE_OUT_OF_DAILY_RANGE"
    assert result.price_in_range is False


def test_daily_validity_marks_buy_limit_up_touch_suspicious():
    result = evaluate_daily_trade_validity(OrderSide.BUY, Decimal("10.50"), Decimal("9.00"), Decimal("11.00"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.SUSPICIOUS
    assert result.reason_code == "BUY_ON_LIMIT_UP_TOUCH"
    assert result.touched_limit_up is True


def test_daily_validity_rejects_buy_at_touched_limit_up():
    result = evaluate_daily_trade_validity(OrderSide.BUY, Decimal("11.00"), Decimal("9.00"), Decimal("11.00"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "BUY_AT_LIMIT_UP_TOUCH"


def test_daily_validity_marks_sell_limit_down_touch_suspicious():
    result = evaluate_daily_trade_validity(OrderSide.SELL, Decimal("9.50"), Decimal("9.00"), Decimal("10.50"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.SUSPICIOUS
    assert result.reason_code == "SELL_ON_LIMIT_DOWN_TOUCH"
    assert result.touched_limit_down is True


def test_daily_validity_rejects_sell_at_touched_limit_down():
    result = evaluate_daily_trade_validity(OrderSide.SELL, Decimal("9.00"), Decimal("9.00"), Decimal("10.50"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "SELL_AT_LIMIT_DOWN_TOUCH"


def test_daily_validity_accepts_normal_price():
    result = evaluate_daily_trade_validity(OrderSide.BUY, Decimal("10.00"), Decimal("9.00"), Decimal("10.50"), Decimal("11.00"), Decimal("9.00"))
    assert result.status == TradeValidityStatus.VALID
    assert result.reason_code == "VALID"
```

- [ ] **Step 2: Run rule tests and confirm failure**

Run: `uv run pytest test/paper_trading/domain/test_rules.py -v`

Expected: FAIL because enum/helper do not exist.

- [ ] **Step 3: Add enum and dataclass helper**

Add to `paper_trading/domain/enums.py`:

```python
class TradeValidityStatus(StrEnum):
    VALID = "valid"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"
    UNCHECKED = "unchecked"
```

Add to `paper_trading/domain/rules.py`:

```python
from dataclasses import dataclass

from paper_trading.domain.enums import OrderSide, TradeValidityStatus


@dataclass(frozen=True)
class TradeValidityResult:
    status: TradeValidityStatus
    reason_code: str
    reason_detail: str
    price_in_range: bool
    touched_limit_up: bool | None
    touched_limit_down: bool | None
```

- [ ] **Step 4: Implement daily validity helper**

Add to `paper_trading/domain/rules.py`:

```python
def evaluate_daily_trade_validity(
    side: OrderSide,
    price: Decimal,
    low: Decimal,
    high: Decimal,
    limit_up: Decimal | None,
    limit_down: Decimal | None,
) -> TradeValidityResult:
    price_in_range = low <= price <= high
    if not price_in_range:
        return TradeValidityResult(
            TradeValidityStatus.INVALID,
            "PRICE_OUT_OF_DAILY_RANGE",
            "Input price is outside the daily low/high range",
            False,
            None if limit_up is None else high >= limit_up,
            None if limit_down is None else low <= limit_down,
        )

    touched_limit_up = None if limit_up is None else high >= limit_up
    touched_limit_down = None if limit_down is None else low <= limit_down

    if side == OrderSide.BUY and touched_limit_up:
        if price >= limit_up:
            return TradeValidityResult(TradeValidityStatus.INVALID, "BUY_AT_LIMIT_UP_TOUCH", "Buy price is at the touched limit-up price", True, touched_limit_up, touched_limit_down)
        return TradeValidityResult(TradeValidityStatus.SUSPICIOUS, "BUY_ON_LIMIT_UP_TOUCH", "The symbol touched limit-up on this trade date", True, touched_limit_up, touched_limit_down)

    if side == OrderSide.SELL and touched_limit_down:
        if price <= limit_down:
            return TradeValidityResult(TradeValidityStatus.INVALID, "SELL_AT_LIMIT_DOWN_TOUCH", "Sell price is at the touched limit-down price", True, touched_limit_up, touched_limit_down)
        return TradeValidityResult(TradeValidityStatus.SUSPICIOUS, "SELL_ON_LIMIT_DOWN_TOUCH", "The symbol touched limit-down on this trade date", True, touched_limit_up, touched_limit_down)

    return TradeValidityResult(TradeValidityStatus.VALID, "VALID", "Price is inside daily range", True, touched_limit_up, touched_limit_down)
```

- [ ] **Step 5: Run domain tests**

Run: `uv run pytest test/paper_trading/domain/test_rules.py -v`

Expected: PASS.

---

### Task 3: Validity Service Integration

**Files:**
- Create: `paper_trading/services/trade_validity_service.py`
- Modify: `paper_trading/services/order_service.py:1-138`
- Test: `test/paper_trading/services/test_trade_validity_service.py`
- Test: `test/paper_trading/services/test_order_service.py`

**Interfaces:**
- Consumes: `evaluate_daily_trade_validity(side: OrderSide, price: Decimal, low: Decimal, high: Decimal, limit_up: Decimal | None, limit_down: Decimal | None) -> TradeValidityResult` from Task 2.
- Consumes: repository methods from Task 1.
- Produces: `TradeValidityService.analyze_order(order: PaperOrder) -> PaperTradeValidityCheck`.
- Produces: `OrderService(repo: PaperTradingRepository, market_data: MarketDataProvider, validity_service: TradeValidityService | None = None)` optional dependency.

- [ ] **Step 1: Write failing service tests**

Create `test/paper_trading/services/test_trade_validity_service.py` with a local market-data fake. Include:

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


class StaticMarketData:
    def __init__(self, bar: DailyBar | None):
        self.bar = bar

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        if self.bar is None:
            raise KeyError(f"No daily bar for {symbol} on {trade_date.isoformat()}")
        return self.bar


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'validity.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_analyze_order_persists_validity_detail_and_summary(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.ACCEPTED)
    service = TradeValidityService(
        repo,
        StaticMarketData(
            DailyBar(
                symbol="000001.SZ",
                trade_date=date(2026, 6, 16),
                open=Decimal("9.50"),
                high=Decimal("10.50"),
                low=Decimal("9.00"),
                close=Decimal("10.00"),
                up_limit=Decimal("11.00"),
                down_limit=Decimal("8.00"),
            )
        ),
    )

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "valid"
    assert repo.get_order(order.id).validity_status == "valid"
    assert repo.list_trade_validity_checks(order.id)[0].reason_code == "VALID"
    engine.dispose()


def test_analyze_order_marks_missing_market_data_unchecked(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.ACCEPTED)
    service = TradeValidityService(repo, StaticMarketData(None))

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "unchecked"
    assert check.reason_code == "MARKET_DATA_UNAVAILABLE"
    assert repo.get_order(order.id).validity_status == "unchecked"
    engine.dispose()
```

- [ ] **Step 2: Run service tests and confirm failure**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py -v`

Expected: FAIL because service file does not exist.

- [ ] **Step 3: Implement `TradeValidityService`**

Create `paper_trading/services/trade_validity_service.py`:

```python
from decimal import Decimal

from paper_trading.domain.enums import OrderSide, TradeValidityStatus
from paper_trading.domain.rules import evaluate_daily_trade_validity
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder, PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository


class TradeValidityService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def analyze_order(self, order: PaperOrder) -> PaperTradeValidityCheck:
        try:
            bar = self.market_data.get_daily_bar(order.symbol, order.trade_date)
            result = evaluate_daily_trade_validity(
                OrderSide(order.side),
                Decimal(order.limit_price),
                bar.low,
                bar.high,
                bar.up_limit,
                bar.down_limit,
            )
            values = {
                "daily_low": bar.low,
                "daily_high": bar.high,
                "limit_up_price": bar.up_limit,
                "limit_down_price": bar.down_limit,
                "touched_limit_up": result.touched_limit_up,
                "touched_limit_down": result.touched_limit_down,
                "price_in_range": result.price_in_range,
                "status": result.status.value,
                "reason_code": result.reason_code,
                "reason_detail": result.reason_detail,
            }
        except Exception as exc:
            values = {
                "daily_low": None,
                "daily_high": None,
                "limit_up_price": None,
                "limit_down_price": None,
                "touched_limit_up": None,
                "touched_limit_down": None,
                "price_in_range": None,
                "status": TradeValidityStatus.UNCHECKED.value,
                "reason_code": "MARKET_DATA_UNAVAILABLE",
                "reason_detail": str(exc),
            }

        check = self.repo.create_trade_validity_check(
            order_id=order.id,
            account_id=order.account_id,
            symbol=order.symbol,
            trade_date=order.trade_date,
            side=order.side,
            input_price=Decimal(order.limit_price),
            data_granularity="daily",
            **values,
        )
        self.repo.update_order_validity(order, check.status, check.reason_code)
        return check
```

- [ ] **Step 4: Wire order service without changing lifecycle**

Modify `OrderService.__init__` to create a default `TradeValidityService`. After each `repo.create_order` call in `place_order()`, `_accept_buy_order()`, and `_accept_sell_order()`, call `self.validity_service.analyze_order(order)` and return the analyzed order object.

- [ ] **Step 5: Add order service regression tests**

In `test/paper_trading/services/test_order_service.py`, add tests that place an order with missing market data and assert:

```python
assert order.status == OrderStatus.ACCEPTED.value
assert order.validity_status == "unchecked"
assert order.validity_reason == "MARKET_DATA_UNAVAILABLE"
```

Also add a daily-bar test where the order is accepted and validity is `valid`.

- [ ] **Step 6: Run service tests**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_order_service.py -v`

Expected: PASS.

---

### Task 4: API Schemas And Endpoint

**Files:**
- Modify: `paper_trading/schemas/orders.py:1-48`
- Modify: `paper_trading/api/routers/orders.py:1-62`
- Test: `test/paper_trading/api/test_orders_api.py`

**Interfaces:**
- Consumes: repository `list_trade_validity_checks(order_id)` from Task 1.
- Produces: `TradeValidityCheckResponse` Pydantic schema.
- Produces: `GET /paper/accounts/{account_id}/orders/{order_id}/validity-checks`.

- [ ] **Step 1: Write failing API tests**

Add to `test/paper_trading/api/test_orders_api.py`:

```python
def test_create_order_returns_validity_summary(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post("/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers)
    account_id = account_response.json()["id"]

    response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={"symbol": "000001.SZ", "side": "buy", "quantity": 100, "limit_price": "10.00", "trade_date": "2026-06-16"},
        headers=headers,
    )

    payload = response.json()
    assert "validity_status" in payload
    assert "validity_reason" in payload
    assert "validity_checked_at" in payload


def test_get_order_validity_checks_returns_evidence(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post("/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers)
    account_id = account_response.json()["id"]
    order_response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={"symbol": "000001.SZ", "side": "buy", "quantity": 100, "limit_price": "10.00", "trade_date": "2026-06-16"},
        headers=headers,
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/paper/accounts/{account_id}/orders/{order_id}/validity-checks", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["order_id"] == order_id
    assert payload[0]["data_granularity"] == "daily"
```

- [ ] **Step 2: Run API tests and confirm failure**

Run: `uv run pytest test/paper_trading/api/test_orders_api.py -v`

Expected: FAIL because response fields and endpoint do not exist.

- [ ] **Step 3: Extend schemas**

Add to `OrderResponse`:

```python
validity_status: str | None = None
validity_reason: str | None = None
validity_checked_at: datetime | None = None
```

Import `datetime` and add:

```python
class TradeValidityCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    account_id: int
    symbol: str
    trade_date: date
    side: str
    input_price: Decimal
    daily_low: Decimal | None = None
    daily_high: Decimal | None = None
    limit_up_price: Decimal | None = None
    limit_down_price: Decimal | None = None
    touched_limit_up: bool | None = None
    touched_limit_down: bool | None = None
    price_in_range: bool | None = None
    status: str
    reason_code: str
    reason_detail: str | None = None
    data_granularity: str
    created_at: datetime
```

- [ ] **Step 4: Add router endpoint**

In `paper_trading/api/routers/orders.py`, import `TradeValidityCheckResponse` and add:

```python
@router.get(
    "/accounts/{account_id}/orders/{order_id}/validity-checks",
    response_model=list[TradeValidityCheckResponse],
)
def list_order_validity_checks(account_id: int, order_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    order = repo.get_order(order_id)
    if order.account_id != account_id:
        return []
    return repo.list_trade_validity_checks(order_id)
```

- [ ] **Step 5: Run API tests**

Run: `uv run pytest test/paper_trading/api/test_orders_api.py -v`

Expected: PASS.

---

### Task 5: Matching Regression And Documentation

**Files:**
- Modify: `test/paper_trading/services/test_matching_service.py:1-103`
- Modify: `docs/paper_trading.md:1-115`

**Interfaces:**
- Consumes: order validity status from Tasks 1-4.
- Produces: documented semantics for same-day matching and validity analysis.

- [ ] **Step 1: Add matching regression test**

Add to `test/paper_trading/services/test_matching_service.py`:

```python
def test_default_matching_does_not_skip_invalid_validity_order(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    repo.update_order_validity(order, "invalid", "BUY_AT_LIMIT_UP_TOUCH")

    run = matching_service.run(trade_date)
    session.commit()

    assert run.filled_count == 1
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    engine.dispose()
```

- [ ] **Step 2: Run matching regression**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_default_matching_does_not_skip_invalid_validity_order -v`

Expected: PASS because default matching ignores validity status.

- [ ] **Step 3: Update documentation**

Update `docs/paper_trading.md` with a section after “Create Limit Order”:

```markdown
## Trade Validity Analysis

Paper trading records the original trading intent and analyzes whether the operation was valid for the specified `trade_date`. The order lifecycle status (`accepted`, `rejected`, `filled`, `cancelled`) remains separate from validity status.

Validity statuses:

- `valid`: available data supports the operation.
- `suspicious`: daily data indicates risk or uncertainty, such as a same-day limit touch.
- `invalid`: the operation is not valid for the specified trading day, such as a price outside the daily low/high range.
- `unchecked`: required market data was unavailable, so the original order is preserved without a completed analysis.

The first version uses daily bars for limit-up and limit-down detection. `trade_date` is the operation date, so default analysis and matching are same-day. A-share T+1 remains a sellable-position rule and does not shift matching to the next day.
```

- [ ] **Step 4: Run focused suite**

Run: `uv run pytest test/paper_trading/domain/test_rules.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_orders_api.py -v`

Expected: PASS.

---

### Task 6: Final Verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified implementation ready for review.

- [ ] **Step 1: Run formatter**

Run: `uv run ruff format paper_trading storage/model/paper_trading.py test/paper_trading`

Expected: command exits 0.

- [ ] **Step 2: Run linter**

Run: `uv run ruff check paper_trading storage/model/paper_trading.py test/paper_trading`

Expected: command exits 0.

- [ ] **Step 3: Run focused tests**

Run: `uv run pytest test/paper_trading -v`

Expected: PASS.

- [ ] **Step 4: Inspect diff**

Run: `git diff -- paper_trading storage/model/paper_trading.py test/paper_trading tools/db_common.sh docs/paper_trading.md`

Expected: diff only contains validity-analysis related changes.

---

## Self-Review Notes

- Spec coverage: data model, statuses, daily-range rules, limit-touch rules, missing-data handling, service integration, API exposure, matching semantics, tests, docs, and `tools/db_common.sh` are covered.
- Placeholder scan: checked for red-flag wording and replaced incomplete snippets with executable examples.
- Type consistency: status values are strings in persistence/API and `TradeValidityStatus` enum values in domain logic; repository boundaries convert to persisted strings.
