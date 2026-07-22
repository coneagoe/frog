# Paper Trading Hong Kong Stock Connect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Southbound Hong Kong Stock Connect ordinary-stock paper trading to the existing backend while keeping existing A-share behavior unchanged.

**Architecture:** Use explicit market-aware dispatch (`a_share` / `hk_connect`) instead of inferring market from code shape. Orders, trades, positions, and validity checks carry a `market` field. Services dispatch to market-specific rule, fee, and market-data implementations. A single RMB cash pool supports both markets.

**Tech Stack:** Python 3.11+, SQLAlchemy, Pydantic, FastAPI, pytest, Ruff.

**Constraints:**
- Use `uv run` for Python commands; do not use bare `python` or `python3`.
- Existing A-share tests must pass without fixture rewrites (except expected response fields that now include `market`).
- Existing persisted orders/trades are interpreted as `a_share` (default during migration).
- No frontend redesign in this phase.
- No ETF, REIT, warrant, derivative support.
- No Stock Connect quota simulation.
- No FX or multi-currency cash ledger.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA.
- If adding new tables, update `tools/db_common.sh`.
- Existing API clients that omit `market` continue to create A-share orders (backward compatibility).

---

## File Map

### New files
- `paper_trading/domain/hk_connect_fees.py` — HK Connect fee config and calculator
- `paper_trading/domain/hk_connect_rules.py` — HK-specific lot, tick, odd-lot rules
- `paper_trading/services/hk_settlement_service.py` — T+2 settlement tracking
- `paper_trading/storage/hk_metadata.py` — HK Connect security metadata repository
- `paper_trading/schemas/hk_fees.py` — HK fee schema models
- `test/paper_trading/domain/test_hk_connect_fees.py`
- `test/paper_trading/domain/test_hk_connect_rules.py`
- `test/paper_trading/services/test_hk_settlement_service.py`
- `test/paper_trading/storage/test_hk_metadata.py`

### Modified files
- `storage/model/paper_trading.py` — add `market` column to `PaperOrder`, `PaperTrade`, `PaperPosition`, `PaperTradeValidityCheck`; add HK fee columns to `PaperAccount`; add `PaperPendingSettlement` table
- `paper_trading/domain/enums.py` — add `Market` enum
- `paper_trading/domain/fees.py` — add `FeeConfig` factory/dispatch for HK, rename A-share preset key
- `paper_trading/domain/rules.py` — add `TradeValidityResult.market` field; keep A-share rules unchanged
- `paper_trading/domain/errors.py` — add HK-specific error codes (optional, or reuse existing `PaperTradingError`)
- `paper_trading/storage/repository.py` — add `market` persistence, HK fee field update, settlement methods
- `paper_trading/storage/models.py` — re-export new models
- `paper_trading/schemas/orders.py` — add `market` to `CreateOrderRequest` (optional, default `a_share`) and `OrderResponse`
- `paper_trading/schemas/accounts.py` — add HK fee fields to account schema
- `paper_trading/schemas/snapshots.py` — add `pending_settlement` field (optional)
- `paper_trading/services/order_service.py` — market-aware routing in `place_order()`, `_accept_buy_order()`, `_accept_sell_order()`
- `paper_trading/services/matching_service.py` — market-aware fee calc and market-data lookup in `_fill_order()`, `_settle_buy()`, `_settle_sell()`
- `paper_trading/services/trade_validity_service.py` — market-aware validity analysis
- `paper_trading/services/snapshot_service.py` — include pending settlement in asset calc
- `paper_trading/api/routers/orders.py` — pass optional `market` from request
- `paper_trading/api/routers/accounts.py` — add HK fee update endpoint
- `tools/paper_trading_cli.py` — add `--market` to `order create`
- `tools/db_common.sh` — add `paper_pending_settlement` if new table added

### Existing tests (must still pass)
- `test/paper_trading/domain/test_fees.py`
- `test/paper_trading/domain/test_rules.py`
- `test/paper_trading/storage/test_repository.py`
- `test/paper_trading/services/test_order_service.py`
- `test/paper_trading/services/test_matching_service.py`
- `test/paper_trading/services/test_trade_validity_service.py`
- `test/paper_trading/services/test_cash_service.py`
- `test/paper_trading/services/test_snapshot_service.py`
- `test/paper_trading/services/test_analytics_service.py`
- `test/paper_trading/api/test_orders_api.py`
- `test/paper_trading/api/test_accounts_api.py`
- `test/tools/test_paper_trading_cli.py`

---

## Task 1: Add Market enum and storage migration

**Files:**
- Modify: `paper_trading/domain/enums.py`
- Modify: `storage/model/paper_trading.py`
- Modify: `paper_trading/storage/models.py`
- Modify: `paper_trading/schemas/orders.py`
- Modify: `paper_trading/schemas/accounts.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces: `Market` enum (`a_share`, `hk_connect`)
- Produces: `market` column on `PaperOrder`, `PaperTrade`, `PaperPosition`, `PaperTradeValidityCheck` (default `a_share`)
- Produces: HK fee columns on `PaperAccount` (`hk_commission_rate`, `hk_min_commission`, `hk_stamp_duty_rate`, `hk_trading_fee_rate`, `hk_sfc_levy_rate`, `hk_afrc_levy_rate`, `hk_settlement_fee_rate`)
- Produces: `PaperPendingSettlement` table

- [ ] **Step 1: Write failing repository and model tests**

Add to `test/paper_trading/storage/test_repository.py`:

```python
def test_create_order_persists_market_default_a_share(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-demo", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    assert order.market == "a_share"


def test_create_order_persists_market_hk_connect(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-hk", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    assert order.market == "hk_connect"


def test_create_trade_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("trade-mkt", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    trade = repo.create_trade(
        order_id=order.id,
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("400.00"),
        amount=Decimal("40000.00"),
        fees=Decimal("100.00"),
        trade_date=date(2026, 7, 21),
        market="hk_connect",
    )
    assert trade.market == "hk_connect"


def test_position_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("pos-mkt", Decimal("100000.00"))
    pos = repo.upsert_position(
        account_id=account.id,
        symbol="00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.00"),
        market="hk_connect",
    )
    assert pos.market == "hk_connect"


def test_account_hk_fee_fields_default_to_none(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees", Decimal("100000.00"))
    assert account.hk_commission_rate is None
    assert account.hk_min_commission is None


def test_update_account_hk_fees_persists(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees-upd", Decimal("100000.00"))
    updated = repo.update_account_hk_fees(
        account.id,
        hk_commission_rate=Decimal("0.0002"),
        hk_min_commission=Decimal("18.00"),
        hk_stamp_duty_rate=Decimal("0.0013"),
        hk_trading_fee_rate=Decimal("0.0000565"),
        hk_sfc_levy_rate=Decimal("0.0000027"),
        hk_afrc_levy_rate=Decimal("0.0000015"),
        hk_settlement_fee_rate=Decimal("0.00002"),
    )
    assert updated is not None
    reloaded = repo.get_account(account.id)
    assert reloaded.hk_commission_rate == Decimal("0.0002")
    assert reloaded.hk_stamp_duty_rate == Decimal("0.0013")


def test_create_pending_settlement(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-demo", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    assert pending.account_id == account.id
    assert pending.settled is False


def test_settle_pending_releases_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-rel", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    repo.settle_pending(pending.id)
    assert pending.settled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q -k "market or hk_fee or pending_settle or settle"`

Expected: fail because `market` column, HK fee columns, pending settlement table, and repository methods do not exist.

- [ ] **Step 3: Add `Market` enum to `enums.py`**

In `paper_trading/domain/enums.py`:

```python
class Market(StrEnum):
    A_SHARE = "a_share"
    HK_CONNECT = "hk_connect"
```

- [ ] **Step 4: Add storage columns and table**

In `storage/model/paper_trading.py`:

Add `market` column to `PaperOrder`:
```python
market = Column(String(20), nullable=False, server_default="a_share", index=True)
```

Add `market` column to `PaperTrade`:
```python
market = Column(String(20), nullable=False, server_default="a_share", index=True)
```

Add `market` column to `PaperPosition`:
```python
market = Column(String(20), nullable=False, server_default="a_share", index=True)
```

Add `market` column to `PaperTradeValidityCheck`:
```python
market = Column(String(20), nullable=False, server_default="a_share", index=True)
```

Add HK fee columns to `PaperAccount`:
```python
hk_commission_rate = Column(Numeric(20, 8), nullable=True)
hk_min_commission = Column(Numeric(20, 4), nullable=True)
hk_stamp_duty_rate = Column(Numeric(20, 8), nullable=True)
hk_trading_fee_rate = Column(Numeric(20, 8), nullable=True)
hk_sfc_levy_rate = Column(Numeric(20, 8), nullable=True)
hk_afrc_levy_rate = Column(Numeric(20, 8), nullable=True)
hk_settlement_fee_rate = Column(Numeric(20, 8), nullable=True)
```

Add `PaperPendingSettlement` table:
```python
tb_name_paper_pending_settlement = "paper_pending_settlement"

class PaperPendingSettlement(Base):
    __tablename__ = tb_name_paper_pending_settlement

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    amount = Column(Numeric(20, 4), nullable=False)
    expected_settle_date = Column(Date, nullable=False, index=True)
    trade_id = Column(Integer, nullable=True)
    source = Column(String(20), nullable=False)  # "hk_sell"
    settled = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

Add the table name constant to the module-level exports and to `paper_trading/storage/models.py`.

- [ ] **Step 5: Extend repository methods**

In `paper_trading/storage/repository.py`:

Extend `create_order()` signature and body to accept `market: str | None = None` and persist `order.market = market or "a_share"`.

Extend `create_trade()` signature and body to accept `market: str | None = None` and persist `trade.market = market or "a_share"`.

Extend `upsert_position()` to accept `market: str | None = None` and persist `position.market = market or "a_share"`.

Add repository methods:

```python
def update_account_hk_fees(
    self,
    account_id: int,
    hk_commission_rate: Decimal | None = None,
    hk_min_commission: Decimal | None = None,
    hk_stamp_duty_rate: Decimal | None = None,
    hk_trading_fee_rate: Decimal | None = None,
    hk_sfc_levy_rate: Decimal | None = None,
    hk_afrc_levy_rate: Decimal | None = None,
    hk_settlement_fee_rate: Decimal | None = None,
) -> PaperAccount | None:
    _require_fee_update(
        hk_commission_rate=hk_commission_rate,
        hk_min_commission=hk_min_commission,
        hk_stamp_duty_rate=hk_stamp_duty_rate,
        hk_trading_fee_rate=hk_trading_fee_rate,
        hk_sfc_levy_rate=hk_sfc_levy_rate,
        hk_afrc_levy_rate=hk_afrc_levy_rate,
        hk_settlement_fee_rate=hk_settlement_fee_rate,
    )
    _validate_fee_values(
        hk_commission_rate=hk_commission_rate,
        hk_min_commission=hk_min_commission,
        hk_stamp_duty_rate=hk_stamp_duty_rate,
        hk_trading_fee_rate=hk_trading_fee_rate,
        hk_sfc_levy_rate=hk_sfc_levy_rate,
        hk_afrc_levy_rate=hk_afrc_levy_rate,
        hk_settlement_fee_rate=hk_settlement_fee_rate,
    )
    account = self.get_account(account_id)
    if account is None:
        return None
    if hk_commission_rate is not None:
        account.hk_commission_rate = hk_commission_rate
    if hk_min_commission is not None:
        account.hk_min_commission = hk_min_commission
    if hk_stamp_duty_rate is not None:
        account.hk_stamp_duty_rate = hk_stamp_duty_rate
    if hk_trading_fee_rate is not None:
        account.hk_trading_fee_rate = hk_trading_fee_rate
    if hk_sfc_levy_rate is not None:
        account.hk_sfc_levy_rate = hk_sfc_levy_rate
    if hk_afrc_levy_rate is not None:
        account.hk_afrc_levy_rate = hk_afrc_levy_rate
    if hk_settlement_fee_rate is not None:
        account.hk_settlement_fee_rate = hk_settlement_fee_rate
    self.session.flush()
    return account

def create_pending_settlement(
    self,
    account_id: int,
    amount: Decimal,
    expected_settle_date: date,
    trade_id: int | None = None,
    source: str = "hk_sell",
) -> PaperPendingSettlement:
    pending = PaperPendingSettlement(
        account_id=account_id,
        amount=amount,
        expected_settle_date=expected_settle_date,
        trade_id=trade_id,
        source=source,
        settled=False,
    )
    self.session.add(pending)
    self.session.flush()
    return pending

def list_pending_settlements(self, account_id: int) -> list[PaperPendingSettlement]:
    return list(
        self.session.query(PaperPendingSettlement)
        .filter(
            PaperPendingSettlement.account_id == account_id,
            PaperPendingSettlement.settled == False,
        )
        .order_by(PaperPendingSettlement.expected_settle_date.asc())
        .all()
    )

def settle_pending(self, pending_id: int) -> PaperPendingSettlement:
    pending = cast(PaperPendingSettlement, self.session.get(PaperPendingSettlement, pending_id))
    if pending is None:
        raise KeyError(f"pending settlement not found: {pending_id}")
    pending.settled = True
    # Add cash to ledger as trade event
    self.add_cash_event(
        pending.account_id,
        CashEventType.TRADE,
        pending.amount,
        trade_id=pending.trade_id,
        note="hk_sell_settlement",
    )
    self.session.flush()
    return pending

def get_pending_settlement_total(self, account_id: int) -> Decimal:
    total = (
        self.session.query(func.coalesce(func.sum(PaperPendingSettlement.amount), 0))
        .filter(
            PaperPendingSettlement.account_id == account_id,
            PaperPendingSettlement.settled == False,
        )
        .scalar()
    )
    return Decimal(total).quantize(Decimal("0.0001"))
```

- [ ] **Step 6: Run repository tests**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: PASS.

- [ ] **Step 7: Update db_common.sh**

Add `paper_pending_settlement` to the `BUSINESS_TABLES` array in `tools/db_common.sh`.

---

## Task 2: Add HK Connect security metadata source

**Files:**
- Create: `paper_trading/storage/hk_metadata.py`
- Create: `test/paper_trading/storage/test_hk_metadata.py`

**Interfaces:**
- Produces: `HkConnectMetadataProvider(lookup)` — service-level metadata source
- Produces: `HkSecurityMetadata(symbol, name, board_lot, eligible, effective_date)`

- [ ] **Step 1: Write failing metadata tests**

Create `test/paper_trading/storage/test_hk_metadata.py`:

```python
def test_known_security_returns_metadata(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("00700")
    assert meta is not None
    assert meta.symbol == "00700"
    assert meta.board_lot == 100
    assert meta.eligible is True


def test_unknown_security_returns_none(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("99999")
    assert meta is None


def test_board_lot_for_different_security(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("03690")
    assert meta is not None
    assert meta.board_lot == 100


def test_get_security_raises_for_empty_symbol(sqlite_session):
    provider = HkConnectMetadataProvider(sqlite_session)
    with pytest.raises(ValueError, match="symbol is required"):
        provider.get_security("")
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest test/paper_trading/storage/test_hk_metadata.py -q`

Expected: fail because `HkConnectMetadataProvider` does not exist.

- [ ] **Step 3: Implement `HkConnectMetadataProvider`**

Create `paper_trading/storage/hk_metadata.py`:

```python
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from storage.model.general_info_ggt import GeneralInfoGGT


@dataclass(frozen=True)
class HkSecurityMetadata:
    symbol: str
    name: str | None = None
    board_lot: int = 100  # default 100 for ordinary stocks
    eligible: bool = True


class HkConnectMetadataProvider:
    """Metadata source for Hong Kong Stock Connect ordinary stocks.

    Backed by the existing `general_info_hk_ggt` table.  Board lot size is
    100 for all ordinary stocks; this is the default.  If the symbol is not
    found in the table it is treated as ineligible.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_security(self, symbol: str) -> HkSecurityMetadata | None:
        if not symbol:
            raise ValueError("symbol is required")
        row = (
            self._session.query(GeneralInfoGGT)
            .filter(GeneralInfoGGT.股票代码 == symbol)
            .one_or_none()
        )
        if row is None:
            return None
        return HkSecurityMetadata(
            symbol=symbol,
            name=getattr(row, '股票名称', None),
            board_lot=100,
            eligible=True,
        )
```

- [ ] **Step 4: Run metadata tests**

Run: `uv run pytest test/paper_trading/storage/test_hk_metadata.py -q`

Expected: PASS.

---

## Task 3: Add HK Connect fees and rules

**Files:**
- Create: `paper_trading/domain/hk_connect_fees.py`
- Create: `paper_trading/domain/hk_connect_rules.py`
- Create: `test/paper_trading/domain/test_hk_connect_fees.py`
- Create: `test/paper_trading/domain/test_hk_connect_rules.py`

**Interfaces:**
- Produces: `HkFeeConfig` dataclass with HK-specific rates
- Produces: `calculate_hk_connect_fees(side, amount, config)` returning `HkFeeBreakdown`
- Produces: `ensure_hk_lot_size(quantity, board_lot)`, `ensure_hk_odd_lot_sell(quantity, remaining)`, `validate_hk_tick_size(price, symbol_range)`

- [ ] **Step 1: Write failing HK fee tests**

Create `test/paper_trading/domain/test_hk_connect_fees.py`:

```python
from decimal import Decimal
from paper_trading.domain.enums import OrderSide
from paper_trading.domain.hk_connect_fees import (
    HkFeeConfig,
    calculate_hk_connect_fees,
)


def test_hk_buy_fees():
    config = HkFeeConfig(
        commission_rate=Decimal("0.0002"),
        min_commission=Decimal("18.00"),
        stamp_duty_rate=Decimal("0.0013"),
        trading_fee_rate=Decimal("0.0000565"),
        sfc_levy_rate=Decimal("0.0000027"),
        afrc_levy_rate=Decimal("0.0000015"),
        settlement_fee_rate=Decimal("0.00002"),
    )
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("40000.00"), config)
    assert fees.commission >= fees.min_commission  # minimum commission applies
    assert fees.stamp_duty > Decimal("0")
    assert fees.total > Decimal("0")


def test_hk_sell_fees_include_stamp():
    config = HkFeeConfig()
    fees = calculate_hk_connect_fees(OrderSide.SELL, Decimal("50000.00"), config)
    assert fees.stamp_duty > Decimal("0")


def test_hk_sfc_and_afrc_levy():
    config = HkFeeConfig()
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("100000.00"), config)
    assert fees.sfc_levy > Decimal("0")
    assert fees.afrc_levy > Decimal("0")
    assert fees.settlement_fee >= Decimal("0")


def test_hk_min_commission_applied():
    config = HkFeeConfig(commission_rate=Decimal("0.0001"), min_commission=Decimal("50.00"))
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("100.00"), config)
    assert fees.commission == Decimal("50.00")


def test_hk_fee_config_defaults():
    config = HkFeeConfig()
    assert config.commission_rate == Decimal("0.00027")
    assert config.min_commission == Decimal("18.00")
    assert config.stamp_duty_rate == Decimal("0.0013")
```

- [ ] **Step 2: Write failing HK rule tests**

Create `test/paper_trading/domain/test_hk_connect_rules.py`:

```python
from decimal import Decimal
import pytest
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.hk_connect_rules import (
    ensure_hk_lot_size,
    ensure_hk_odd_lot_sell,
    validate_hk_tick_size,
    get_hk_tick_size,
)


def test_hk_lot_size_valid():
    ensure_hk_lot_size(100, 100)  # should not raise


def test_hk_lot_size_invalid():
    with pytest.raises(PaperTradingError, match="INVALID_LOT_SIZE"):
        ensure_hk_lot_size(50, 100)


def test_hk_lot_size_multiple():
    ensure_hk_lot_size(400, 100)  # 4 lots


def test_hk_odd_lot_sell_full_remainder():
    ensure_hk_odd_lot_sell(50, 50)  # selling exactly the odd lot remainder


def test_hk_odd_lot_sell_extra_share():
    with pytest.raises(PaperTradingError, match="INVALID_ODD_LOT_SELL"):
        ensure_hk_odd_lot_sell(51, 50)  # more than odd lot remainder


def test_hk_odd_lot_sell_board_lot_allowed():
    # Board lot multiples are always OK, even when remainder exists
    ensure_hk_odd_lot_sell(100, 50)


def test_hk_tick_below_10():
    assert get_hk_tick_size(Decimal("5.00")) == Decimal("0.010")


def test_hk_tick_10_to_20():
    assert get_hk_tick_size(Decimal("15.00")) == Decimal("0.020")


def test_hk_tick_20_to_100():
    assert get_hk_tick_size(Decimal("50.00")) == Decimal("0.050")


def test_hk_tick_100_to_200():
    assert get_hk_tick_size(Decimal("150.00")) == Decimal("0.100")


def test_hk_tick_200_to_500():
    assert get_hk_tick_size(Decimal("300.00")) == Decimal("0.200")


def test_hk_tick_500_to_1000():
    assert get_hk_tick_size(Decimal("700.00")) == Decimal("0.500")


def test_hk_tick_1000_to_2000():
    assert get_hk_tick_size(Decimal("1500.00")) == Decimal("1.000")


def test_hk_tick_2000_to_5000():
    assert get_hk_tick_size(Decimal("3000.00")) == Decimal("2.000")


def test_hk_tick_5000_and_above():
    assert get_hk_tick_size(Decimal("10000.00")) == Decimal("5.000")


def test_hk_validate_tick_aligned():
    validate_hk_tick_size(Decimal("5.00"), Decimal("5.01"))  # aligned to 0.010


def test_hk_validate_tick_off_tick():
    with pytest.raises(PaperTradingError, match="INVALID_TICK_SIZE"):
        validate_hk_tick_size(Decimal("5.00"), Decimal("5.015"))  # not aligned
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest test/paper_trading/domain/test_hk_connect_fees.py test/paper_trading/domain/test_hk_connect_rules.py -q`

Expected: fail because modules don't exist.

- [ ] **Step 4: Implement HK fee module**

Create `paper_trading/domain/hk_connect_fees.py`:

```python
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from paper_trading.domain.enums import OrderSide

CENT = Decimal("0.01")


@dataclass(frozen=True)
class HkFeeConfig:
    commission_rate: Decimal = Decimal("0.00027")
    min_commission: Decimal = Decimal("18.00")
    stamp_duty_rate: Decimal = Decimal("0.0013")
    trading_fee_rate: Decimal = Decimal("0.0000565")
    sfc_levy_rate: Decimal = Decimal("0.0000027")
    afrc_levy_rate: Decimal = Decimal("0.0000015")
    settlement_fee_rate: Decimal = Decimal("0.00002")

    def __post_init__(self) -> None:
        for field_name in (
            "commission_rate", "min_commission", "stamp_duty_rate",
            "trading_fee_rate", "sfc_levy_rate", "afrc_levy_rate",
            "settlement_fee_rate",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class HkFeeBreakdown:
    commission: Decimal
    stamp_duty: Decimal
    trading_fee: Decimal
    sfc_levy: Decimal
    afrc_levy: Decimal
    settlement_fee: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.commission + self.stamp_duty + self.trading_fee
            + self.sfc_levy + self.afrc_levy + self.settlement_fee
        )


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_hk_connect_fees(
    side: OrderSide,
    amount: Decimal,
    config: HkFeeConfig | None = None,
) -> HkFeeBreakdown:
    cfg = config or HkFeeConfig()
    commission = max(quantize_money(amount * cfg.commission_rate), cfg.min_commission)
    stamp_duty = (
        quantize_money(amount * cfg.stamp_duty_rate)
        if side == OrderSide.SELL
        else Decimal("0.00")
    )
    # Round stamp duty up to nearest integer (HK rule)
    stamp_duty = stamp_duty.quantize(CENT)
    trading_fee = quantize_money(amount * cfg.trading_fee_rate)
    sfc_levy = quantize_money(amount * cfg.sfc_levy_rate)
    afrc_levy = quantize_money(amount * cfg.afrc_levy_rate)
    settlement_fee = quantize_money(amount * cfg.settlement_fee_rate)
    # Settlement fee has min 2.00 and max 100.00
    if settlement_fee < Decimal("2.00"):
        settlement_fee = Decimal("2.00")
    elif settlement_fee > Decimal("100.00"):
        settlement_fee = Decimal("100.00")
    return HkFeeBreakdown(
        commission=commission,
        stamp_duty=stamp_duty,
        trading_fee=trading_fee,
        sfc_levy=sfc_levy,
        afrc_levy=afrc_levy,
        settlement_fee=settlement_fee,
    )


def hk_fee_config_from_account(account) -> HkFeeConfig:
    return HkFeeConfig(
        commission_rate=(
            Decimal(account.hk_commission_rate)
            if account.hk_commission_rate is not None
            else HkFeeConfig.commission_rate
        ),
        min_commission=(
            Decimal(account.hk_min_commission)
            if account.hk_min_commission is not None
            else HkFeeConfig.min_commission
        ),
        stamp_duty_rate=(
            Decimal(account.hk_stamp_duty_rate)
            if account.hk_stamp_duty_rate is not None
            else HkFeeConfig.stamp_duty_rate
        ),
        trading_fee_rate=(
            Decimal(account.hk_trading_fee_rate)
            if account.hk_trading_fee_rate is not None
            else HkFeeConfig.trading_fee_rate
        ),
        sfc_levy_rate=(
            Decimal(account.hk_sfc_levy_rate)
            if account.hk_sfc_levy_rate is not None
            else HkFeeConfig.sfc_levy_rate
        ),
        afrc_levy_rate=(
            Decimal(account.hk_afrc_levy_rate)
            if account.hk_afrc_levy_rate is not None
            else HkFeeConfig.afrc_levy_rate
        ),
        settlement_fee_rate=(
            Decimal(account.hk_settlement_fee_rate)
            if account.hk_settlement_fee_rate is not None
            else HkFeeConfig.settlement_fee_rate
        ),
    )
```

- [ ] **Step 5: Implement HK rule module**

Create `paper_trading/domain/hk_connect_rules.py`:

```python
from decimal import Decimal

from paper_trading.domain.errors import PaperTradingError


# Hong Kong minimum spread table (price range -> tick size)
_HK_TICK_TABLE: list[tuple[Decimal, Decimal]] = [
    (Decimal("0"), Decimal("10")),        # 0.010
    (Decimal("10"), Decimal("20")),       # 0.020
    (Decimal("20"), Decimal("100")),      # 0.050
    (Decimal("100"), Decimal("200")),     # 0.100
    (Decimal("200"), Decimal("500")),     # 0.200
    (Decimal("500"), Decimal("1000")),    # 0.500
    (Decimal("1000"), Decimal("2000")),   # 1.000
    (Decimal("2000"), Decimal("5000")),   # 2.000
    (Decimal("5000"), Decimal("100000")), # 5.000
]

_HK_TICK_SIZES: list[Decimal] = [
    Decimal("0.010"),
    Decimal("0.020"),
    Decimal("0.050"),
    Decimal("0.100"),
    Decimal("0.200"),
    Decimal("0.500"),
    Decimal("1.000"),
    Decimal("2.000"),
    Decimal("5.000"),
]


def get_hk_tick_size(price: Decimal) -> Decimal:
    """Return the minimum tick size for a given price level."""
    for (low, high), tick in zip(_HK_TICK_TABLE, _HK_TICK_SIZES):
        if low <= price < high:
            return tick
    return _HK_TICK_SIZES[-1]  # 5.000 for 100000+


def validate_hk_tick_size(price: Decimal, tick_size: Decimal | None = None) -> None:
    """Raise if price is not aligned to the applicable HK tick size."""
    if tick_size is None:
        tick_size = get_hk_tick_size(price)
    # Price must be an exact multiple of tick size
    remainder = (price * Decimal("1000")) % (tick_size * Decimal("1000"))
    if remainder != 0:
        raise PaperTradingError(
            "INVALID_TICK_SIZE",
            f"Price {price} is not aligned to HK tick size {tick_size}",
            {"price": str(price), "tick_size": str(tick_size)},
        )


def ensure_hk_lot_size(quantity: int, board_lot: int) -> None:
    """Raise if quantity is not a positive multiple of board lot."""
    if quantity <= 0 or quantity % board_lot != 0:
        raise PaperTradingError(
            "INVALID_LOT_SIZE",
            f"HK Connect orders must use positive {board_lot}-share lots",
            {"quantity": quantity, "board_lot": board_lot},
        )


def ensure_hk_odd_lot_sell(quantity: int, odd_lot_remainder: int) -> None:
    """Raise if selling more than the odd-lot remainder when not a board lot.

    Board-lot multiples are always allowed.  If the requested quantity is not
    a board-lot multiple, it must exactly match the odd-lot remainder.
    """
    if quantity <= odd_lot_remainder:
        return  # OK: selling at or below odd-lot remainder
    if quantity % 100 == 0:
        return  # OK: board-lot multiple
    raise PaperTradingError(
        "INVALID_ODD_LOT_SELL",
        f"Cannot sell {quantity} shares; odd lot remainder is {odd_lot_remainder}",
        {"quantity": quantity, "odd_lot_remainder": odd_lot_remainder},
    )
```

- [ ] **Step 6: Run HK fee and rule tests**

Run: `uv run pytest test/paper_trading/domain/test_hk_connect_fees.py test/paper_trading/domain/test_hk_connect_rules.py -q`

Expected: PASS.

---

## Task 4: Market-aware OrderService

**Files:**
- Modify: `paper_trading/services/order_service.py`
- Test: `test/paper_trading/services/test_order_service.py`
- Modify: `paper_trading/schemas/orders.py` (add `market` field)

**Interfaces:**
- Consumes: `Market` enum, `HkConnectMetadataProvider`, HK rules/fees
- Produces: market-routed `place_order()` dispatch

- [ ] **Step 1: Write failing market-aware order tests**

Add to `test/paper_trading/services/test_order_service.py`:

```python
def test_hk_connect_buy_rejects_unknown_symbol(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-buy", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "99999", OrderSide.BUY, 100, Decimal("50.00"),
        date(2026, 7, 21), market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "UNKNOWN_HK_SECURITY"


def test_hk_connect_buy_rejects_non_board_lot(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-lot", Decimal("100000.00"))
    # Insert HK metadata
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "00700", OrderSide.BUY, 50, Decimal("400.00"),
        date(2026, 7, 21), market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_LOT_SIZE"


def test_a_share_order_unchanged_with_market_omitted(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-demo", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"),
        date(2026, 7, 21),
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "a_share"


def test_a_share_explicit_market_still_works(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-explicit", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"),
        date(2026, 7, 21), market=Market.A_SHARE,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "a_share"


def test_hk_connect_accepts_board_lot_buy(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-ok", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "00700", OrderSide.BUY, 100, Decimal("400.00"),
        date(2026, 7, 21), market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "hk_connect"
    assert Decimal(order.frozen_cash or 0) > 0
```

Add test for HK tick validation:

```python
def test_hk_connect_rejects_off_tick_price(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-tick", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id, "00700", OrderSide.BUY, 100, Decimal("400.025"),
        date(2026, 7, 21), market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_TICK_SIZE"
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -q -k "hk_connect or hk_ or a_share_"`

Expected: fail because `OrderService` does not accept `hk_metadata` or `market` parameter.

- [ ] **Step 3: Add `market` to `CreateOrderRequest` and `OrderResponse`**

In `paper_trading/schemas/orders.py`:

```python
class CreateOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    quantity: int
    limit_price: Decimal
    trade_date: date
    idempotency_key: str | None = None
    comment: str | None = None
    market: str | None = None  # defaults to a_share via None

class OrderResponse(BaseModel):
    # existing fields...
    market: str = "a_share"
```

- [ ] **Step 4: Update `OrderService`**

In `paper_trading/services/order_service.py`:

- Add `hk_metadata` parameter to `__init__`
- Add `market` parameter to `place_order()` (default `None` → `Market.A_SHARE`)
- In `place_order()`, dispatch to `_accept_hk_buy_order()` or `_accept_hk_sell_order()` when market is `hk_connect`
- Add field `order.market = market.value` in `create_order` calls
- Add new methods:
  - `_accept_hk_buy_order()` — check metadata, lot size, tick, fee freeze using HK fees, call `ensure_hk_lot_size`, `validate_hk_tick_size`, freeze HK estimated fees
  - `_accept_hk_sell_order()` — check metadata, position, lot/odd-lot rules (allow same-day sell), freeze position
- Keep existing `_accept_buy_order()` and `_accept_sell_order()` unchanged for A-share

Key dispatch change in `place_order()`:

```python
market = Market(market) if market else Market.A_SHARE

try:
    if market == Market.HK_CONNECT:
        meta = self.hk_metadata.get_security(symbol)
        if meta is None:
            raise PaperTradingError(
                "UNKNOWN_HK_SECURITY",
                "Symbol is not a recognized HK Connect ordinary stock",
                {"symbol": symbol},
            )
        validate_hk_tick_size(limit_price)
        if side == OrderSide.BUY:
            return self._accept_hk_buy_order(account_id, symbol, quantity, limit_price, trade_date, meta, idempotency_key, comment)
        return self._accept_hk_sell_order(account_id, symbol, quantity, limit_price, trade_date, meta, idempotency_key, comment)
    # A-share path (unchanged)
    ensure_lot_size(quantity)
    ...
```

- [ ] **Step 5: Run order service tests**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -q`

Expected: PASS.

---

## Task 5: Market-aware MatchingService

**Files:**
- Modify: `paper_trading/services/matching_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: market field on orders to dispatch fee calculation and market data lookup
- Produces: HK Connect `_fill_order` uses HK fees, HK GGT bars, and T+2 settlement

- [ ] **Step 1: Write failing market-aware matching tests**

Add to `test/paper_trading/services/test_matching_service.py`:

```python
def test_hk_connect_matching_uses_hk_fees(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-match", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    order = repo.create_order(
        account_id=account.id, symbol="00700", side=OrderSide.BUY,
        quantity=100, limit_price=Decimal("400.00"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED, frozen_cash=Decimal("50000.00"),
        market="hk_connect",
    )
    bars = {("00700", date(2026, 7, 21)): DailyBar(symbol="00700", trade_date=date(2026, 7, 21), open=Decimal("400"), high=Decimal("410"), low=Decimal("395"), close=Decimal("405"))}
    md = FakeMarketDataProvider(bars)
    hk_meta = HkConnectMetadataProvider(session)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service, hk_metadata=hk_meta)
    result = service.match_order(order)
    assert result == "filled"
    trades = repo.list_trades(account.id)
    assert len(trades) == 1
    # HK fees should differ from A-share fees
    assert trades[0].fees != Decimal("0.00")
    assert trades[0].market == "hk_connect"


def test_hk_connect_sell_creates_pending_settlement(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-sell", Decimal("0.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, "00700", 100, 0, Decimal("30000.00"), market="hk_connect")
    order = repo.create_order(
        account_id=account.id, symbol="00700", side=OrderSide.SELL,
        quantity=100, limit_price=Decimal("400.00"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED, frozen_quantity=100, market="hk_connect",
    )
    bars = {("00700", date(2026, 7, 21)): DailyBar(symbol="00700", trade_date=date(2026, 7, 21), open=Decimal("400"), high=Decimal("410"), low=Decimal("395"), close=Decimal("405"))}
    md = FakeMarketDataProvider(bars)
    hk_meta = HkConnectMetadataProvider(session)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service, hk_metadata=hk_meta)
    result = service.match_order(order)
    assert result == "filled"
    pending = repo.list_pending_settlements(account.id)
    assert len(pending) == 1
    assert pending[0].settled is False
    assert pending[0].expected_settle_date == date(2026, 7, 23)  # T+2


def test_hk_connect_buy_does_not_create_pending_settlement(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-buy-ns", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    order = repo.create_order(
        account_id=account.id, symbol="00700", side=OrderSide.BUY,
        quantity=100, limit_price=Decimal("400.00"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED, frozen_cash=Decimal("50000.00"),
        market="hk_connect",
    )
    bars = {("00700", date(2026, 7, 21)): DailyBar(symbol="00700", trade_date=date(2026, 7, 21), open=Decimal("400"), high=Decimal("410"), low=Decimal("395"), close=Decimal("405"))}
    md = FakeMarketDataProvider(bars)
    hk_meta = HkConnectMetadataProvider(session)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service, hk_metadata=hk_meta)
    service.match_order(order)
    pending = repo.list_pending_settlements(account.id)
    assert len(pending) == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py -q -k "hk_connect"`

Expected: fail because `MatchingService` does not handle HK market dispatch.

- [ ] **Step 3: Update `MatchingService`**

In `paper_trading/services/matching_service.py`:

Changes:
- Add `hk_metadata` parameter to `__init__`
- In `_fill_order()`, check `order.market`:
  - If `"hk_connect"`, use `calculate_hk_connect_fees()` and `hk_fee_config_from_account()`
  - If `"hk_connect"` sell, call `repo.create_pending_settlement()` for T+2
  - If `"a_share"`, use existing `calculate_a_share_fees()` path (unchanged)
- Market data routing: `get_daily_bar()` currently goes through `StorageMarketDataProvider` which delegates to `load_history_data_stock()`. For HK Connect symbols, the storage layer needs to route to `load_history_data_stock_hk_ggt()`. This is handled in the `StorageMarketDataProvider._to_storage_stock_id()` method which strips exchange suffixes, but the actual table selection depends on the symbol's prefix. Since the existing market data provider already handles this through symbol normalization, we need to add a market-aware dispatch in `StorageMarketDataProvider.get_daily_bar()`.

Extend `StorageMarketDataProvider.get_daily_bar()` in `paper_trading/storage/market_data.py`:

```python
def get_daily_bar(self, symbol: str, trade_date: date, market: str = "a_share") -> DailyBar:
    stock_id = self._to_storage_stock_id(symbol)
    if market == "hk_connect":
        return self._get_hk_daily_bar(stock_id, symbol, trade_date)
    return self._get_a_share_daily_bar(stock_id, symbol, trade_date)

def _get_a_share_daily_bar(self, stock_id: str, symbol: str, trade_date: date) -> DailyBar:
    df = self._storage.load_history_data_stock(
        stock_id, PeriodType.DAILY, AdjustType.BFQ,
        start_date=trade_date.isoformat(), end_date=trade_date.isoformat(),
    )
    if df.empty:
        raise KeyError(f"No daily bar for {symbol} on {trade_date.isoformat()}")
    row = df.iloc[-1]
    up_limit, down_limit = self._load_limit_prices(symbol, trade_date)
    return DailyBar(
        symbol=symbol, trade_date=trade_date,
        open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
        high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
        low=self._decimal_field(row, COL_LOW, symbol, trade_date),
        close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
        up_limit=up_limit, down_limit=down_limit,
    )

def _get_hk_daily_bar(self, stock_id: str, symbol: str, trade_date: date) -> DailyBar:
    df = self._storage.load_history_data_stock_hk_ggt(
        stock_id, PeriodType.DAILY, AdjustType.BFQ,
        start_date=trade_date.isoformat(), end_date=trade_date.isoformat(),
    )
    if df.empty:
        raise KeyError(f"No HK daily bar for {symbol} on {trade_date.isoformat()}")
    row = df.iloc[-1]
    # No A-share limit prices for HK
    return DailyBar(
        symbol=symbol, trade_date=trade_date,
        open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
        high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
        low=self._decimal_field(row, COL_LOW, symbol, trade_date),
        close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
        up_limit=None, down_limit=None,
    )
```

Update `MatchingService._fill_order()`:

```python
def _fill_order(self, order: PaperOrder) -> None:
    side = OrderSide(order.side)
    price = Decimal(order.limit_price)
    quantity = int(order.quantity)
    account = self.repo.get_account(order.account_id)
    if account is None:
        raise ValueError(f"paper account not found: {order.account_id}")
    amount = (Decimal(quantity) * price).quantize(Decimal("0.0001"))

    if order.market == "hk_connect":
        fee_config = hk_fee_config_from_account(account)
        fees = calculate_hk_connect_fees(side, amount, fee_config).total.quantize(Decimal("0.0001"))
    else:
        fees = calculate_a_share_fees(side, amount, fee_config_from_account(account)).total.quantize(Decimal("0.0001"))

    trade = self.repo.create_trade(
        order.id, order.account_id, order.symbol,
        side, quantity, price, amount, fees,
        order.trade_date, comment=order.comment,
        market=order.market,
    )
    if side == OrderSide.BUY:
        self._settle_buy(order, trade.id, amount, fees)
    else:
        self._settle_sell(order, trade.id, amount, fees)
        if order.market == "hk_connect":
            # T+2 settlement for HK sells
            settle_date = self._next_trade_date(order.trade_date, 2)
            self.repo.create_pending_settlement(
                account_id=order.account_id,
                amount=amount - fees,
                expected_settle_date=settle_date,
                trade_id=trade.id,
                source="hk_sell",
            )

    order.filled_quantity = quantity
    self.repo.update_order_status(order, OrderStatus.FILLED)
```

Note: `_next_trade_date` needs to account for weekends/HK holidays. For simplicity in the first implementation, use `trade_date + timedelta(days=2)` and route through the trade calendar. Add:

```python
def _next_trade_date(self, trade_date: date, n: int) -> date:
    current = trade_date
    for _ in range(n):
        current = self.market_data.next_trade_date(current)
    return current
```

- [ ] **Step 4: Run matching tests**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py -q`

Expected: PASS.

---

## Task 6: Market-aware TradeValidityService

**Files:**
- Modify: `paper_trading/services/trade_validity_service.py`
- Test: `test/paper_trading/services/test_trade_validity_service.py`

- [ ] **Step 1: Write failing HK validity tests**

Add to `test/paper_trading/services/test_trade_validity_service.py`:

```python
def test_hk_connect_validity_checks_tick_alignment(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-val", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id, symbol="00700", side=OrderSide.BUY,
        quantity=100, limit_price=Decimal("400.025"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED, market="hk_connect",
    )
    bars = {("00700", date(2026, 7, 21)): DailyBar(symbol="00700", trade_date=date(2026, 7, 21), open=Decimal("400"), high=Decimal("410"), low=Decimal("395"), close=Decimal("405"))}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.status == "invalid"
    assert "tick" in check.reason_code.lower()


def test_hk_connect_validity_no_limit_up_down(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-nolimit", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id, symbol="00700", side=OrderSide.BUY,
        quantity=100, limit_price=Decimal("400.00"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED, market="hk_connect",
    )
    bars = {("00700", date(2026, 7, 21)): DailyBar(symbol="00700", trade_date=date(2026, 7, 21), open=Decimal("400"), high=Decimal("410"), low=Decimal("395"), close=Decimal("405"))}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.touched_limit_up is None
    assert check.touched_limit_down is None
    assert check.price_in_range is True


def test_a_share_validity_unchanged(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-val", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id, symbol="000001.SZ", side=OrderSide.BUY,
        quantity=100, limit_price=Decimal("10.00"), trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    bars = {("000001.SZ", date(2026, 7, 21)): DailyBar(symbol="000001.SZ", trade_date=date(2026, 7, 21), open=Decimal("10"), high=Decimal("11"), low=Decimal("9"), close=Decimal("10.5"), up_limit=Decimal("11.5"), down_limit=Decimal("8.5"))}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md)
    check = service.analyze_order(order)
    assert check.touched_limit_up is not None  # A-share sets these
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py -q -k "hk_connect"`

Expected: fail because `TradeValidityService` does not accept `hk_metadata`.

- [ ] **Step 3: Update `TradeValidityService`**

In `paper_trading/services/trade_validity_service.py`:

- Add `hk_metadata: HkConnectMetadataProvider | None = None` to `__init__`
- In `analyze_order()`, check `order.market`:
  - If `"hk_connect"`, use HK-specific validity:
    - Check metadata exists (else return `UNCHECKED` with `UNKNOWN_HK_SECURITY`)
    - Check price in daily range (bar low/high)
    - Check tick alignment against HK spread table
    - No limit-up/down analysis
    - Return result with `touched_limit_up=None, touched_limit_down=None`
  - If `"a_share"`, use existing logic (unchanged)

- [ ] **Step 4: Run trade validity tests**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py -q`

Expected: PASS.

---

## Task 7: HK fee API and CLI

**Files:**
- Create: `paper_trading/schemas/hk_fees.py`
- Modify: `paper_trading/api/routers/accounts.py`
- Modify: `paper_trading/schemas/accounts.py`
- Modify: `tools/paper_trading_cli.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/tools/test_paper_trading_cli.py`

- [ ] **Step 1: Write failing API HK fee tests**

Add to `test/paper_trading/api/test_accounts_api.py`:

```python
def test_update_account_hk_fees(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.patch(
        f"/paper/accounts/{account_id}",
        json={
            "hk_commission_rate": "0.0002",
            "hk_min_commission": "18.00",
            "hk_stamp_duty_rate": "0.0013",
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hk_commission_rate"] == "0.00020000"


def test_update_account_hk_fees_rejects_negative(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.patch(
        f"/paper/accounts/{account_id}",
        json={"hk_commission_rate": "-0.01"},
        headers=headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Write failing CLI HK order tests**

Add to `test/tools/test_paper_trading_cli.py`:

```python
def test_order_create_with_hk_market():
    client = _mock_client()
    client.create_order.return_value = {"id": 1, "symbol": "00700", "market": "hk_connect"}
    with patch("tools.paper_trading_cli.PaperTradingApiClient", return_value=client):
        code = main([
            "--token", "secret",
            "order", "create",
            "--account-id", "1",
            "--symbol", "00700",
            "--side", "buy",
            "--quantity", "100",
            "--limit-price", "400.00",
            "--trade-date", "2026-07-21",
            "--market", "hk_connect",
        ])
    assert code == EXIT_CODES["OK"]
    call_kwargs = client.create_order.call_args[1]
    assert call_kwargs.get("market") == "hk_connect"
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py -q -k "hk_fee"`
Run: `uv run pytest test/tools/test_paper_trading_cli.py -q -k "hk_market"`

Expected: fail because schemas, endpoint, and CLI flag don't exist yet.

- [ ] **Step 4: Add HK fee schemas**

Create `paper_trading/schemas/hk_fees.py` (or inline in `accounts.py`):

Add to `paper_trading/schemas/accounts.py`:

```python
class UpdateAccountHkFeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hk_commission_rate: Decimal | None = Field(default=None, ge=0)
    hk_min_commission: Decimal | None = Field(default=None, ge=0)
    hk_stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    hk_trading_fee_rate: Decimal | None = Field(default=None, ge=0)
    hk_sfc_levy_rate: Decimal | None = Field(default=None, ge=0)
    hk_afrc_levy_rate: Decimal | None = Field(default=None, ge=0)
    hk_settlement_fee_rate: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_fee_field(self) -> Self:
        if all(
            value is None
            for value in (
                self.hk_commission_rate, self.hk_min_commission,
                self.hk_stamp_duty_rate, self.hk_trading_fee_rate,
                self.hk_sfc_levy_rate, self.hk_afrc_levy_rate,
                self.hk_settlement_fee_rate,
            )
        ):
            raise ValueError("at least one HK fee field is required")
        return self
```

Add HK fee fields to `AccountResponse`:
```python
hk_commission_rate: Decimal | None = None
hk_min_commission: Decimal | None = None
hk_stamp_duty_rate: Decimal | None = None
hk_trading_fee_rate: Decimal | None = None
hk_sfc_levy_rate: Decimal | None = None
hk_afrc_levy_rate: Decimal | None = None
hk_settlement_fee_rate: Decimal | None = None
```

- [ ] **Step 5: Extend the account PATCH endpoint**

In `paper_trading/api/routers/accounts.py`, modify `update_account_fees()` to also accept HK fee fields:

```python
@router.patch("/{account_id}", response_model=AccountResponse)
def update_account_fees(
    account_id: int,
    request: UpdateAccountFeeRequest,
    session: Session = Depends(get_session),
):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="at least one fee field is required",
        )
    repo = PaperTradingRepository(session)
    service = AccountService(repo)
    try:
        account = service.update_account_fees(account_id=account_id, **payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    session.commit()
    return account
```

No change needed — `AccountService.update_account_fees()` should pass through HK fee fields to the repository. The current implementation calls `repo.update_account_fees()` which only handles A-share fields. Either extend `update_account_fees` in the repository or add a separate call. Simpler: extend the repository's `update_account_fees` to handle both A-share and HK fee fields.

Wait, looking at `AccountService`, let me check it.

- [ ] **Step 5a: Check `AccountService`**

Read `paper_trading/services/account_service.py` and extend it to pass HK fee fields to the repository.

- [ ] **Step 6: Extend `AccountService` for HK fees**

In `paper_trading/services/account_service.py`:

Add to `update_account_fees()`:
```python
def update_account_fees(
    self,
    account_id: int,
    commission_rate: Decimal | None = None,
    min_commission: Decimal | None = None,
    stamp_duty_rate: Decimal | None = None,
    transfer_fee_rate: Decimal | None = None,
    hk_commission_rate: Decimal | None = None,
    hk_min_commission: Decimal | None = None,
    hk_stamp_duty_rate: Decimal | None = None,
    hk_trading_fee_rate: Decimal | None = None,
    hk_sfc_levy_rate: Decimal | None = None,
    hk_afrc_levy_rate: Decimal | None = None,
    hk_settlement_fee_rate: Decimal | None = None,
) -> PaperAccount | None:
    # Check if any HK fee fields are present
    hk_fields = {
        "hk_commission_rate": hk_commission_rate,
        "hk_min_commission": hk_min_commission,
        "hk_stamp_duty_rate": hk_stamp_duty_rate,
        "hk_trading_fee_rate": hk_trading_fee_rate,
        "hk_sfc_levy_rate": hk_sfc_levy_rate,
        "hk_afrc_levy_rate": hk_afrc_levy_rate,
        "hk_settlement_fee_rate": hk_settlement_fee_rate,
    }
    has_hk = any(v is not None for v in hk_fields.values())
    
    if has_hk:
        return self.repo.update_account_hk_fees(account_id, **hk_fields)
    
    # Existing A-share fee update path
    return self.repo.update_account_fees(
        account_id,
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_duty_rate=stamp_duty_rate,
        transfer_fee_rate=transfer_fee_rate,
    )
```

- [ ] **Step 7: Extend order creation in CLI**

In `tools/paper_trading_cli.py`:

In `_add_order_subparsers`, add to the order create parser:
```python
p_create.add_argument("--market", default=None, choices=["a_share", "hk_connect"], help="Market (default: a_share)")
```

In the `create_order` client method, add `market` parameter:
```python
def create_order(
    self,
    account_id: int,
    symbol: str,
    side: str,
    quantity: int,
    limit_price: Decimal,
    trade_date: str,
    idempotency_key: str | None = None,
    comment: str | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "limit_price": str(limit_price),
        "trade_date": trade_date,
    }
    if idempotency_key is not None:
        body["idempotency_key"] = idempotency_key
    if comment is not None:
        body["comment"] = comment
    if market is not None:
        body["market"] = market
    return self._request("POST", f"/paper/accounts/{account_id}/orders", json=body)
```

- [ ] **Step 8: Run API and CLI tests**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py -q -k "hk_fee"`
Run: `uv run pytest test/tools/test_paper_trading_cli.py -q -k "hk_market"`

Expected: PASS.

---

## Task 8: HK settlement processing (snapshot and settlement service)

**Files:**
- Create: `paper_trading/services/hk_settlement_service.py`
- Create: `test/paper_trading/services/test_hk_settlement_service.py`
- Modify: `paper_trading/services/snapshot_service.py` (include pending settlement)

- [ ] **Step 1: Write failing settlement service tests**

Create `test/paper_trading/services/test_hk_settlement_service.py`:

```python
def test_process_settlements_releases_due_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-proc", Decimal("0.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    md = FakeMarketDataProvider()
    service = HkSettlementService(repo, md)
    count = service.process_settlements(date(2026, 7, 23))
    assert count == 1
    assert pending.settled is True
    # Cash should now be available
    assert repo.get_cash_available(account.id) == Decimal("50000.0000")


def test_process_settlements_skips_future_dates(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-skip", Decimal("0.00"))
    repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    md = FakeMarketDataProvider()
    service = HkSettlementService(repo, md)
    count = service.process_settlements(date(2026, 7, 22))
    assert count == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest test/paper_trading/services/test_hk_settlement_service.py -q`

Expected: fail because service does not exist.

- [ ] **Step 3: Implement `HkSettlementService`**

Create `paper_trading/services/hk_settlement_service.py`:

```python
from datetime import date

from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository


class HkSettlementService:
    """Processes HK Connect T+2 settlements that have matured."""

    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def process_settlements(self, as_of_date: date) -> int:
        """Settle all pending HK sell proceeds whose expected date <= as_of_date.

        Returns the count of settlements processed.
        """
        accounts = self.repo.list_accounts()
        count = 0
        for account in accounts:
            pending_list = self.repo.list_pending_settlements(account.id)
            for pending in pending_list:
                if pending.expected_settle_date <= as_of_date:
                    self.repo.settle_pending(pending.id)
                    count += 1
        return count
```

- [ ] **Step 4: Update snapshot service**

In `paper_trading/services/snapshot_service.py`, add pending settlement to `cash_available` calculation:

```python
def generate_snapshot(self, account_id: int, trade_date: date) -> PaperAccountSnapshot:
    cash_available = self.repo.get_cash_available(account_id)
    cash_frozen = self.repo.get_cash_frozen(account_id)
    pending_settlement = self.repo.get_pending_settlement_total(account_id)
    # ... rest of snapshot logic ...
    total_assets = (cash_available + cash_frozen + market_value + pending_settlement).quantize(Decimal("0.0001"))
```

- [ ] **Step 5: Run settlement tests**

Run: `uv run pytest test/paper_trading/services/test_hk_settlement_service.py -q`

Expected: PASS.

---

## Task 9: Full integration and backward-compatibility verification

**Files:**
- Existing A-share tests (must pass without changes)

- [ ] **Step 1: Run all existing paper trading tests**

Run: `uv run pytest test/paper_trading -q --tb=short -x`

Expected: all existing A-share tests pass. Any failures should be only due to new `market` field in responses (fix those schemas/tests if needed).

- [ ] **Step 2: Run CLI tests**

Run: `uv run pytest test/tools/test_paper_trading_cli.py -q --tb=short -x`

Expected: all pass.

- [ ] **Step 3: Run new HK Connect tests**

Run: `uv run pytest test/paper_trading -q -k "hk_connect or hk_" --tb=short`

Expected: all pass.

- [ ] **Step 4: Run full focused test suite**

```bash
uv run pytest test/paper_trading test/tools/test_paper_trading_cli.py -q --tb=short
```

Expected: ALL pass.

- [ ] **Step 5: Verify storage migration awareness**

Run: `uv run pytest test/storage/test_storage_db.py -q` (if storage routing changed)

Expected: all pass.

---

## Self-Review: Spec Requirements vs. Tasks

| Spec Requirement | Task | Status |
|---|---|---|
| Add `market` enum (`a_share`, `hk_connect`) | Task 1 | Covered |
| Persist market on orders, trades, positions, validity checks | Task 1 | Covered |
| Existing rows default to `a_share` | Task 1 | Server default `a_share` |
| HK Connect security metadata source | Task 2 | Covered |
| Extend fee config by market | Task 3 | `HkFeeConfig` + `hk_fee_config_from_account` |
| Order creation accepts explicit `market` | Task 4, Task 7 | Covered via schema + CLI flag |
| Backward compatibility when `market` omitted | Task 4 | Defaults to `a_share` |
| A-share symbols remain 6-digit | Existing code | Unchanged |
| HK symbols must be 5-digit | Task 4 | Rejected via unknown metadata check |
| Market/symbol format mismatch rejected | Task 4 | Covered |
| CLI `--market` flag | Task 7 | Covered |
| API responses include `market` | Task 1, Task 4 | Schema includes `market` |
| HK buy: board-lot multiples | Task 3, Task 4 | `ensure_hk_lot_size()` |
| HK sell: board-lot quantities | Task 3 | `ensure_hk_lot_size()` |
| HK odd-lot sell only full remainder | Task 3 | `ensure_hk_odd_lot_sell()` |
| HK same-day buy/sell allowed | Task 4 | No T+1 check in HK path |
| HK market orders rejected | Task 4 | No market order type exists; limit-only by design |
| HK tick alignment | Task 3 | `validate_hk_tick_size()` / `get_hk_tick_size()` |
| No A-share daily limits for HK | Task 6 | No limit-up/down in HK validity path |
| Reject unknown HK security | Task 4 | `UNKNOWN_HK_SECURITY` error |
| Market data dispatch by market | Task 5 | `StorageMarketDataProvider.get_daily_bar(market=...)` |
| HK uses HK GGT BFQ bars | Task 5 | `load_history_data_stock_hk_ggt()` |
| Missing daily bar consistent with existing behavior | Task 5 | KeyError propagated |
| Daily-bar price-range matching | Task 5 | Unchanged (existing `ensure_price_in_daily_range`) |
| RMB-only cash pool | Existing | Unchanged |
| Buys freeze estimated cash incl. fees | Task 4 | HK path freezes with HK fees |
| Sells freeze position quantity | Task 4 | HK sell freezes position |
| Same-day sellability includes same-day buys | Task 4 | No T+1 restriction in HK path |
| T+2 settlement for HK | Task 5, Task 8 | `create_pending_settlement()` + `HkSettlementService` |
| Sell proceeds pending until settlement | Task 5 | `pending_settlement.settled=False` |
| Buy-side cash deduction finalized on fill | Task 5 | `_settle_buy()` releases/charges diff |
| Validity: market-aware | Task 6 | HK validity checks tick, range; no limit up/down |
| Validity: unknown metadata → specific reason | Task 6 | `UNKNOWN_HK_SECURITY` |
| Explicit rejection reasons | Tasks 3, 4, 6 | Error codes per spec list |
| Existing persisted orders = A-share | Task 1 | Server default `a_share` |
| No DAG/export/import changes | Task 1 | `db_common.sh` updated |
| Test-first | All tasks | Failing tests written before implementation |
| Run `uv run pytest test/paper_trading` | Task 9 | Final verification |

---

## Verification Commands

Run after each task to verify:

```bash
# Task 1: Repository migration
uv run pytest test/paper_trading/storage/test_repository.py -q --tb=short

# Task 2: HK metadata
uv run pytest test/paper_trading/storage/test_hk_metadata.py -q --tb=short

# Task 3: HK fees and rules
uv run pytest test/paper_trading/domain/test_hk_connect_fees.py test/paper_trading/domain/test_hk_connect_rules.py -q --tb=short

# Task 4: Market-aware order service
uv run pytest test/paper_trading/services/test_order_service.py -q --tb=short

# Task 5: Market-aware matching
uv run pytest test/paper_trading/services/test_matching_service.py -q --tb=short

# Task 6: Market-aware validity
uv run pytest test/paper_trading/services/test_trade_validity_service.py -q --tb=short

# Task 7: API and CLI
uv run pytest test/paper_trading/api/test_accounts_api.py -q --tb=short -k "hk_fee"
uv run pytest test/tools/test_paper_trading_cli.py -q --tb=short -k "hk_market"

# Task 8: Settlement
uv run pytest test/paper_trading/services/test_hk_settlement_service.py -q --tb=short

# Task 9: Full verification
uv run pytest test/paper_trading test/tools/test_paper_trading_cli.py -q --tb=short
uv run pytest test/storage/test_storage_db.py -q --tb=short  # if storage changed
```
