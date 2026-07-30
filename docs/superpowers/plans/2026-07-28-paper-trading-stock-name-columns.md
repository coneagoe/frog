# Paper Trading Stock Name Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return and display human-readable stock names next to tickers in paper-trading positions, orders, and trades.

**Architecture:** A read-only batch metadata provider resolves names by persisted `(market, symbol)` without changing paper-trading storage. The three list routes materialize Pydantic rows and enrich them through one helper; shared frontend tables render the nullable field in an adjacent bounded `Stock` column.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, pytest, Next.js, TypeScript, React Testing Library, Vitest, CSS.

## Global Constraints

- Preserve paper-trading persistence, repository queries, matching, accounting, and import behavior.
- `stock_name` is nullable and display-only. Never infer a market or use a symbol as a name fallback.
- A-share resolves through `AStockBasic.股票名称`; HK Connect resolves through `GeneralInfoGGT.股票名称`.
- Missing metadata, unavailable sources, and unsupported markets return `null` without failing a list request.
- Batch by market; do not issue one metadata query per row.
- Insert `Stock` immediately after `Symbol`, preserve identifiers, number alignment, and horizontal mobile scrolling.
- Use `uv run` for Python commands.
- Do not change analytics or other unrequested ticker surfaces.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `paper_trading/storage/security_metadata.py` | Resolve names in batches from market-specific metadata tables. |
| `paper_trading/api/response_enrichment.py` | Materialize response models and overlay stock names. |
| `paper_trading/api/deps.py` | Provider dependency factory. |
| `paper_trading/schemas/accounts.py` | Position response contract. |
| `paper_trading/schemas/orders.py` | Order and trade response contracts. |
| `paper_trading/api/routers/accounts.py` | Enrich the positions list route. |
| `paper_trading/api/routers/orders.py` | Enrich order and trade list routes. |
| `test/paper_trading/storage/test_security_metadata.py` | Provider tests. |
| `test/paper_trading/api/test_accounts_api.py` | Positions API tests. |
| `test/paper_trading/api/test_orders_api.py` | Orders/trades API tests. |
| `frontend/paper-trading/lib/types.ts` | Matching nullable frontend contracts. |
| `frontend/paper-trading/features/trading/trading-tables.tsx` | Shared `Stock` column renderers. |
| `frontend/paper-trading/features/trading/trading-tables.test.tsx` | Table behavior tests. |
| `frontend/paper-trading/app/globals.css` | Ellipsis and bounded name-cell styles. |
| `docs/paper_trading.md` | List response documentation. |

### Task 1: Add Batched Security Name Resolution

**Files:**
- Create: `paper_trading/storage/security_metadata.py`
- Create: `test/paper_trading/storage/test_security_metadata.py`
- Modify: `paper_trading/api/deps.py:84-92`

**Interfaces:**
- Produces: `SecurityNameProvider(session: Session)` with `resolve_names(securities: Collection[tuple[str, str]]) -> dict[tuple[str, str], str]`.
- Produces: `get_security_name_provider(session: Session = Depends(get_session)) -> SecurityNameProvider`.

- [ ] **Step 1: Write failing provider tests**

```python
def test_resolve_names_reads_a_share_and_hk_metadata(sqlite_session):
    sqlite_session.add_all([
        AStockBasic(股票代码="000001", 股票名称="Ping An Bank"),
        GeneralInfoGGT(股票代码="00700", 股票名称="Tencent Holdings"),
    ])
    sqlite_session.commit()

    result = SecurityNameProvider(sqlite_session).resolve_names({
        ("a_share", "000001"),
        ("hk_connect", "00700"),
    })

    assert result == {
        ("a_share", "000001"): "Ping An Bank",
        ("hk_connect", "00700"): "Tencent Holdings",
    }


def test_resolve_names_omits_missing_blank_and_unknown_names(sqlite_session):
    sqlite_session.add(AStockBasic(股票代码="000001", 股票名称=""))
    sqlite_session.commit()

    assert SecurityNameProvider(sqlite_session).resolve_names({
        ("a_share", "000001"),
        ("a_share", "600000"),
        ("unknown", "XYZ"),
    }) == {}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_security_metadata.py -q`

Expected: FAIL because `paper_trading.storage.security_metadata` does not exist.

- [ ] **Step 3: Implement a batched per-market provider**

```python
class SecurityNameProvider:
    def __init__(self, session: Session):
        self._session = session

    def resolve_names(self, securities: Collection[tuple[str, str]]) -> dict[tuple[str, str], str]:
        symbols_by_market: dict[str, set[str]] = {}
        for market, symbol in securities:
            if symbol:
                symbols_by_market.setdefault(market, set()).add(symbol)
        return {
            **self._resolve_a_share(symbols_by_market.get(Market.A_SHARE.value, set())),
            **self._resolve_hk_connect(symbols_by_market.get(Market.HK_CONNECT.value, set())),
        }
```

Implement `_resolve_a_share` and `_resolve_hk_connect` with one `IN` query each. Return only non-empty names keyed by exact `(market, symbol)`. Use a nested transaction around each loader and catch `SQLAlchemyError`, returning `{}` from only the failed source. Add `get_security_name_provider` in `paper_trading/api/deps.py`.

- [ ] **Step 4: Cover deduplication and source isolation**

```python
def test_resolve_names_calls_each_loader_once_for_duplicate_keys(sqlite_session, monkeypatch):
    provider = SecurityNameProvider(sqlite_session)
    calls: list[set[str]] = []
    monkeypatch.setattr(provider, "_resolve_a_share", lambda symbols: calls.append(symbols) or {})

    provider.resolve_names({("a_share", "000001"), ("a_share", "000001")})

    assert calls == [{"000001"}]


def test_resolve_names_preserves_hk_when_a_share_loader_fails(sqlite_session, monkeypatch):
    provider = SecurityNameProvider(sqlite_session)
    monkeypatch.setattr(provider, "_resolve_a_share", lambda symbols: (_ for _ in ()).throw(SQLAlchemyError("down")))
    monkeypatch.setattr(provider, "_resolve_hk_connect", lambda symbols: {("hk_connect", "00700"): "Tencent Holdings"})

    assert provider.resolve_names({("a_share", "000001"), ("hk_connect", "00700")}) == {
        ("hk_connect", "00700"): "Tencent Holdings"
    }
```

- [ ] **Step 5: Run provider verification and commit**

Run: `uv run pytest test/paper_trading/storage/test_security_metadata.py -q`

Expected: PASS.

```bash
git add paper_trading/storage/security_metadata.py paper_trading/api/deps.py test/paper_trading/storage/test_security_metadata.py
git commit -m "feat: resolve paper trading security names"
```

### Task 2: Enrich the Three List Responses

**Files:**
- Create: `paper_trading/api/response_enrichment.py`
- Modify: `paper_trading/schemas/accounts.py:84-92`
- Modify: `paper_trading/schemas/orders.py:20-40,72-86`
- Modify: `paper_trading/api/routers/accounts.py:90-92`
- Modify: `paper_trading/api/routers/orders.py:60-62,116-118`
- Modify: `test/paper_trading/api/test_accounts_api.py`
- Modify: `test/paper_trading/api/test_orders_api.py`
- Modify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: `SecurityNameProvider.resolve_names()` and ORM list rows.
- Produces: `enrich_security_names(rows, response_type, provider) -> list[ResponseModel]` and `stock_name: str | None = None` on all three response models.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_list_positions_includes_a_share_stock_name(client, seeded_a_share_position):
    response = client.get(f"/paper/accounts/{seeded_a_share_position.account_id}/positions", headers=AUTH)

    assert response.status_code == 200
    assert response.json()[0]["stock_name"] == "Ping An Bank"


def test_list_orders_and_trades_include_hk_stock_name(client, seeded_hk_order_and_trade):
    orders = client.get(f"/paper/accounts/{seeded_hk_order_and_trade.account_id}/orders", headers=AUTH)
    trades = client.get(f"/paper/accounts/{seeded_hk_order_and_trade.account_id}/trades", headers=AUTH)

    assert orders.json()[0]["stock_name"] == "Tencent Holdings"
    assert trades.json()[0]["stock_name"] == "Tencent Holdings"
```

Also assert a row with no metadata returns status `200`, ordinary row data, and `"stock_name": null`.

- [ ] **Step 2: Run focused API tests to verify failure**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_orders_api.py -q`

Expected: FAIL because list payloads lack `stock_name`.

- [ ] **Step 3: Add response fields and enrichment helper**

```python
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

def enrich_security_names(rows, response_type, provider):
    responses = [response_type.model_validate(row) for row in rows]
    names = provider.resolve_names({(response.market, response.symbol) for response in responses})
    return [
        response.model_copy(update={"stock_name": names.get((response.market, response.symbol))})
        for response in responses
    ]
```

Add `stock_name: str | None = None` to `PositionResponse`, `OrderResponse`, and `TradeResponse`. Inject the provider and call the helper only in `list_positions`, `list_orders`, and `list_trades`. Do not add metadata work to create, get, cancel, update, or delete endpoints.

- [ ] **Step 4: Document and verify API behavior**

Document in `docs/paper_trading.md` that the three list response rows include nullable display-only `stock_name`, while `symbol` remains the trading identifier.

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_orders_api.py -q && uv run ruff check paper_trading test/paper_trading && uv run mypy`

Expected: all commands exit `0`.

- [ ] **Step 5: Commit list response enrichment**

```bash
git add paper_trading/api/response_enrichment.py paper_trading/api/routers/accounts.py paper_trading/api/routers/orders.py paper_trading/schemas/accounts.py paper_trading/schemas/orders.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_orders_api.py docs/paper_trading.md
git commit -m "feat: include stock names in paper trading lists"
```

### Task 3: Render Names in Shared Trading Tables

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:102-153`
- Modify: `frontend/paper-trading/features/trading/trading-tables.tsx:7-116`
- Create: `frontend/paper-trading/features/trading/trading-tables.test.tsx`
- Modify: `frontend/paper-trading/app/globals.css:164-209`
- Modify: `frontend/paper-trading/app/globals.test.ts`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Modify: `frontend/paper-trading/features/history/orders-page.test.tsx`
- Modify: `frontend/paper-trading/features/history/trades-page.test.tsx`
- Modify: `frontend/paper-trading/features/trading/order-form.test.tsx`

**Interfaces:**
- Consumes: `stock_name: string | null` in Position, Order, and Trade list payloads.
- Produces: a private `StockNameCell` and a `Stock` column next to every `Symbol` column.

- [ ] **Step 1: Write failing shared-table tests**

```tsx
it("renders Symbol then Stock and displays a populated name", () => {
  render(<PositionTable positions={[position]} />);

  expect(screen.getAllByRole("columnheader").slice(0, 2).map((cell) => cell.textContent))
    .toEqual(["Symbol", "Stock"]);
  expect(screen.getByText("Ping An Bank")).toBeInTheDocument();
});

it("renders a dash when the stock name is null", () => {
  render(<OrderTable {...orderTableProps} orders={[{ ...order, stock_name: null }]} />);

  expect(screen.getByText("-")).toBeInTheDocument();
});

it("preserves the full long name in title", () => {
  render(<TradeTable trades={[{ ...trade, stock_name: "A Very Long Security Name" }]} />);

  expect(screen.getByTitle("A Very Long Security Name")).toHaveClass("stock-name");
});
```

Add coverage for `stock-name--compact` when a compact positions table renders.

- [ ] **Step 2: Run table test to verify failure**

Run: `npm --prefix frontend/paper-trading test -- features/trading/trading-tables.test.tsx`

Expected: FAIL because the shared tables have no `Stock` column.

- [ ] **Step 3: Extend contracts and shared table renderers**

```tsx
function StockNameCell({ compact = false, name }: { compact?: boolean; name: string | null }) {
  const value = name || "-";
  return (
    <span className={compact ? "stock-name stock-name--compact" : "stock-name"} title={name || undefined}>
      {value}
    </span>
  );
}
```

Add a required `stock_name: string | null` property to `Position`, `Order`, and `Trade`. Add `{ key: "stock", header: "Stock", render: ... }` immediately after the Symbol column in all three tables. Pass `compact={density === "compact"}` only for the position table.

- [ ] **Step 4: Add bounded name-cell CSS and CSS-source test**

```css
.stock-name {
  display: block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stock-name--compact {
  max-width: 140px;
}
```

Update `globals.test.ts` to assert the selector has `overflow: hidden`, `text-overflow: ellipsis`, and `white-space: nowrap`. Do not alter global table widths, scrolling, or numeric styles.

- [ ] **Step 5: Update typed fixtures and verify frontend behavior**

Add `stock_name` to every non-empty typed Position, Order, and Trade fixture in the named page and form tests. Use actual values in normal fixtures and `null` only in fallback tests.

Run:

```bash
npm --prefix frontend/paper-trading test -- features/trading/trading-tables.test.tsx features/accounts/accounts-page.test.tsx features/history/orders-page.test.tsx features/history/trades-page.test.tsx features/trading/order-form.test.tsx app/globals.test.ts
npm --prefix frontend/paper-trading run lint
npm --prefix frontend/paper-trading run build
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit frontend table work**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/features/trading/trading-tables.test.tsx frontend/paper-trading/app/globals.css frontend/paper-trading/app/globals.test.ts frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/features/history/orders-page.test.tsx frontend/paper-trading/features/history/trades-page.test.tsx frontend/paper-trading/features/trading/order-form.test.tsx
git commit -m "feat: show stock names in trading tables"
```

### Task 4: Run Final Focused Regression Gates

**Files:**
- Modify: none unless a scoped verification failure requires a correction.

- [ ] **Step 1: Verify backend behavior**

```bash
uv run pytest test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_orders_api.py
uv run ruff check paper_trading test/paper_trading
```

Expected: both commands exit `0`.

- [ ] **Step 2: Verify frontend behavior**

```bash
npm --prefix frontend/paper-trading test -- features/trading/trading-tables.test.tsx features/accounts/accounts-page.test.tsx features/history/orders-page.test.tsx features/history/trades-page.test.tsx features/trading/order-form.test.tsx app/globals.test.ts
npm --prefix frontend/paper-trading run build
```

Expected: both commands exit `0`.

- [ ] **Step 3: Inspect final worktree integrity**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; preserve unrelated pre-existing changes.
