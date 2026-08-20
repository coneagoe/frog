# Trades Filtering And Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement issue #76 by giving paper-trading Trades server-backed inclusive date filtering, stable pagination, reproducible URL state, and Orders-equivalent frontend behavior while keeping Trades read-only.

**Architecture:** Reuse `OrderListQuery` for request validation and add a Trade-specific pagination envelope. Add a dedicated repository page query and make only the Trades API route use it, preserving the legacy full-list repository method. Port the existing Orders history query/date/pagination state machine into `TradesPage`, with Trade-specific types, API calls, tests, and documentation.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, pytest, TypeScript, React, Next.js navigation, Vitest, Testing Library, Ruff, mypy.

## Global Constraints

- Trades remain read-only; do not add cancellation, deletion, or comment-editing controls.
- Date filtering is inclusive and uses `Asia/Shanghai` calendar semantics in the frontend.
- API pages are one-indexed and `page_size` is bounded by the existing Orders query contract.
- Stable backend ordering is `trade_date DESC, id DESC`.
- Empty results normalize to page 1 with zero total pages; over-large pages normalize to the final valid page.
- Preserve the legacy `TradeRepository.list_trades(account_id)` because `paper_trading/services/round_trip_service.py` consumes it.
- Use `uv run` for Python commands and `tools/run_tests.sh` for PostgreSQL integration tests.
- Do not change Orders behavior or unrelated shared abstractions.

---

### Task 1: Add the Trade pagination schema

**Files:**
- Modify: `paper_trading/schemas/orders.py:44-109`
- Test: `test/paper_trading/api/test_orders_api.py`

**Interfaces:**
- Consumes: existing `TradeResponse` and `OrderListQuery`.
- Produces: `TradeListResponse` with `items: list[TradeResponse]`, `page`, `page_size`, `total_count`, and `total_pages`.

- [ ] **Step 1: Add the response model next to `OrderListResponse`**

Use the same field names and Pydantic configuration conventions as Orders, changing only the item type:

```python
class TradeListResponse(BaseModel):
    items: list[TradeResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int
```

- [ ] **Step 2: Run the focused import/type test**

Run: `uv run pytest test/paper_trading/api/test_orders_api.py -q`

Expected: existing tests pass; no behavior uses the new model yet.

- [ ] **Step 3: Commit the schema contract**

```bash
git add paper_trading/schemas/orders.py
git commit -m "feat: add paginated trade response schema"
```

### Task 2: Add repository-side Trade pagination

**Files:**
- Modify: `paper_trading/storage/repository.py:648-654`
- Test: `test/paper_trading/storage/test_repository.py:303-333`

**Interfaces:**
- Consumes: `PaperTrade`, `date`, SQLAlchemy select/count conventions from `list_orders_page`.
- Produces: `list_trades_page(account_id: int, start_date: date, end_date: date, page: int, page_size: int) -> tuple[list[PaperTrade], int]`.

- [ ] **Step 1: Write the failing repository test**

Add a test that creates target-account trades on both date boundaries and multiple trades on one date, plus a trade for another account. Query `2026-08-01` through `2026-08-02` with `page_size=2`; assert target-account isolation, inclusive boundaries, `trade_date DESC, id DESC` ordering, `total_count == 3`, page 1 contains the two newest IDs, and page 2 contains the remaining ID.

- [ ] **Step 2: Run the test to verify it fails**

Run: `tools/run_tests.sh test/paper_trading/storage/test_repository.py -k list_trades_page -v`

Expected: FAIL because `list_trades_page` does not exist.

- [ ] **Step 3: Implement the minimal page query**

Mirror `list_orders_page`: filter `PaperTrade.account_id`, `PaperTrade.trade_date >= start_date`, and `<= end_date`; count before slicing; apply `offset = (page - 1) * page_size`; order by `PaperTrade.trade_date.desc(), PaperTrade.id.desc()`; return rows and the count. Leave `list_trades` unchanged.

- [ ] **Step 4: Run the focused repository tests**

Run: `tools/run_tests.sh test/paper_trading/storage/test_repository.py -k "list_trades_page or list_trades" -v`

Expected: PASS.

- [ ] **Step 5: Commit the repository behavior**

```bash
git add paper_trading/storage/repository.py test/paper_trading/storage/test_repository.py
git commit -m "feat: paginate paper trades in repository"
```

### Task 3: Expose the paginated Trades API

**Files:**
- Modify: `paper_trading/api/routers/orders.py:1-25,153-160`
- Modify: `test/paper_trading/api/test_orders_api.py:169-283`

**Interfaces:**
- Consumes: `OrderListQuery`, `TradeListResponse`, and `TradeRepository.list_trades_page`.
- Produces: `GET /paper/accounts/{account_id}/trades` returning `TradeListResponse`.

- [ ] **Step 1: Update the existing enrichment test for the envelope**

Change its Trade assertion from `response.json()[0]` to `response.json()["items"][0]` while retaining the `stock_name` assertion.

- [ ] **Step 2: Add the filtered envelope API test**

Mirror the Orders filtered-pagination test with Trades. Assert inclusive date filtering, newest trade date first, newer ID first for equal dates, `page`, `page_size`, `total_count`, `total_pages`, and enriched `stock_name`.

- [ ] **Step 3: Add validation and normalization cases**

Mirror the Orders validation test: `page=0` and `page_size=101` return 422, reversed dates return 422, `page=99` returns the last valid page, and a date range with no matches returns `page == 1`, `total_count == 0`, and `total_pages == 0`.

- [ ] **Step 4: Run the new API tests to verify they initially fail**

Run: `tools/run_tests.sh test/paper_trading/api/test_orders_api.py -k "trades and (pagination or validates or include_stock_name)" -v`

Expected: FAIL until the route accepts query parameters and returns an envelope.

- [ ] **Step 5: Change the route contract and implementation**

Import `TradeListResponse`, accept `query: Annotated[OrderListQuery, Query()]`, call `list_trades_page`, calculate `total_pages = ceil(total_count / query.page_size)`, use page 1 for zero results, clamp over-large pages to `total_pages`, fetch the normalized slice when needed, enrich each trade using the existing provider, and return the envelope.

- [ ] **Step 6: Run focused API verification**

Run: `tools/run_tests.sh test/paper_trading/api/test_orders_api.py -k "trades" -v`

Expected: PASS, including existing account/security and stock-name behavior.

- [ ] **Step 7: Commit the API contract**

```bash
git add paper_trading/api/routers/orders.py test/paper_trading/api/test_orders_api.py
git commit -m "feat: add paginated trades API"
```

### Task 4: Update frontend Trade types and API client

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:151-179`
- Modify: `frontend/paper-trading/lib/api-client.ts:1-21,96-98`
- Modify: `frontend/paper-trading/lib/api-client.test.ts:87-125`

**Interfaces:**
- Consumes: the backend `TradeListResponse` JSON envelope.
- Produces: `TradePage`, `ListTradesParams`, and `listTrades(accountId: number, params?: ListTradesParams): Promise<TradePage>`.

- [ ] **Step 1: Add page and query types**

Define `TradePage` with `items: Trade[]` and the four pagination metadata fields. Define `ListTradesParams` with optional `start_date`, `end_date`, `page`, and `page_size` strings/numbers matching `ListOrdersParams`.

- [ ] **Step 2: Add the failing client contract test**

Mock `fetch`, resolve a TradePage envelope, call `listTrades(7, { start_date: "2026-08-01", end_date: "2026-08-02", page: 2, page_size: 25 })`, and assert the URL has all four query parameters. Also assert undefined fields are omitted and a call without params has no query string.

- [ ] **Step 3: Implement query serialization**

Mirror `listOrders`: build `URLSearchParams`, add only defined values, call `/accounts/${accountId}/trades` with the query string when non-empty, and return `response.json()` typed as `TradePage`.

- [ ] **Step 4: Run frontend client tests**

Run: `npm --prefix frontend/paper-trading test -- --run lib/api-client.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the client contract**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/lib/api-client.ts frontend/paper-trading/lib/api-client.test.ts
git commit -m "feat: support paginated trades in frontend client"
```

### Task 5: Port Orders history behavior into TradesPage

**Files:**
- Modify: `frontend/paper-trading/features/history/trades-page.tsx:1-95`
- Reference: `frontend/paper-trading/features/history/orders-page.tsx:10-425`

**Interfaces:**
- Consumes: `listAccounts`, `listTrades(accountId, params)`, `TradePage`, `TradeTable`, `ErrorBanner`, and Next router/search params.
- Produces: a read-only Trades history page with URL-synchronized date filters and pagination.

- [ ] **Step 1: Add query/date helper tests before implementation**

Use the existing Orders page test patterns to specify default trailing-30-day range, Shanghai Today/7-day/30-day presets, custom inclusive ranges, account/page URL restoration, and invalid reversed ranges producing no `listTrades` call.

- [ ] **Step 2: Run the new page tests to verify they fail**

Run: `npm --prefix frontend/paper-trading test -- --run features/history/trades-page.test.tsx`

Expected: FAIL because the current page has no date controls, URL replacement, pagination, or envelope handling.

- [ ] **Step 3: Implement the query state machine**

Port the Orders constants and helpers (`PAGE_SIZE = 25`, Shanghai timezone date helpers, range parsing/validation, account/page parsing, and active preset calculation). Parse initial URL state once, load accounts once, select the URL account when valid, and keep `rangeStart`, `rangeEnd`, `page`, and explicit-range state in React state.

- [ ] **Step 4: Implement guarded server fetching and URL synchronization**

Fetch with `{ start_date: rangeStart, end_date: rangeEnd, page, page_size: 25 }`. Store `items`, `total_count`, `total_pages`, and the API-returned page. Use a request ID/ref guard covering account, range, and page changes. Replace `/trades` URL state without triggering account reinitialization. Reset page 1 on account or range changes, and skip fetching while the custom range is invalid.

- [ ] **Step 5: Implement the controls and states**

Render preset buttons, labeled start/end date inputs, invalid-range feedback, account selector, loading state, no-account state, API error banner, filtered-empty state, read-only `TradeTable`, and Previous/Next controls with page metadata. Hide pagination when `total_pages <= 1`; do not pass mutation callbacks to `TradeTable`.

- [ ] **Step 6: Run the focused page tests**

Run: `npm --prefix frontend/paper-trading test -- --run features/history/trades-page.test.tsx`

Expected: PASS for both the new Orders-parity cases and the preserved existing Trade row/comment/read-only/error/account cases.

- [ ] **Step 7: Commit the Trades page**

```bash
git add frontend/paper-trading/features/history/trades-page.tsx frontend/paper-trading/features/history/trades-page.test.tsx
git commit -m "feat: add trade history filtering and pagination"
```

### Task 6: Update Trades documentation

**Files:**
- Modify: `docs/paper_trading.md:62-68`

**Interfaces:**
- Consumes: implemented Trades API and page behavior.
- Produces: documentation that accurately describes server-backed date filtering, pagination, URL persistence, and read-only execution history.

- [ ] **Step 1: Update the Trades bullet**

Document fixed 25-row pages, Today/7-day/30-day and custom inclusive Asia/Shanghai date ranges, URL-preserved account/range/page state, and read-only historical execution review. Keep the existing Orders wording and unrelated documentation unchanged.

- [ ] **Step 2: Check documentation diff**

Run: `git diff --check -- docs/paper_trading.md`

Expected: no whitespace errors and no claims that are absent from the implementation.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/paper_trading.md
git commit -m "docs: describe paginated trade history"
```

### Task 7: Run cross-layer verification and simplify review

**Files:**
- Verify all files changed by Tasks 1-6.

- [ ] **Step 1: Run backend focused tests**

Run: `tools/run_tests.sh test/paper_trading/api/test_orders_api.py test/paper_trading/storage/test_repository.py -v`

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run: `npm --prefix frontend/paper-trading test -- --run lib/api-client.test.ts features/history/trades-page.test.tsx`

Expected: PASS.

- [ ] **Step 3: Run formatting, lint, and type checks**

Run: `uv run ruff format --check . && uv run ruff check . && uv run mypy`

Expected: PASS, or any pre-existing unrelated failures are recorded rather than hidden.

- [ ] **Step 4: Invoke the simplify review**

Use the `simplify` skill on the final diff. Apply only targeted clarity improvements that preserve the issue scope and rerun affected tests after any change. If no safe simplification exists, record that conclusion in the final report.

- [ ] **Step 5: Inspect final status and diff**

Run: `git status --short && git diff HEAD~7..HEAD --check`

Expected: only issue #76 implementation/spec-plan commits and intentional pre-existing untracked user data remain; no generated or unrelated files are staged.
