# Paper Trading Cash Flows And NAV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paper-trading deposits and withdrawals, and make returns, drawdown, and risk metrics use a fund-style NAV/share model.

**Architecture:** Extend the existing cash-ledger accounting path instead of adding a separate funding subsystem. Store current NAV/share state on accounts, store NAV/share snapshots with account snapshots, expose account-scoped cash-flow API and CLI commands, and update frontend account and analytics views to show deposits, withdrawals, NAV, and NAV return.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest, Ruff, Next.js App Router, React 19, TypeScript, Vitest, Testing Library.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3`.
- Deposits and withdrawals use a fund-style NAV/share model.
- Cash flows are pre-market effective on `trade_date`.
- Withdrawals are limited to available cash only; no auto-sell, no frozen-cash use, no negative cash.
- Cash-flow ledger entries are immutable; corrections are reverse cash-flow entries.
- `total_return` remains in the analytics API but means NAV return after this change.
- Add `simple_asset_return` for the old scale-sensitive total-assets-vs-initial-cash reference.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA.

---

## File Map

- `storage/model/paper_trading.py`
  - Add NAV/share fields to `PaperAccount`, `PaperCashLedger`, and `PaperAccountSnapshot`.
- `paper_trading/domain/enums.py`
  - Add `CashEventType.WITHDRAWAL`.
- `paper_trading/storage/repository.py`
  - Initialize account NAV/share fields, extend `add_cash_event()`, add account NAV update helpers, and persist snapshot NAV fields.
- `paper_trading/schemas/accounts.py`
  - Add account NAV fields, cash-flow request/response models, and cash-ledger NAV fields.
- `paper_trading/schemas/snapshots.py`
  - Add snapshot NAV/share/cash-flow fields.
- `paper_trading/schemas/analytics.py`
  - Add overview NAV/share and `simple_asset_return` fields.
- `paper_trading/services/cash_service.py`
  - New service for deposit and withdrawal validation and transactional account/ledger updates.
- `paper_trading/services/snapshot_service.py`
  - Compute snapshot NAV from `total_assets / share_count` and persist account latest NAV.
- `paper_trading/services/analytics_service.py`
  - Compute overview return, drawdown, Sharpe, Sortino, and Calmar from NAV series.
- `paper_trading/api/routers/accounts.py`
  - Add deposit and withdrawal endpoints.
- `tools/paper_trading_cli.py`
  - Add API client methods, account subcommands, validation, and output for deposits/withdrawals.
- `frontend/paper-trading/lib/types.ts`
  - Add NAV/share fields and cash-flow request/response types.
- `frontend/paper-trading/lib/api-client.ts`
  - Add deposit and withdrawal helpers.
- `frontend/paper-trading/features/accounts/cash-flow-modal.tsx`
  - New modal for deposit/withdrawal forms.
- `frontend/paper-trading/features/accounts/accounts-page.tsx`
  - Wire deposit/withdrawal actions and refresh account detail after success.
- `frontend/paper-trading/features/trading/trading-tables.tsx`
  - Show cash-ledger labels, NAV, and share delta.
- `frontend/paper-trading/features/analytics/analytics-summary.tsx`
  - Show NAV/share and rename return label.
- `frontend/paper-trading/features/analytics/asset-chart.tsx`
  - Default chart to NAV series with old total-assets fallback.
- `docs/paper_trading.md`
  - Document API, CLI, NAV/share accounting, and changed metric meanings.
- Tests listed in each task.

## Task 1: Add NAV/share storage fields and repository support

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `paper_trading/domain/enums.py`
- Modify: `paper_trading/storage/repository.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces: `CashEventType.WITHDRAWAL`
- Produces: `PaperTradingRepository.add_cash_event(account_id, event_type, amount, order_id=None, trade_id=None, note=None, trade_date=None, net_asset_value=None, share_delta=None)`
- Produces: `PaperTradingRepository.update_account_nav_state(account, share_count, net_asset_value, cumulative_deposit, cumulative_withdrawal)`
- Produces: account fields `share_count`, `net_asset_value`, `cumulative_deposit`, `cumulative_withdrawal`

- [ ] **Step 1: Write failing repository tests**

Add tests to `test/paper_trading/storage/test_repository.py`:

```python
def test_create_account_initializes_nav_share_state(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("nav-demo", Decimal("100000.00"))
    ledger = repo.list_cash_ledger(account.id)

    assert account.net_asset_value == Decimal("1.000000")
    assert account.share_count == Decimal("100000.000000")
    assert account.cumulative_deposit == Decimal("100000.0000")
    assert account.cumulative_withdrawal == Decimal("0.0000")
    assert ledger[0].event_type == "deposit"
    assert ledger[0].net_asset_value == Decimal("1.000000")
    assert ledger[0].share_delta == Decimal("100000.000000")


def test_add_cash_event_persists_nav_share_fields(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-event-demo", Decimal("100000.00"))

    event = repo.add_cash_event(
        account.id,
        CashEventType.WITHDRAWAL,
        Decimal("-5000.0000"),
        trade_date=date(2026, 7, 20),
        net_asset_value=Decimal("1.250000"),
        share_delta=Decimal("-4000.000000"),
        note="withdraw",
    )

    assert event.trade_date == date(2026, 7, 20)
    assert event.net_asset_value == Decimal("1.250000")
    assert event.share_delta == Decimal("-4000.000000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: fail because NAV/share columns and `WITHDRAWAL` do not exist.

- [ ] **Step 3: Add model and enum fields**

In `paper_trading/domain/enums.py`, change `CashEventType` to:

```python
class CashEventType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FREEZE = "freeze"
    RELEASE = "release"
    TRADE = "trade"
    FEE = "fee"
```

In `storage/model/paper_trading.py`, add these columns to the named ORM classes:

```python
class PaperAccount(Base):
    share_count = Column(Numeric(20, 6), nullable=False, server_default=text("0"))
    net_asset_value = Column(Numeric(20, 6), nullable=False, server_default=text("1"))
    cumulative_deposit = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    cumulative_withdrawal = Column(Numeric(20, 4), nullable=False, server_default=text("0"))


class PaperCashLedger(Base):
    trade_date = Column(Date, nullable=True, index=True)
    net_asset_value = Column(Numeric(20, 6), nullable=True)
    share_delta = Column(Numeric(20, 6), nullable=True)


class PaperAccountSnapshot(Base):
    net_asset_value = Column(Numeric(20, 6), nullable=True)
    share_count = Column(Numeric(20, 6), nullable=True)
    cumulative_deposit = Column(Numeric(20, 4), nullable=True)
    cumulative_withdrawal = Column(Numeric(20, 4), nullable=True)
    net_cash_flow = Column(Numeric(20, 4), nullable=True)
```

- [ ] **Step 4: Update repository methods**

In `paper_trading/storage/repository.py`, keep the existing `create_account` signature and replace the current `PaperAccount(...)` construction plus initial cash event with:

```python
initial_nav = Decimal("1.000000")
initial_shares = Decimal(initial_cash).quantize(Decimal("0.000001"))
account = PaperAccount(
    name=name,
    initial_cash=initial_cash,
    fee_preset=preset_name,
    commission_rate=commission_rate if commission_rate is not None else preset.commission_rate,
    min_commission=min_commission if min_commission is not None else preset.min_commission,
    stamp_duty_rate=stamp_duty_rate if stamp_duty_rate is not None else preset.stamp_duty_rate,
    transfer_fee_rate=transfer_fee_rate if transfer_fee_rate is not None else preset.transfer_fee_rate,
    share_count=initial_shares,
    net_asset_value=initial_nav,
    cumulative_deposit=Decimal(initial_cash).quantize(Decimal("0.0001")),
    cumulative_withdrawal=Decimal("0.0000"),
)
self.session.add(account)
self.session.flush()
self.add_cash_event(
    account.id,
    CashEventType.DEPOSIT,
    Decimal(initial_cash).quantize(Decimal("0.0001")),
    net_asset_value=initial_nav,
    share_delta=initial_shares,
    note="initial_cash",
)
return account
```

Extend `add_cash_event`:

```python
def add_cash_event(
    self,
    account_id: int,
    event_type: CashEventType | str,
    amount: Decimal,
    order_id: int | None = None,
    trade_id: int | None = None,
    note: str | None = None,
    trade_date: date | None = None,
    net_asset_value: Decimal | None = None,
    share_delta: Decimal | None = None,
) -> PaperCashLedger:
    event = PaperCashLedger(
        account_id=account_id,
        event_type=str(event_type),
        amount=amount,
        order_id=order_id,
        trade_id=trade_id,
        trade_date=trade_date,
        net_asset_value=net_asset_value,
        share_delta=share_delta,
        note=note,
    )
    self.session.add(event)
    self.session.flush()
    return event
```

Add helper:

```python
def update_account_nav_state(
    self,
    account: PaperAccount,
    *,
    share_count: Decimal,
    net_asset_value: Decimal,
    cumulative_deposit: Decimal,
    cumulative_withdrawal: Decimal,
) -> PaperAccount:
    account.share_count = share_count.quantize(Decimal("0.000001"))
    account.net_asset_value = net_asset_value.quantize(Decimal("0.000001"))
    account.cumulative_deposit = cumulative_deposit.quantize(Decimal("0.0001"))
    account.cumulative_withdrawal = cumulative_withdrawal.quantize(Decimal("0.0001"))
    self.session.flush()
    return account
```

- [ ] **Step 5: Run repository tests**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add storage/model/paper_trading.py paper_trading/domain/enums.py paper_trading/storage/repository.py test/paper_trading/storage/test_repository.py
git commit -m "feat(paper-trading): add NAV cash ledger fields"
```

## Task 2: Add backend cash-flow service, schemas, and API endpoints

**Files:**
- Create: `paper_trading/services/cash_service.py`
- Modify: `paper_trading/schemas/accounts.py`
- Modify: `paper_trading/api/routers/accounts.py`
- Test: `test/paper_trading/services/test_cash_service.py`
- Test: `test/paper_trading/api/test_accounts_api.py`

**Interfaces:**
- Consumes: repository methods from Task 1
- Produces: `CashService.deposit(account_id, amount, trade_date, note)`
- Produces: `CashService.withdraw(account_id, amount, trade_date, note)`
- Produces: `CashFlowRequest`, `CashFlowResponse`

- [ ] **Step 1: Write failing service tests**

Create `test/paper_trading/services/test_cash_service.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.services.cash_service import CashService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cash_service.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_deposit_adds_cash_and_mints_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).deposit(account.id, Decimal("25000.00"), date(2026, 7, 20), "add cash")
    session.commit()

    assert result.ledger.amount == Decimal("25000.0000")
    assert result.ledger.share_delta == Decimal("25000.000000")
    assert result.account.share_count == Decimal("125000.000000")
    assert result.account.net_asset_value == Decimal("1.000000")
    assert result.cash_available == Decimal("125000.0000")
    engine.dispose()


def test_withdraw_reduces_cash_and_redeems_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).withdraw(account.id, Decimal("5000.00"), date(2026, 7, 20), "take cash")
    session.commit()

    assert result.ledger.amount == Decimal("-5000.0000")
    assert result.ledger.share_delta == Decimal("-5000.000000")
    assert result.account.share_count == Decimal("95000.000000")
    assert result.cash_available == Decimal("95000.0000")
    engine.dispose()


def test_withdraw_rejects_more_than_available_cash(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    with pytest.raises(ValueError, match="withdrawal amount 100001.0000 exceeds available cash 100000.0000"):
        CashService(repo).withdraw(account.id, Decimal("100001.00"), date(2026, 7, 20), None)

    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()
```

- [ ] **Step 2: Write failing API tests**

Add to `test/paper_trading/api/test_accounts_api.py`:

```python
def test_deposit_endpoint_returns_cash_flow_response(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.post(
        f"/paper/accounts/{account_id}/cash/deposit",
        json={"amount": "25000.00", "trade_date": "2026-07-20", "note": "add cash"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ledger"]["event_type"] == "deposit"
    assert body["ledger"]["share_delta"] == "25000.000000"
    assert body["cash_available"] == "125000.0000"
    assert body["share_count"] == "125000.000000"


def test_withdraw_endpoint_rejects_excess_cash(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.post(
        f"/paper/accounts/{account_id}/cash/withdraw",
        json={"amount": "100001.00", "trade_date": "2026-07-20"},
        headers=headers,
    )

    assert response.status_code == 422
    assert "exceeds available cash" in response.json()["detail"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py -q`

Expected: fail because service, schemas, and routes do not exist.

- [ ] **Step 4: Add schemas**

In `paper_trading/schemas/accounts.py`, extend `AccountResponse` and `CashLedgerResponse`, then add cash-flow models:

```python
class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    initial_cash: Decimal
    fee_preset: str
    commission_rate: Decimal
    min_commission: Decimal
    stamp_duty_rate: Decimal
    transfer_fee_rate: Decimal
    status: str
    base_currency: str
    share_count: Decimal
    net_asset_value: Decimal
    cumulative_deposit: Decimal
    cumulative_withdrawal: Decimal


class CashLedgerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    event_type: str
    amount: Decimal
    trade_date: date | None = None
    net_asset_value: Decimal | None = None
    share_delta: Decimal | None = None
    note: str | None = None


class CashFlowRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    trade_date: date
    note: str | None = None


class CashFlowResponse(BaseModel):
    account_id: int
    cash_available: Decimal
    net_asset_value: Decimal
    share_count: Decimal
    ledger: CashLedgerResponse
```

- [ ] **Step 5: Add `CashService`**

Create `paper_trading/services/cash_service.py`:

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import AccountStatus, CashEventType
from paper_trading.storage.models import PaperAccount, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository

_MONEY = Decimal("0.0001")
_NAV = Decimal("0.000001")


@dataclass(frozen=True)
class CashFlowResult:
    account: PaperAccount
    ledger: PaperCashLedger
    cash_available: Decimal


class CashService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def deposit(self, account_id: int, amount: Decimal, trade_date: date, note: str | None = None) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        nav = self._current_nav(account)
        share_delta = (amount / nav).quantize(_NAV)
        ledger = self.repo.add_cash_event(
            account_id,
            CashEventType.DEPOSIT,
            amount,
            trade_date=trade_date,
            net_asset_value=nav,
            share_delta=share_delta,
            note=note,
        )
        self.repo.update_account_nav_state(
            account,
            share_count=Decimal(account.share_count or 0) + share_delta,
            net_asset_value=nav,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0) + amount,
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0),
        )
        return CashFlowResult(account=account, ledger=ledger, cash_available=self.repo.get_cash_available(account_id))

    def withdraw(self, account_id: int, amount: Decimal, trade_date: date, note: str | None = None) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        cash_available = self.repo.get_cash_available(account_id)
        if amount > cash_available:
            raise ValueError(f"withdrawal amount {amount} exceeds available cash {cash_available}")
        nav = self._current_nav(account)
        share_delta = -(amount / nav).quantize(_NAV)
        next_shares = Decimal(account.share_count or 0) + share_delta
        if next_shares < 0:
            raise ValueError("withdrawal would make share count negative")
        ledger = self.repo.add_cash_event(
            account_id,
            CashEventType.WITHDRAWAL,
            -amount,
            trade_date=trade_date,
            net_asset_value=nav,
            share_delta=share_delta,
            note=note,
        )
        self.repo.update_account_nav_state(
            account,
            share_count=next_shares,
            net_asset_value=nav,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0),
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0) + amount,
        )
        return CashFlowResult(account=account, ledger=ledger, cash_available=self.repo.get_cash_available(account_id))

    def _active_account(self, account_id: int) -> PaperAccount:
        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE.value:
            raise ValueError(f"paper account is not active: {account_id}")
        return account

    @staticmethod
    def _positive_money(amount: Decimal) -> Decimal:
        amount = Decimal(amount).quantize(_MONEY)
        if amount <= 0:
            raise ValueError("cash flow amount must be positive")
        return amount

    @staticmethod
    def _current_nav(account: PaperAccount) -> Decimal:
        nav = Decimal(account.net_asset_value or 0).quantize(_NAV)
        if nav <= 0:
            raise ValueError("account NAV must be positive")
        return nav
```

- [ ] **Step 6: Add routes**

In `paper_trading/api/routers/accounts.py`, import `CashFlowRequest`, `CashFlowResponse`, and `CashService`, then add:

```python
def _cash_flow_response(result) -> CashFlowResponse:
    return CashFlowResponse(
        account_id=result.account.id,
        cash_available=result.cash_available,
        net_asset_value=result.account.net_asset_value,
        share_count=result.account.share_count,
        ledger=result.ledger,
    )


@router.post("/{account_id}/cash/deposit", response_model=CashFlowResponse)
def deposit_cash(account_id: int, request: CashFlowRequest, session: Session = Depends(get_session)):
    service = CashService(PaperTradingRepository(session))
    try:
        result = service.deposit(account_id, request.amount, request.trade_date, request.note)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return _cash_flow_response(result)


@router.post("/{account_id}/cash/withdraw", response_model=CashFlowResponse)
def withdraw_cash(account_id: int, request: CashFlowRequest, session: Session = Depends(get_session)):
    service = CashService(PaperTradingRepository(session))
    try:
        result = service.withdraw(account_id, request.amount, request.trade_date, request.note)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return _cash_flow_response(result)
```

- [ ] **Step 7: Run backend cash-flow tests**

Run: `uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add paper_trading/services/cash_service.py paper_trading/schemas/accounts.py paper_trading/api/routers/accounts.py test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py
git commit -m "feat(paper-trading): add cash flow API"
```

## Task 3: Make snapshots and analytics NAV-aware

**Files:**
- Modify: `paper_trading/schemas/snapshots.py`
- Modify: `paper_trading/schemas/analytics.py`
- Modify: `paper_trading/services/snapshot_service.py`
- Modify: `paper_trading/services/analytics_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/services/test_analytics_service.py`

**Interfaces:**
- Consumes: account NAV/share fields from Task 1 and cash-flow service from Task 2
- Produces: snapshot fields `net_asset_value`, `share_count`, `cumulative_deposit`, `cumulative_withdrawal`, `net_cash_flow`
- Produces: analytics overview fields `net_asset_value`, `share_count`, `simple_asset_return`

- [ ] **Step 1: Add failing snapshot test**

Add to `test/paper_trading/services/test_snapshot_service.py`:

```python
def test_generate_snapshot_persists_nav_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_nav.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("900.00"))
    storage = FakeHistoryStorage({"000001": pd.DataFrame({COL_STOCK_ID: ["000001"], COL_DATE: ["2026-06-16"], COL_OPEN: [9.0], COL_HIGH: [11.0], COL_LOW: [8.0], COL_CLOSE: [10.0]})})
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    snapshot = SnapshotService(repo, market_data).generate_snapshot(account.id, date(2026, 6, 16))

    assert snapshot.total_assets == Decimal("101000.0000")
    assert snapshot.share_count == Decimal("100000.000000")
    assert snapshot.net_asset_value == Decimal("1.010000")
    assert snapshot.cumulative_deposit == Decimal("100000.0000")
    assert snapshot.cumulative_withdrawal == Decimal("0.0000")
    assert snapshot.net_cash_flow == Decimal("100000.0000")
    assert account.net_asset_value == Decimal("1.010000")
    engine.dispose()
```

- [ ] **Step 2: Add failing analytics test**

Add to `test/paper_trading/services/test_analytics_service.py`:

```python
def test_analytics_uses_nav_return_not_total_assets_after_deposit(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("nav-return-demo", Decimal("100000.00"))
    repo.save_snapshot(account_id=account.id, trade_date=date(2026, 6, 16), cash_available=Decimal("100000.0000"), cash_frozen=Decimal("0"), market_value=Decimal("0"), total_assets=Decimal("100000.0000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), position_count=0, order_count=0, trade_count=0, net_asset_value=Decimal("1.000000"), share_count=Decimal("100000.000000"), cumulative_deposit=Decimal("100000.0000"), cumulative_withdrawal=Decimal("0.0000"), net_cash_flow=Decimal("100000.0000"))
    repo.save_snapshot(account_id=account.id, trade_date=date(2026, 6, 17), cash_available=Decimal("150000.0000"), cash_frozen=Decimal("0"), market_value=Decimal("0"), total_assets=Decimal("150000.0000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), position_count=0, order_count=0, trade_count=0, net_asset_value=Decimal("1.000000"), share_count=Decimal("150000.000000"), cumulative_deposit=Decimal("150000.0000"), cumulative_withdrawal=Decimal("0.0000"), net_cash_flow=Decimal("150000.0000"))

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("0.000000")
    assert analytics.overview.simple_asset_return.value == Decimal("0.500000")
    assert analytics.risk.max_drawdown.value == Decimal("0.000000")
    engine.dispose()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py -q`

Expected: fail because schemas/services are not NAV-aware.

- [ ] **Step 4: Extend schemas**

In `paper_trading/schemas/snapshots.py`, add:

```python
net_asset_value: Decimal | None = None
share_count: Decimal | None = None
cumulative_deposit: Decimal | None = None
cumulative_withdrawal: Decimal | None = None
net_cash_flow: Decimal | None = None
```

In `paper_trading/schemas/analytics.py`, change `OverviewAnalytics` to:

```python
class OverviewAnalytics(BaseModel):
    total_assets: Decimal | None = None
    cash_available: Decimal | None = None
    market_value: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    net_asset_value: Decimal | None = None
    share_count: Decimal | None = None
    total_return: MetricValue
    simple_asset_return: MetricValue | None = None
```

- [ ] **Step 5: Update snapshot generation**

In `paper_trading/services/snapshot_service.py`, after `total_assets` is computed, derive NAV fields and persist account state:

```python
account = self.repo.get_account(account_id)
if account is None:
    raise KeyError(f"paper account not found: {account_id}")
share_count = Decimal(account.share_count or 0).quantize(Decimal("0.000001"))
total_assets = (cash_available + cash_frozen + market_value).quantize(Decimal("0.0001"))
net_asset_value = None
if share_count > 0:
    net_asset_value = (total_assets / share_count).quantize(Decimal("0.000001"))
    self.repo.update_account_nav_state(
        account,
        share_count=share_count,
        net_asset_value=net_asset_value,
        cumulative_deposit=Decimal(account.cumulative_deposit or 0),
        cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0),
    )
snapshot = self.repo.save_snapshot(
    account_id=account_id,
    trade_date=trade_date,
    cash_available=cash_available,
    cash_frozen=cash_frozen,
    market_value=market_value.quantize(Decimal("0.0001")),
    total_assets=total_assets,
    realized_pnl=sum(
        (Decimal(position.realized_pnl or 0) for position in positions),
        Decimal("0"),
    ).quantize(Decimal("0.0001")),
    unrealized_pnl=unrealized_pnl.quantize(Decimal("0.0001")),
    position_count=len(active_positions),
    order_count=self.repo.count_orders(account_id, trade_date),
    trade_count=self.repo.count_trades(account_id, trade_date),
    net_asset_value=net_asset_value,
    share_count=share_count,
    cumulative_deposit=Decimal(account.cumulative_deposit or 0).quantize(Decimal("0.0001")),
    cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0).quantize(Decimal("0.0001")),
    net_cash_flow=(Decimal(account.cumulative_deposit or 0) - Decimal(account.cumulative_withdrawal or 0)).quantize(Decimal("0.0001")),
)
return snapshot
```

- [ ] **Step 6: Update analytics calculations**

In `paper_trading/services/analytics_service.py`, add helper functions and update `_overview()` and `_risk()`:

```python
def _snapshot_nav(self, snapshot: PaperAccountSnapshot, initial_cash: Decimal) -> Decimal | None:
    if snapshot.net_asset_value is not None:
        return Decimal(snapshot.net_asset_value).quantize(_QUANTIZE)
    if initial_cash and initial_cash > 0:
        return (Decimal(snapshot.total_assets) / initial_cash).quantize(_QUANTIZE)
    return None

def _nav_series(self, snapshots: list[PaperAccountSnapshot], initial_cash: Decimal) -> list[Decimal]:
    values = [self._snapshot_nav(snapshot, initial_cash) for snapshot in snapshots]
    return [value for value in values if value is not None]
```

Make `get_account_analytics()` pass `account.initial_cash` into `_risk()`:

```python
risk=self._risk(snapshots, account.initial_cash),
```

Use NAV in overview:

```python
first_nav = self._snapshot_nav(snapshots[0], initial_cash)
latest_nav = self._snapshot_nav(latest, initial_cash)
if first_nav is None or first_nav <= 0 or latest_nav is None:
    total_return = MetricValue(value=None, reason="invalid_nav")
else:
    total_return = MetricValue(value=((latest_nav - first_nav) / first_nav).quantize(_QUANTIZE))
simple_asset_return = MetricValue(value=None, reason="invalid_initial_cash")
if initial_cash and initial_cash > 0:
    simple_asset_return = MetricValue(value=((Decimal(latest.total_assets) - initial_cash) / initial_cash).quantize(_QUANTIZE))
```

Use the NAV values in `_risk()` instead of `total_assets`:

```python
def _risk(self, snapshots: list[PaperAccountSnapshot], initial_cash: Decimal) -> RiskAnalytics:
    navs = self._nav_series(snapshots, initial_cash)
    if len(navs) < 2:
        metric = MetricValue(value=None, reason="insufficient_data")
        return RiskAnalytics(
            max_drawdown=metric,
            current_drawdown=metric,
            sharpe=metric,
            sortino=metric,
            calmar=metric,
        )
    peak = navs[0]
    max_drawdown = Decimal("0")
    for nav in navs:
        if nav > peak:
            peak = nav
        drawdown = (nav - peak) / peak if peak else Decimal("0")
        max_drawdown = min(max_drawdown, drawdown)
    current_drawdown = ((navs[-1] - max(navs)) / max(navs)).quantize(_QUANTIZE) if max(navs) else Decimal("0.000000")
```

- [ ] **Step 7: Run analytics tests**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add paper_trading/schemas/snapshots.py paper_trading/schemas/analytics.py paper_trading/services/snapshot_service.py paper_trading/services/analytics_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py
git commit -m "feat(paper-trading): compute NAV analytics"
```

## Task 4: Add CLI deposit and withdrawal commands

**Files:**
- Modify: `tools/paper_trading_cli.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: backend endpoints from Task 2
- Produces: `PaperTradingApiClient.deposit_cash(account_id, amount, trade_date, note)`
- Produces: `PaperTradingApiClient.withdraw_cash(account_id, amount, trade_date, note)`

- [ ] **Step 1: Write failing CLI tests**

Add to `test/tools/test_paper_trading_cli.py`:

```python
def test_account_deposit_command_calls_client(capsys):
    client = _mock_client()
    client.deposit_cash.return_value = {"account_id": 1, "cash_available": "125000.0000", "net_asset_value": "1.000000", "share_count": "125000.000000", "ledger": {"id": 2, "event_type": "deposit", "amount": "25000.0000", "share_delta": "25000.000000"}}
    with patch("tools.paper_trading_cli.PaperTradingApiClient", return_value=client):
        code = main(["--token", "secret", "account", "deposit", "--account-id", "1", "--amount", "25000", "--trade-date", "2026-07-20", "--note", "add cash"])
    assert code == EXIT_CODES["OK"]
    client.deposit_cash.assert_called_once_with(1, Decimal("25000"), "2026-07-20", "add cash")
    assert "cash_available" in capsys.readouterr().out


def test_account_withdraw_command_calls_client():
    client = _mock_client()
    client.withdraw_cash.return_value = {"account_id": 1, "cash_available": "95000.0000", "net_asset_value": "1.000000", "share_count": "95000.000000", "ledger": {"id": 2, "event_type": "withdrawal", "amount": "-5000.0000", "share_delta": "-5000.000000"}}
    with patch("tools.paper_trading_cli.PaperTradingApiClient", return_value=client):
        code = main(["--token", "secret", "account", "withdraw", "--account-id", "1", "--amount", "5000", "--trade-date", "2026-07-20"])
    assert code == EXIT_CODES["OK"]
    client.withdraw_cash.assert_called_once_with(1, Decimal("5000"), "2026-07-20", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/tools/test_paper_trading_cli.py -q`

Expected: fail because commands and client methods do not exist.

- [ ] **Step 3: Add client methods and parsers**

In `tools/paper_trading_cli.py`, add methods:

```python
def deposit_cash(self, account_id: int, amount: Decimal, trade_date: str, note: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"amount": str(amount), "trade_date": trade_date}
    if note is not None:
        body["note"] = note
    return self._request("POST", f"/paper/accounts/{account_id}/cash/deposit", json=body)

def withdraw_cash(self, account_id: int, amount: Decimal, trade_date: str, note: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"amount": str(amount), "trade_date": trade_date}
    if note is not None:
        body["note"] = note
    return self._request("POST", f"/paper/accounts/{account_id}/cash/withdraw", json=body)
```

In `_add_account_subparsers`, add:

```python
p_deposit = acct_sub.add_parser("deposit", help="Deposit cash into an account")
p_deposit.add_argument("--account-id", type=int, required=True, help="Account ID")
p_deposit.add_argument("--amount", required=True, help="Positive cash amount")
p_deposit.add_argument("--trade-date", required=True, help="Effective date YYYY-MM-DD")
p_deposit.add_argument("--note", default=None, help="Optional note")
p_withdraw = acct_sub.add_parser("withdraw", help="Withdraw available cash from an account")
p_withdraw.add_argument("--account-id", type=int, required=True, help="Account ID")
p_withdraw.add_argument("--amount", required=True, help="Positive cash amount")
p_withdraw.add_argument("--trade-date", required=True, help="Effective date YYYY-MM-DD")
p_withdraw.add_argument("--note", default=None, help="Optional note")
```

- [ ] **Step 4: Wire command handling**

In account command handling, add:

```python
if args.account_command == "deposit":
    _validate_trade_date(args.trade_date)
    result = client.deposit_cash(args.account_id, _parse_decimal(args.amount, "amount"), args.trade_date, args.note)
    _print_result(result, as_json=args.json)
    return EXIT_CODES["OK"]
if args.account_command == "withdraw":
    _validate_trade_date(args.trade_date)
    result = client.withdraw_cash(args.account_id, _parse_decimal(args.amount, "amount"), args.trade_date, args.note)
    _print_result(result, as_json=args.json)
    return EXIT_CODES["OK"]
```

- [ ] **Step 5: Run CLI tests**

Run: `uv run pytest test/tools/test_paper_trading_cli.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/paper_trading_cli.py test/tools/test_paper_trading_cli.py
git commit -m "feat(paper-trading): add cash flow CLI"
```

## Task 5: Add frontend cash-flow client and account modal

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts`
- Modify: `frontend/paper-trading/lib/api-client.ts`
- Create: `frontend/paper-trading/features/accounts/cash-flow-modal.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx`
- Test: `frontend/paper-trading/lib/api-client.test.ts`
- Test: `frontend/paper-trading/features/accounts/cash-flow-modal.test.tsx`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`

**Interfaces:**
- Consumes: API endpoints from Task 2
- Produces: `depositCash(accountId, input)` and `withdrawCash(accountId, input)`
- Produces: `CashFlowModal` props `{ account, mode, open, cashAvailable, onClose, onCompleted }`

- [ ] **Step 1: Write failing API client tests**

Add to `frontend/paper-trading/lib/api-client.test.ts`:

```ts
import { depositCash, withdrawCash } from "./api-client";

it("posts deposit cash payloads", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ account_id: 7 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await depositCash(7, { amount: "10000", trade_date: "2026-07-20", note: "add cash" });
  expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/cash/deposit", expect.objectContaining({ method: "POST", body: JSON.stringify({ amount: "10000", trade_date: "2026-07-20", note: "add cash" }) }));
});

it("posts withdraw cash payloads", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ account_id: 7 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await withdrawCash(7, { amount: "5000", trade_date: "2026-07-20" });
  expect(fetchMock).toHaveBeenCalledWith("/api/paper/accounts/7/cash/withdraw", expect.objectContaining({ method: "POST", body: JSON.stringify({ amount: "5000", trade_date: "2026-07-20" }) }));
});
```

- [ ] **Step 2: Write failing modal tests**

Create `frontend/paper-trading/features/accounts/cash-flow-modal.test.tsx` with tests:

```tsx
it("submits a deposit", async () => {
  depositCashMock.mockResolvedValue({ account_id: 1, cash_available: "110000.0000", net_asset_value: "1.000000", share_count: "110000.000000", ledger: { id: 2, account_id: 1, event_type: "deposit", amount: "10000.0000", note: "add" } });
  render(<CashFlowModal account={demoAccount} cashAvailable="100000.0000" mode="deposit" open onClose={vi.fn()} onCompleted={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("Amount"), "10000");
  await userEvent.clear(screen.getByLabelText("Trade date"));
  await userEvent.type(screen.getByLabelText("Trade date"), "2026-07-20");
  await userEvent.type(screen.getByLabelText("Note"), "add");
  await userEvent.click(screen.getByRole("button", { name: "Deposit" }));
  expect(depositCashMock).toHaveBeenCalledWith(1, { amount: "10000", trade_date: "2026-07-20", note: "add" });
});

it("blocks withdrawal above available cash", async () => {
  render(<CashFlowModal account={demoAccount} cashAvailable="1000.0000" mode="withdraw" open onClose={vi.fn()} onCompleted={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("Amount"), "1001");
  await userEvent.click(screen.getByRole("button", { name: "Withdraw" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Amount cannot exceed available cash 1000.0000");
  expect(withdrawCashMock).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run frontend tests to verify they fail**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts features/accounts/cash-flow-modal.test.tsx features/accounts/accounts-page.test.tsx`

Expected: fail because helpers/modal do not exist.

- [ ] **Step 4: Add types and API helpers**

In `frontend/paper-trading/lib/types.ts`, add these properties to the existing types:

```ts
export type Account = {
  share_count: string;
  net_asset_value: string;
  cumulative_deposit: string;
  cumulative_withdrawal: string;
};

export type CashLedgerEntry = {
  id: number;
  account_id: number;
  event_type: string;
  amount: string;
  trade_date: string | null;
  net_asset_value: string | null;
  share_delta: string | null;
  note: string | null;
};

export type CashFlowInput = { amount: string; trade_date: string; note?: string };
export type CashFlowResult = { account_id: number; cash_available: string; net_asset_value: string; share_count: string; ledger: CashLedgerEntry };
```

In `frontend/paper-trading/lib/api-client.ts`, add:

```ts
export function depositCash(accountId: number, input: CashFlowInput): Promise<CashFlowResult> {
  return apiRequest<CashFlowResult>(`/accounts/${accountId}/cash/deposit`, { method: "POST", body: JSON.stringify(input) });
}

export function withdrawCash(accountId: number, input: CashFlowInput): Promise<CashFlowResult> {
  return apiRequest<CashFlowResult>(`/accounts/${accountId}/cash/withdraw`, { method: "POST", body: JSON.stringify(input) });
}
```

- [ ] **Step 5: Add `CashFlowModal`**

Create `frontend/paper-trading/features/accounts/cash-flow-modal.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ErrorBanner } from "@/components/error-banner";
import { depositCash, withdrawCash } from "@/lib/api-client";
import type { Account, CashFlowResult } from "@/lib/types";

type Props = { account: Account | null; cashAvailable: string; mode: "deposit" | "withdraw"; open: boolean; onClose: () => void; onCompleted: (result: CashFlowResult) => Promise<void> | void };

export function CashFlowModal({ account, cashAvailable, mode, open, onClose, onCompleted }: Props) {
  const [amount, setAmount] = useState("");
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (!open || !account) return null;
  const title = mode === "deposit" ? `Deposit cash for ${account.name}` : `Withdraw cash from ${account.name}`;
  const buttonLabel = mode === "deposit" ? "Deposit" : "Withdraw";
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const numericAmount = Number(amount);
    if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
      setError("Amount must be greater than 0");
      return;
    }
    if (mode === "withdraw" && numericAmount > Number(cashAvailable)) {
      setError(`Amount cannot exceed available cash ${cashAvailable}`);
      return;
    }
    setSubmitting(true);
    try {
      const payload = { amount, trade_date: tradeDate, ...(note.trim() ? { note: note.trim() } : {}) };
      const result = mode === "deposit" ? await depositCash(account.id, payload) : await withdrawCash(account.id, payload);
      await onCompleted(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${mode} cash`);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div className="modal-backdrop" role="presentation">
      <form aria-label={title} className="modal" onSubmit={onSubmit} role="dialog">
        <div className="panel__header"><h2>{title}</h2><button className="button button--secondary" onClick={onClose} type="button">Close</button></div>
        {mode === "withdraw" ? <p className="muted">Maximum withdrawable: {cashAvailable}</p> : null}
        {error ? <ErrorBanner message={error} /> : null}
        <label>Amount<input aria-label="Amount" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        <label>Trade date<input aria-label="Trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} /></label>
        <label>Note<textarea aria-label="Note" value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <button className="button" disabled={submitting} type="submit">{submitting ? "Submitting..." : buttonLabel}</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 6: Wire the modal into accounts page**

In `accounts-page.tsx`, add state:

```tsx
const [cashFlowMode, setCashFlowMode] = useState<"deposit" | "withdraw" | null>(null);
const cashAvailable = cashLedger.reduce((sum, entry) => sum + Number(entry.amount), 0).toFixed(4);
```

Add buttons near `Edit fees`:

```tsx
<button className="button button--secondary" onClick={() => setCashFlowMode("deposit")} type="button">Deposit</button>
<button className="button button--secondary" onClick={() => setCashFlowMode("withdraw")} type="button">Withdraw</button>
```

Render the modal:

```tsx
<CashFlowModal
  account={selectedAccount}
  cashAvailable={cashAvailable}
  mode={cashFlowMode ?? "deposit"}
  open={cashFlowMode !== null}
  onClose={() => setCashFlowMode(null)}
  onCompleted={async () => {
    await refreshAccounts();
    if (selectedAccountIdRef.current) {
      await loadAccountDetails(selectedAccountIdRef.current, true);
    }
  }}
/>
```

- [ ] **Step 7: Run frontend cash-flow tests**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts features/accounts/cash-flow-modal.test.tsx features/accounts/accounts-page.test.tsx`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/lib/api-client.ts frontend/paper-trading/features/accounts/cash-flow-modal.tsx frontend/paper-trading/features/accounts/accounts-page.tsx frontend/paper-trading/lib/api-client.test.ts frontend/paper-trading/features/accounts/cash-flow-modal.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx
git commit -m "feat(paper-trading): add cash flow account UI"
```

## Task 6: Update frontend ledger and analytics display

**Files:**
- Modify: `frontend/paper-trading/features/trading/trading-tables.tsx`
- Modify: `frontend/paper-trading/features/analytics/analytics-summary.tsx`
- Modify: `frontend/paper-trading/features/analytics/asset-chart.tsx`
- Modify: `frontend/paper-trading/lib/types.ts`
- Test: `frontend/paper-trading/features/analytics/analytics-page.test.tsx`
- Test: `frontend/paper-trading/features/trading/trading-tables.test.tsx` if it exists; otherwise add assertions through existing page tests that render `CashLedgerTable`.

**Interfaces:**
- Consumes: NAV-aware frontend types from Task 5 and analytics API fields from Task 3
- Produces: NAV-first analytics UI and cash-ledger NAV/share columns

- [ ] **Step 1: Add failing display tests**

In the most focused existing frontend test, add expectations equivalent to:

```tsx
expect(screen.getByText("NAV Return")).toBeInTheDocument();
expect(screen.getByText("Unit NAV")).toBeInTheDocument();
expect(screen.getByText("Share Count")).toBeInTheDocument();
expect(screen.getByText("1.050000")).toBeInTheDocument();
```

For cash ledger display, add a render assertion:

```tsx
render(<CashLedgerTable entries={[{ id: 1, account_id: 1, event_type: "withdrawal", amount: "-5000.0000", trade_date: "2026-07-20", net_asset_value: "1.250000", share_delta: "-4000.000000", note: "cash out" }]} />);
expect(screen.getByText("Withdrawal")).toBeInTheDocument();
expect(screen.getByText("1.250000")).toBeInTheDocument();
expect(screen.getByText("-4000.000000")).toBeInTheDocument();
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/paper-trading && npm run test -- features/analytics/analytics-page.test.tsx features/accounts/accounts-page.test.tsx`

Expected: fail because UI labels/fields are not present.

- [ ] **Step 3: Extend analytics types**

In `frontend/paper-trading/lib/types.ts`, add NAV fields by updating `OverviewAnalytics` and adding the listed properties to `Snapshot`:

```ts
export type OverviewAnalytics = {
  total_assets: string | null;
  cash_available: string | null;
  market_value: string | null;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  net_asset_value: string | null;
  share_count: string | null;
  total_return: MetricValue;
  simple_asset_return: MetricValue | null;
};

export type Snapshot = {
  net_asset_value: string | null;
  share_count: string | null;
  cumulative_deposit: string | null;
  cumulative_withdrawal: string | null;
  net_cash_flow: string | null;
};
```

- [ ] **Step 4: Update cash ledger table**

In `trading-tables.tsx`, add formatter and columns:

```tsx
const cashEventLabels: Record<string, string> = {
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  freeze: "Freeze",
  release: "Release",
  trade: "Trade",
  fee: "Fee"
};

{ key: "event", header: "Event", render: (row) => cashEventLabels[row.event_type] ?? row.event_type },
{ key: "date", header: "Date", render: (row) => row.trade_date ? formatDate(row.trade_date) : "-" },
{ key: "nav", header: "NAV", align: "right", render: (row) => row.net_asset_value ?? "-" },
{ key: "shares", header: "Share Delta", align: "right", render: (row) => row.share_delta ?? "-" },
```

- [ ] **Step 5: Update analytics summary and chart**

In `analytics-summary.tsx`, change cards:

```tsx
["Unit NAV", overview?.net_asset_value ?? snapshot?.net_asset_value ?? "-"],
["Share Count", overview?.share_count ?? snapshot?.share_count ?? "-"],
["NAV Return", <MetricValueText key="total-return" metric={overview?.total_return} percent />],
["Simple Asset Return", <MetricValueText key="simple-return" metric={overview?.simple_asset_return} percent />]
```

In `asset-chart.tsx`, use NAV values first:

```tsx
series.setData(
  snapshots.map((snapshot) => ({
    time: snapshot.trade_date,
    value: Number(snapshot.net_asset_value ?? snapshot.total_assets)
  }))
);
```

- [ ] **Step 6: Run frontend display tests**

Run: `cd frontend/paper-trading && npm run test -- features/analytics/analytics-page.test.tsx features/accounts/accounts-page.test.tsx`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/features/analytics/analytics-summary.tsx frontend/paper-trading/features/analytics/asset-chart.tsx frontend/paper-trading/features/analytics/analytics-page.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx
git commit -m "feat(paper-trading): show NAV analytics"
```

## Task 7: Update documentation and run focused verification

**Files:**
- Modify: `docs/paper_trading.md`
- Test/verify: backend focused pytest, frontend focused vitest, docs grep/read review

**Interfaces:**
- Consumes: all tasks above
- Produces: documented user workflow and verified integrated behavior

- [ ] **Step 1: Update docs**

In `docs/paper_trading.md`, add a section under account management with this content:

### Deposits and withdrawals

Paper trading accounts support external cash flows through account-scoped deposit and withdrawal operations. Deposits add available cash and mint account shares at the current unit NAV. Withdrawals reduce available cash and redeem account shares at the current unit NAV. Withdrawals cannot exceed available cash and do not automatically sell positions or use frozen cash.

Use these CLI commands:

```bash
uv run tools/paper_trading_cli.py account deposit --account-id 1 --amount 10000 --trade-date 2026-07-20 --note "add cash"
uv run tools/paper_trading_cli.py account withdraw --account-id 1 --amount 5000 --trade-date 2026-07-20 --note "withdraw cash"
```

The matching and snapshot flow treats cash flows as pre-market effective on their `trade_date`. A cash flow changes account scale and share count but does not by itself change unit NAV.

Add analytics wording:

```markdown
`total_return` now represents NAV return: latest unit NAV versus the first valid unit NAV. `simple_asset_return` is the old scale-sensitive reference metric based on total assets versus initial cash. Drawdown and risk-adjusted metrics use the NAV series so deposits and withdrawals do not appear as trading gains or losses.
```

- [ ] **Step 2: Run backend focused tests**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py test/tools/test_paper_trading_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd frontend/paper-trading && npm run test -- lib/api-client.test.ts features/accounts/cash-flow-modal.test.tsx features/accounts/accounts-page.test.tsx features/analytics/analytics-page.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run formatting/linting for touched Python files**

Run:

```bash
uv run ruff format storage/model/paper_trading.py paper_trading/domain/enums.py paper_trading/storage/repository.py paper_trading/services/cash_service.py paper_trading/services/snapshot_service.py paper_trading/services/analytics_service.py paper_trading/schemas/accounts.py paper_trading/schemas/snapshots.py paper_trading/schemas/analytics.py paper_trading/api/routers/accounts.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py test/tools/test_paper_trading_cli.py
uv run ruff check storage/model/paper_trading.py paper_trading/domain/enums.py paper_trading/storage/repository.py paper_trading/services/cash_service.py paper_trading/services/snapshot_service.py paper_trading/services/analytics_service.py paper_trading/schemas/accounts.py paper_trading/schemas/snapshots.py paper_trading/schemas/analytics.py paper_trading/api/routers/accounts.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_cash_service.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_analytics_service.py test/tools/test_paper_trading_cli.py
```

Expected: PASS.

- [ ] **Step 5: Commit docs and verification fixes**

```bash
git add docs/paper_trading.md
git commit -m "docs(paper-trading): document cash flow NAV model"
```

## Self-Review

- Spec coverage: Tasks cover storage model, immutable cash ledger rows, cash service/API, CLI, snapshot NAV, analytics NAV return and risk metrics, frontend account entry, frontend ledger display, frontend analytics display, docs, and focused verification.
- Placeholder scan: No unspecified implementation or test steps remain; each task includes concrete tests, files, commands, and expected outcomes.
- Type consistency: Backend uses `net_asset_value`, `share_count`, `cumulative_deposit`, `cumulative_withdrawal`, `net_cash_flow`, and `simple_asset_return` consistently across ORM, schemas, services, and frontend types.
