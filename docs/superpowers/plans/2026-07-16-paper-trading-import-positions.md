# Paper Trading Import Existing Positions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a new paper trading account import pre-existing stock holdings without changing cash or creating trades.

**Architecture:** Add a new JSON API for importing holdings, a matching CLI command that reads CSV and posts JSON, and service/repository logic that seeds positions and lots atomically. Imported holdings are treated as already-owned inventory: they create positions and lots only, preserve cash, and remain sellable on later trade dates through required historical lot dates.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, pytest, uv, Ruff.

## Global Constraints

- `initial_cash` remains independent of imported holdings and must not change during import.
- Imported holdings must not create trades, orders, round trips, or cash ledger entries.
- Imported holdings must seed `PaperPosition` and `PaperPositionLot` rows atomically.
- Imported lots must carry a real `buy_trade_date` so later sells satisfy existing T+1 validation.
- First version should reject imports into any account that already has positions or lots.
- Use `uv run` for Python commands in this repo.

---

### Task 1: Add import-positions API and CLI

**Files:**
- Modify: `paper_trading/schemas/accounts.py`
- Modify: `paper_trading/services/account_service.py`
- Modify: `paper_trading/api/routers/accounts.py`
- Modify: `tools/paper_trading_cli.py`
- Test: `test/paper_trading/schemas/test_accounts.py`
- Test: `test/paper_trading/services/test_account_service.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: `PaperTradingRepository.create_position_lot()`, `PaperTradingRepository.upsert_position()`, `PaperTradingRepository.get_positions()`, `PaperTradingRepository.get_lots()`
- Produces: `AccountService.import_positions(account_id: int, positions: list[ImportPositionItem])`, `POST /paper/accounts/{account_id}/positions/import`, `PaperTradingApiClient.import_positions(...)`, and `account import-positions --account-id ID --file holdings.csv`

- [ ] **Step 1: Write the failing tests**

Add tests that prove: the new request schema validates items, the service seeds positions/lots without changing cash or creating trades, the API returns 404/422 correctly, and the CLI reads a CSV file and posts the parsed rows.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:
`uv run pytest test/paper_trading/schemas/test_accounts.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py test/tools/test_paper_trading_cli.py -k import_positions -v`

Expected: failures because the import endpoint, service method, schema, and CLI command do not exist yet.

- [ ] **Step 3: Implement the minimal code**

Add these definitions:

```python
class ImportPositionItem(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    cost_price: Decimal = Field(ge=0)
    buy_trade_date: date


class ImportPositionsRequest(BaseModel):
    positions: list[ImportPositionItem]
```

```python
def import_positions(self, account_id: int, positions: list[ImportPositionItem]) -> None:
    if self.repo.get_account(account_id) is None:
        raise ValueError(f"paper account not found: {account_id}")
    if self.repo.get_positions(account_id):
        raise ValueError("account already has positions")
    for item in positions:
        self.repo.create_position_lot(
            account_id=account_id,
            symbol=item.symbol,
            buy_trade_date=item.buy_trade_date,
            original_quantity=item.quantity,
            remaining_quantity=item.quantity,
            cost_price=item.cost_price,
        )
        self.repo.upsert_position(
            account_id=account_id,
            symbol=item.symbol,
            total_quantity=item.quantity,
            frozen_quantity=0,
            cost_amount=item.cost_price * item.quantity,
            realized_pnl=Decimal("0"),
        )
```

```python
@router.post("/{account_id}/positions/import", response_model=ImportPositionsResponse)
def import_positions(account_id: int, request: ImportPositionsRequest, session: Session = Depends(get_session)):
    ...
```

```python
def import_positions(self, account_id: int, positions: list[dict[str, Any]]) -> dict[str, Any]:
    return self._request("POST", f"/paper/accounts/{account_id}/positions/import", json={"positions": positions})
```

```python
p_import = acct_sub.add_parser("import-positions", help="Import existing holdings")
p_import.add_argument("--account-id", type=int, required=True)
p_import.add_argument("--file", required=True)
```

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run the same `uv run pytest ... -k import_positions -v` command.

Expected: all import-position tests pass.

- [ ] **Step 5: Add/adjust CLI and API docs if needed**

Update `docs/paper_trading.md` to describe the new import flow and the CSV columns if the implementation introduces user-facing behavior that is not already documented.
