# Paper Trading Order Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add order deletion for paper trading and rebuild account-derived state so cash, trades, positions, snapshots, and related records remain consistent.

**Architecture:** Add a service-level delete operation that owns transaction-safe orchestration: load the order, delete it, clear derived account state, and replay surviving orders in deterministic order. Keep backend rebuild logic behind repository/service methods; the frontend only calls a delete API and refreshes visible data.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy ORM, pytest, Ruff, Next.js/React, TypeScript, Vitest/Testing Library patterns already used under `frontend/paper-trading`.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3`.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA.
- Storage table list is unchanged; no `tools/db_common.sh` update is required.
- Add `source` marker columns to `paper_positions` and `paper_position_lots`; default existing rows to `trade`.
- Preserve user changes in the working tree and do not revert unrelated edits.
- Delete means hard-delete the order and rebuild the entire account history from surviving orders.
- Preserve account row, fee settings, initial cash ledger entry, imported starting positions/lots, and surviving order status semantics.

---

## File Structure

- Modify `storage/model/paper_trading.py`: add position and lot source marker columns.
- Modify `paper_trading/storage/repository.py`: add low-level helpers for order deletion, clearing derived account data, listing replayable orders, and preserving initial/imported state.
- Modify `paper_trading/services/account_service.py`: mark imported positions/lots with `source=\"imported\"`.
- Modify `paper_trading/services/matching_service.py`: mark matching-generated positions/lots with `source=\"trade\"`.
- Create `paper_trading/services/order_delete_service.py`: orchestrate delete-and-rebuild with `MatchingService`, `SnapshotService`, and `RoundTripService`.
- Modify `paper_trading/api/routers/orders.py`: expose `DELETE /paper/orders/{order_id}`.
- Modify `tools/paper_trading_cli.py`: add `order delete --order-id` wrapper.
- Modify `frontend/paper-trading/lib/api-client.ts`: add `deleteOrder(orderId)`.
- Modify `frontend/paper-trading/features/trading/trading-tables.tsx`: add optional delete action props and pending-state support.
- Modify `frontend/paper-trading/features/history/orders-page.tsx`: wire confirmation, delete call, error handling, and refresh.
- Test `test/paper_trading/storage/test_repository.py`: repository cleanup primitives.
- Test `test/paper_trading/services/test_order_delete_service.py`: full delete/rebuild behavior.
- Test `test/paper_trading/api/test_orders_api.py` or existing order API test file: route status codes.
- Test `test/tools/test_paper_trading_cli.py`: CLI command parsing/client call.
- Test `frontend/paper-trading/features/history/orders-page.test.tsx`: UI delete flow.
- Update `docs/paper_trading.md`: API and CLI usage.

---

### Task 1: Repository Delete And Rebuild Primitives

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `paper_trading/services/account_service.py`
- Modify: `paper_trading/services/matching_service.py`
- Modify: `paper_trading/storage/repository.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces: `PaperTradingRepository.delete_order(order_id: int) -> PaperOrder | None`
- Produces: `PaperTradingRepository.clear_account_rebuild_state(account_id: int) -> None`
- Produces: `PaperTradingRepository.reset_orders_for_replay(account_id: int) -> None`
- Produces: `PaperTradingRepository.list_order_trade_dates(account_id: int) -> list[date]`
- Produces: `PaperTradingRepository.upsert_position(..., source: str = "trade") -> PaperPosition`
- Produces: `PaperTradingRepository.create_position_lot(..., source: str = "trade") -> PaperPositionLot`

- [ ] **Step 1: Write failing repository tests**

Add focused tests to `test/paper_trading/storage/test_repository.py` using the existing session/repository fixtures in that file. If fixture names differ, keep the assertions exactly equivalent and adapt only setup names.

```python
def test_delete_order_returns_deleted_order_and_removes_row(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )

    deleted = repo.delete_order(order.id)

    assert deleted is not None
    assert deleted.id == order.id
    with pytest.raises(KeyError):
        repo.get_order(order.id)


def test_clear_account_rebuild_state_preserves_initial_cash(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.FILLED,
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.0000"),
        Decimal("5.0000"),
        date(2026, 7, 19),
    )
    repo.add_cash_event(account.id, CashEventType.TRADE, Decimal("-1005.0000"), order_id=order.id, trade_id=trade.id)
    repo.upsert_position(account.id, "000001", total_quantity=100, frozen_quantity=0, cost_amount=Decimal("1005.0000"), source="trade")
    repo.create_position_lot(account.id, "000001", date(2026, 7, 19), 100, 100, Decimal("10.00"), source="trade")
    repo.upsert_position(account.id, "000002", total_quantity=200, frozen_quantity=0, cost_amount=Decimal("1800.0000"), source="imported")
    repo.create_position_lot(account.id, "000002", date(2026, 7, 1), 200, 200, Decimal("9.00"), source="imported")
    repo.save_snapshot(account.id, date(2026, 7, 19), Decimal("98995"), Decimal("0"), Decimal("1000"), Decimal("99995"), Decimal("0"), Decimal("0"), 1, 1, 1)

    repo.clear_account_rebuild_state(account.id)

    assert repo.list_trades(account.id) == []
    positions = repo.get_positions(account.id)
    assert [(position.symbol, position.source) for position in positions] == [("000002", "imported")]
    assert repo.count_position_lots(account.id) == 1
    assert repo.list_snapshots(account.id) == []
    ledger = repo.list_cash_ledger(account.id)
    assert len(ledger) == 1
    assert ledger[0].note == "initial_cash"
    assert Decimal(ledger[0].amount) == Decimal("100000.0000")
```

- [ ] **Step 2: Run repository tests and verify failure**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py -q
```

Expected: FAIL because the new repository methods do not exist.

- [ ] **Step 3: Implement repository methods**

In `paper_trading/storage/repository.py`, add imports and methods inside `PaperTradingRepository`.

```python
    def delete_order(self, order_id: int) -> PaperOrder | None:
        order = cast(PaperOrder | None, self.session.get(PaperOrder, order_id))
        if order is None:
            return None
        self.session.delete(order)
        return order

    def clear_account_rebuild_state(self, account_id: int) -> None:
        self.session.query(PaperTradeValidityCheck).filter(PaperTradeValidityCheck.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperCashLedger).filter(
            PaperCashLedger.account_id == account_id,
            PaperCashLedger.note != "initial_cash",
        ).delete(synchronize_session=False)
        self.session.query(PaperPositionRoundTrip).filter(PaperPositionRoundTrip.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperTrade).filter(PaperTrade.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperAccountSnapshot).filter(PaperAccountSnapshot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperMatchingRun).filter(PaperMatchingRun.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPositionLot).filter(
            PaperPositionLot.account_id == account_id,
            PaperPositionLot.source == "trade",
        ).delete(synchronize_session=False)
        self.session.query(PaperPositionLot).filter(
            PaperPositionLot.account_id == account_id,
            PaperPositionLot.source == "imported",
        ).update({PaperPositionLot.remaining_quantity: PaperPositionLot.original_quantity}, synchronize_session=False)
        self.session.query(PaperPosition).filter(PaperPosition.account_id == account_id).delete(synchronize_session=False)
        # Rebuild imported aggregate positions from imported lots here.
        self.session.flush()

    def reset_orders_for_replay(self, account_id: int) -> None:
        self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.status.in_(
                [
                    OrderStatus.ACCEPTED.value,
                    OrderStatus.FILLED.value,
                    OrderStatus.PARTIALLY_FILLED.value,
                    OrderStatus.NEW.value,
                ]
            ),
        ).update(
            {
                PaperOrder.status: OrderStatus.ACCEPTED.value,
                PaperOrder.filled_quantity: 0,
                PaperOrder.rejection_code: None,
                PaperOrder.rejection_reason: None,
            },
            synchronize_session=False,
        )
        self.session.flush()

    def list_order_trade_dates(self, account_id: int) -> list[date]:
        rows = (
            self.session.query(PaperOrder.trade_date)
            .filter(PaperOrder.account_id == account_id)
            .distinct()
            .order_by(PaperOrder.trade_date.asc())
            .all()
        )
        return [row[0] for row in rows]
```

Add `source` columns to the `PaperPosition` and `PaperPositionLot` models. Update `upsert_position()` and `create_position_lot()` signatures to accept `source: str = "trade"`, and assign it to the ORM rows. Update `AccountService.import_positions()` to pass `source="imported"` for imported lots and aggregate positions. Keep `MatchingService` on the default `trade` source.

`clear_account_rebuild_state()` must delete trade lots, reset imported lots to `remaining_quantity = original_quantity`, delete all aggregate positions, and rebuild imported aggregate positions from imported lots. Task 2 must load the target order, clear dependent derived rows, then call `delete_order()` before replay. Do not call `delete_order()` before clearing dependencies, because any later query can trigger SQLAlchemy autoflush while `paper_trades.order_id` or `paper_trade_validity_checks.order_id` still reference the order.

Canceled and rejected orders must keep their original status and must not be reset to accepted during replay.

- [ ] **Step 4: Run repository tests and verify pass**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 2: Order Delete Service With Account Replay

**Files:**
- Create: `paper_trading/services/order_delete_service.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`

**Interfaces:**
- Consumes: repository methods from Task 1.
- Produces: `OrderDeleteService.delete_order(order_id: int) -> bool`

- [ ] **Step 1: Write failing service tests**

Create `test/paper_trading/services/test_order_delete_service.py`. Use existing fake market data patterns from `test/paper_trading/services/test_matching_service.py`.

```python
from datetime import date
from decimal import Decimal

import pytest

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.repository import PaperTradingRepository
from test.paper_trading.fakes import FakeMarketDataProvider


def test_delete_missing_order_returns_false(session):
    repo = PaperTradingRepository(session)
    service = OrderDeleteService(repo, FakeMarketDataProvider())

    assert service.delete_order(999999) is False


def test_delete_filled_order_rebuilds_account_from_remaining_orders(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))
    first = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    second = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    snapshot_service = SnapshotService(repo, market_data)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 17), account.id)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 2

    deleted = OrderDeleteService(repo, market_data).delete_order(first.id)

    assert deleted is True
    with pytest.raises(KeyError):
        repo.get_order(first.id)
    remaining_orders = repo.list_orders(account.id)
    assert [order.id for order in remaining_orders] == [second.id]
    trades = repo.list_trades(account.id)
    assert len(trades) == 1
    assert trades[0].order_id == second.id
    positions = repo.get_positions(account.id)
    assert [(position.symbol, int(position.total_quantity)) for position in positions] == [("000002", 100)]
    assert all(snapshot.trade_date >= date(2026, 7, 18) for snapshot in repo.list_snapshots(account.id))
    ledger = repo.list_cash_ledger(account.id)
    assert ledger[0].note == "initial_cash"
    assert repo.get_cash_available(account.id) < Decimal("100000")
```

- [ ] **Step 2: Run service tests and verify failure**

Run:

```bash
uv run pytest test/paper_trading/services/test_order_delete_service.py -q
```

Expected: FAIL because `paper_trading.services.order_delete_service` does not exist.

- [ ] **Step 3: Implement service**

Create `paper_trading/services/order_delete_service.py`.

```python
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository


class OrderDeleteService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def delete_order(self, order_id: int) -> bool:
        try:
            order = self.repo.get_order(order_id)
        except KeyError:
            return False

        account_id = order.account_id
        self.repo.clear_account_rebuild_state(account_id)
        deleted = self.repo.delete_order(order_id)
        if deleted is None:
            return False
        self.repo.reset_orders_for_replay(account_id)

        snapshot_service = SnapshotService(self.repo, self.market_data)
        matching_service = MatchingService(self.repo, self.market_data, snapshot_service)
        for trade_date in self.repo.list_order_trade_dates(account_id):
            matching_service.run(trade_date, account_id)
        RoundTripService(self.repo).rebuild_account(account_id)
        return True
```

- [ ] **Step 4: Run service tests and focused matching tests**

Run:

```bash
uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_matching_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 3: Backend Delete API

**Files:**
- Modify: `paper_trading/api/routers/orders.py`
- Test: existing order API test file under `test/paper_trading/api/`, or create `test/paper_trading/api/test_order_delete_api.py`

**Interfaces:**
- Consumes: `OrderDeleteService.delete_order(order_id: int) -> bool`
- Produces: `DELETE /paper/orders/{order_id}` returning `204` or `404`.

- [ ] **Step 1: Write failing API tests**

Add route tests matching current API test client fixtures. The assertions must verify status codes, not implementation details.

```python
def test_delete_order_returns_204(client, auth_headers, session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    session.commit()

    response = client.delete(f"/paper/orders/{order.id}", headers=auth_headers)

    assert response.status_code == 204


def test_delete_missing_order_returns_404(client, auth_headers):
    response = client.delete("/paper/orders/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "paper order not found: 999999"
```

- [ ] **Step 2: Run API tests and verify failure**

Run the exact API test file selected in Step 1:

```bash
uv run pytest test/paper_trading/api/test_order_delete_api.py -q
```

Expected: FAIL with 405 or missing route.

- [ ] **Step 3: Implement API route**

Modify `paper_trading/api/routers/orders.py` imports and add the route near `cancel_order`.

```python
from fastapi import APIRouter, Depends, HTTPException, Response, status
from paper_trading.services.order_delete_service import OrderDeleteService
```

```python
@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    repo = PaperTradingRepository(session)
    deleted = OrderDeleteService(repo, market_data).delete_order(order_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper order not found: {order_id}")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run backend focused tests**

Run:

```bash
uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_order_delete_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 4: CLI Order Delete Command

**Files:**
- Modify: `tools/paper_trading_cli.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Produces: `PaperTradingApiClient.delete_order(order_id: int) -> None`
- Produces: CLI command `order delete --order-id 123`

- [ ] **Step 1: Write failing CLI tests**

Add tests near existing order command tests in `test/tools/test_paper_trading_cli.py`.

```python
def test_delete_order_calls_client(self):
    client = make_client()

    result = main(["order", "delete", "--order-id", "123"], client=client)

    assert result == 0
    client.delete_order.assert_called_once_with(order_id=123)


def test_delete_order_missing_order_id(self):
    client = make_client()

    result = main(["order", "delete"], client=client)

    assert result == EXIT_CODES["usage"]
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
uv run pytest test/tools/test_paper_trading_cli.py -q
```

Expected: FAIL because `delete_order` and parser subcommand do not exist.

- [ ] **Step 3: Implement CLI client and parser**

In `tools/paper_trading_cli.py`, add to `PaperTradingApiClient`:

```python
    def delete_order(self, order_id: int) -> None:
        self._request("DELETE", f"/paper/orders/{order_id}")
```

In the order subparser setup, add:

```python
    p_delete = order_sub.add_parser("delete", help="Delete an order and rebuild account history")
    p_delete.add_argument("--order-id", type=int, required=True)
```

In `_handle_order`, add:

```python
    if args.order_command == "delete":
        client.delete_order(order_id=args.order_id)
        return {"deleted": True, "order_id": args.order_id}
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest test/tools/test_paper_trading_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 5: Frontend API Client And Order Table Action

**Files:**
- Modify: `frontend/paper-trading/lib/api-client.ts`
- Modify: `frontend/paper-trading/features/trading/trading-tables.tsx`
- Test: existing table tests if present, otherwise covered by Task 6 page tests.

**Interfaces:**
- Produces: `deleteOrder(orderId: number): Promise<void>`
- Produces: optional `OrderTable` props `onDelete?: (orderId: number) => void` and `deletingOrderId?: number | null`

- [ ] **Step 1: Add frontend API client function**

Modify `frontend/paper-trading/lib/api-client.ts`.

```ts
export function deleteOrder(orderId: number): Promise<void> {
  return apiRequest<void>(`/orders/${orderId}`, { method: "DELETE" });
}
```

- [ ] **Step 2: Add OrderTable delete props**

Modify the `OrderTable` signature in `frontend/paper-trading/features/trading/trading-tables.tsx`.

```tsx
export function OrderTable({
  orders,
  onCancel,
  onDelete,
  deletingOrderId,
  editingOrderId,
  editingValue,
  onEditStart,
  onEditValueChange,
  onEditSave,
  onEditCancel
}: {
  orders: Order[];
  onCancel: (orderId: number) => void;
  onDelete?: (orderId: number) => void;
  deletingOrderId?: number | null;
  editingOrderId?: number | null;
  editingValue?: string;
  onEditStart?: (orderId: number) => void;
  onEditValueChange?: (value: string) => void;
  onEditSave?: (orderId: number) => void;
  onEditCancel?: () => void;
}) {
```

- [ ] **Step 3: Render Delete button**

In the `action` column render block, add this after the Edit button.

```tsx
            {onDelete ? (
              <button
                className="button button--danger"
                disabled={deletingOrderId === row.id}
                onClick={() => onDelete(row.id)}
                type="button"
              >
                {deletingOrderId === row.id ? "Deleting..." : "Delete"}
              </button>
            ) : null}
```

If `button--danger` does not exist in the frontend styles, use `button button--secondary` instead and do not introduce new styling in this task.

- [ ] **Step 4: Run frontend type/lint focused check**

Inspect `frontend/paper-trading/package.json` and run the narrowest available frontend check, for example:

```bash
npm --prefix frontend/paper-trading run lint
```

Expected: PASS. If this repo uses a different package manager script, use the script already documented in that package.

- [ ] **Step 5: Commit Task 5**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 6: Frontend Orders Page Delete Flow

**Files:**
- Modify: `frontend/paper-trading/features/history/orders-page.tsx`
- Test: `frontend/paper-trading/features/history/orders-page.test.tsx`

**Interfaces:**
- Consumes: `deleteOrder(orderId: number): Promise<void>` from Task 5.
- Consumes: `OrderTable` delete props from Task 5.

- [ ] **Step 1: Write failing page tests**

Add tests to `frontend/paper-trading/features/history/orders-page.test.tsx` near existing cancel/comment tests.

```tsx
it("does not delete an order when confirmation is cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);

  render(<OrdersPage />);

  await screen.findByText("AAPL");
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));

  expect(deleteOrderMock).not.toHaveBeenCalled();
});

it("deletes an order and reloads orders after confirmation", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteOrderMock.mockResolvedValue(undefined);

  render(<OrdersPage />);

  await screen.findByText("AAPL");
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));

  expect(deleteOrderMock).toHaveBeenCalledWith(1);
  await waitFor(() => expect(listOrdersMock).toHaveBeenCalledTimes(2));
});

it("shows an error when deleting an order fails", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteOrderMock.mockRejectedValue(new Error("Failed to delete order"));

  render(<OrdersPage />);

  await screen.findByText("AAPL");
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Failed to delete order");
});
```

Also extend the API client mock at the top of the test file:

```tsx
const deleteOrderMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  cancelOrder: cancelOrderMock,
  deleteOrder: deleteOrderMock,
  listAccounts: listAccountsMock,
  listOrders: listOrdersMock,
  updateOrderComment: updateOrderCommentMock
}));
```

- [ ] **Step 2: Run page tests and verify failure**

Run the frontend test command used by the package for this file, for example:

```bash
npm --prefix frontend/paper-trading test -- orders-page.test.tsx
```

Expected: FAIL because delete flow is not wired.

- [ ] **Step 3: Implement OrdersPage delete flow**

Modify imports and state in `frontend/paper-trading/features/history/orders-page.tsx`.

```tsx
import { cancelOrder, deleteOrder, listAccounts, listOrders, updateOrderComment } from "@/lib/api-client";
```

```tsx
  const [deletingOrderId, setDeletingOrderId] = useState<number | null>(null);
```

Add handler:

```tsx
  async function handleDelete(orderId: number) {
    const confirmed = window.confirm(
      "Delete this order? Filled trades, cash ledger, positions, and snapshots for this paper account will be recalculated."
    );
    if (!confirmed) return;

    const requestId = ++requestIdRef.current;
    setDeletingOrderId(orderId);
    setError(null);
    try {
      await deleteOrder(orderId);
      if (requestId === requestIdRef.current && selectedAccountId) {
        await loadOrders(selectedAccountId);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "Failed to delete order");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setDeletingOrderId(null);
      }
    }
  }
```

Pass props to `OrderTable`:

```tsx
        onDelete={handleDelete}
        deletingOrderId={deletingOrderId}
```

- [ ] **Step 4: Run page tests**

Run:

```bash
npm --prefix frontend/paper-trading test -- orders-page.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

Only commit if the user explicitly requested commits. Otherwise skip this step and leave changes unstaged.

---

### Task 7: Documentation And Focused Verification

**Files:**
- Modify: `docs/paper_trading.md`

**Interfaces:**
- Documents: `DELETE /paper/orders/{order_id}`
- Documents: `uv run tools/paper_trading_cli.py order delete --order-id 123`

- [ ] **Step 1: Update docs**

Add a short section to `docs/paper_trading.md` near order management docs.

```markdown
### Delete an order

Deleting an order hard-deletes the order. If the order had already filled, the paper trading backend recalculates the account's trades, cash ledger, positions, position lots, round trips, matching runs, validity checks, and snapshots from the remaining order history.

```bash
uv run tools/paper_trading_cli.py order delete --order-id 123
```

Raw API:

```bash
curl -X DELETE "$PAPER_TRADING_API_BASE_URL/paper/orders/123" \
  -H "Authorization: Bearer $PAPER_TRADING_API_TOKEN"
```
```

- [ ] **Step 2: Run backend focused verification**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_order_delete_api.py test/tools/test_paper_trading_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused verification**

Run the package's available focused checks, for example:

```bash
npm --prefix frontend/paper-trading test -- orders-page.test.tsx
npm --prefix frontend/paper-trading run lint
```

Expected: PASS.

- [ ] **Step 4: Run formatting/lint for changed Python files**

Run:

```bash
uv run ruff format paper_trading/storage/repository.py paper_trading/services/order_delete_service.py paper_trading/api/routers/orders.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_order_delete_api.py test/tools/test_paper_trading_cli.py
uv run ruff check paper_trading/storage/repository.py paper_trading/services/order_delete_service.py paper_trading/api/routers/orders.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_order_delete_api.py test/tools/test_paper_trading_cli.py
```

Expected: PASS.

- [ ] **Step 5: Final git inspection**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended paper trading delete files changed.

---

## Self-Review

- Spec coverage: backend API, rebuild semantics, frontend delete flow, CLI, tests, and docs are covered by Tasks 1-7.
- Placeholder scan: no TBD/TODO placeholders remain; steps include concrete code or exact verification commands.
- Type consistency: `OrderDeleteService.delete_order(order_id: int) -> bool`, `PaperTradingRepository.delete_order(order_id: int) -> PaperOrder | None`, and frontend `deleteOrder(orderId: number): Promise<void>` are consistent across tasks.
