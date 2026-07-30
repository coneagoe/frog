# Paper Trading Delete Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend API that permanently deletes a paper trading account and all rows owned by that account.

**Architecture:** Keep the existing router → service → repository layering. The route exposes `DELETE /paper/accounts/{account_id}`, the service owns account deletion semantics, and the repository performs explicit child-to-parent deletes before deleting `PaperAccount`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy ORM, pytest, `uv run` for Python commands.

## Global Constraints

- Use `uv run` for Python commands in this repo.
- Do not add frontend UI in this change.
- Return `204 No Content` when deletion succeeds.
- Return `404 Not Found` when the account does not exist.
- Physically delete account-owned rows for cash ledger entries, orders, trades, positions, position lots, snapshots, and matching runs.
- Do not add a database migration or model-level cascade change.

---

## File Structure

- Modify `paper_trading/storage/repository.py`: add `delete_account(account_id: int) -> bool` and explicit delete queries.
- Modify `paper_trading/services/account_service.py`: add `delete_account(account_id: int) -> bool` as the account-level interface.
- Modify `paper_trading/api/routers/accounts.py`: add the `DELETE /paper/accounts/{account_id}` route with `204`/`404` behavior.
- Modify `test/paper_trading/services/test_account_service.py`: add service/repository deletion coverage.
- Modify `test/paper_trading/api/test_accounts_api.py`: add API deletion success and not-found coverage.

---

### Task 1: Repository And Service Deletion

**Files:**
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/account_service.py`
- Create if missing: `test/paper_trading/services/test_account_service.py`

**Interfaces:**
- Consumes: existing `PaperTradingRepository.create_account`, `get_account`, `list_cash_ledger`, `create_order`, `upsert_position`, `create_position_lot`, `save_snapshot`.
- Produces: `PaperTradingRepository.delete_account(account_id: int) -> bool` and `AccountService.delete_account(account_id: int) -> bool`.

- [ ] **Step 1: Write the failing service/repository test**

Create `test/paper_trading/services/test_account_service.py` if it does not exist, with this test:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.account_service import AccountService
from paper_trading.storage.models import (
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperMatchingRun,
    PaperOrder,
    PaperPosition,
    PaperPositionLot,
    PaperTrade,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo_and_service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    return engine, session, repo, AccountService(repo)


def test_delete_account_removes_account_owned_rows(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    trade = PaperTrade(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY.value,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.00"),
        fees=Decimal("5.00"),
        trade_date=date(2026, 6, 16),
    )
    session.add(trade)
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("1000.00"))
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("10.00"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("98995.00"),
        cash_frozen=Decimal("0.00"),
        market_value=Decimal("1000.00"),
        total_assets=Decimal("99995.00"),
        realized_pnl=Decimal("0.00"),
        unrealized_pnl=Decimal("0.00"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    session.add(PaperMatchingRun(trade_date=date(2026, 6, 16), account_id=account.id, status="completed"))
    session.commit()

    deleted = service.delete_account(account.id)
    session.commit()

    assert deleted is True
    assert repo.get_account(account.id) is None
    assert session.query(PaperCashLedger).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperTrade).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperOrder).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPosition).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPositionLot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperAccountSnapshot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperMatchingRun).filter_by(account_id=account.id).count() == 0
    engine.dispose()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest test/paper_trading/services/test_account_service.py::test_delete_account_removes_account_owned_rows -q
```

Expected: FAIL because `AccountService` does not have `delete_account`.

- [ ] **Step 3: Add minimal repository deletion implementation**

In `paper_trading/storage/repository.py`, add this method inside `PaperTradingRepository`:

```python
    def delete_account(self, account_id: int) -> bool:
        account = self.get_account(account_id)
        if account is None:
            return False

        self.session.query(PaperCashLedger).filter(PaperCashLedger.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperTrade).filter(PaperTrade.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperOrder).filter(PaperOrder.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperPositionLot).filter(PaperPositionLot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPosition).filter(PaperPosition.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperAccountSnapshot).filter(PaperAccountSnapshot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperMatchingRun).filter(PaperMatchingRun.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.delete(account)
        self.session.flush()
        return True
```

- [ ] **Step 4: Add minimal service method**

In `paper_trading/services/account_service.py`, add this method inside `AccountService`:

```python
    def delete_account(self, account_id: int) -> bool:
        return self.repo.delete_account(account_id)
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest test/paper_trading/services/test_account_service.py::test_delete_account_removes_account_owned_rows -q
```

Expected: PASS.

- [ ] **Step 6: Run adjacent service tests**

Run:

```bash
uv run pytest test/paper_trading/services/test_account_service.py test/paper_trading/services/test_order_service.py -q
```

Expected: PASS.

---

### Task 2: Delete Account API Route

**Files:**
- Modify: `paper_trading/api/routers/accounts.py`
- Create if missing: `test/paper_trading/api/test_accounts_api.py`

**Interfaces:**
- Consumes: `AccountService.delete_account(account_id: int) -> bool` from Task 1.
- Produces: `DELETE /paper/accounts/{account_id}` returning `204` on success and `404` when the account is missing.

- [ ] **Step 1: Write failing API tests**

Create `test/paper_trading/api/test_accounts_api.py` if it does not exist, with these tests:

```python
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from storage.model.base import Base


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app), {"Authorization": "Bearer secret"}


def test_delete_account_removes_account_from_list(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    account_response = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    )
    account_id = account_response.json()["id"]

    response = client.delete(f"/paper/accounts/{account_id}", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    list_response = client.get("/paper/accounts", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_missing_account_returns_404(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.delete("/paper/accounts/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"
```

- [ ] **Step 2: Run API tests and verify RED**

Run:

```bash
uv run pytest test/paper_trading/api/test_accounts_api.py -q
```

Expected: FAIL because `DELETE /paper/accounts/{account_id}` returns `405 Method Not Allowed` or `404 Not Found`.

- [ ] **Step 3: Add route implementation**

In `paper_trading/api/routers/accounts.py`, change the import and add the route:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
```

Add below `get_account` and above `list_positions`:

```python
@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    deleted = AccountService(repo).delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run API tests and verify GREEN**

Run:

```bash
uv run pytest test/paper_trading/api/test_accounts_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Run paper trading API tests**

Run:

```bash
uv run pytest test/paper_trading/api -q
```

Expected: PASS.

---

### Task 3: Documentation And Focused Verification

**Files:**
- Modify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: `DELETE /paper/accounts/{account_id}` from Task 2.
- Produces: user-facing backend documentation for deleting an account.

- [ ] **Step 1: Add delete account documentation**

In `docs/paper_trading.md`, add this section after the “Create Account” section:

```markdown
## Delete Account

Deleting an account permanently removes the paper account and its associated orders, trades, positions, position lots, snapshots, matching runs, and cash ledger entries.

```bash
curl -X DELETE http://localhost:8000/paper/accounts/1 \
  -H "Authorization: Bearer change-me"
```
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
uv run pytest test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run all paper trading tests**

Run:

```bash
uv run pytest test/paper_trading -q
```

Expected: PASS.

- [ ] **Step 4: Run lint for changed Python files**

Run:

```bash
uv run ruff check paper_trading/storage/repository.py paper_trading/services/account_service.py paper_trading/api/routers/accounts.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py
```

Expected: PASS.

---

## Self-Review

- Spec coverage: Tasks cover repository/service deletion, API `204`/`404` behavior, tests, and docs.
- Placeholder scan: No placeholder steps remain; each code/test step includes exact content and commands.
- Type consistency: The plan consistently uses `delete_account(account_id: int) -> bool` in repository and service, and `DELETE /paper/accounts/{account_id}` in the API.
