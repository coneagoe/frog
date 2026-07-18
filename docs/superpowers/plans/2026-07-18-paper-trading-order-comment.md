# Paper Trading Order Comment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional paper trading order comments that can be supplied at order creation, updated later, copied to generated trades, and shown by API/CLI queries.

**Architecture:** Store `comment` as nullable text on both `paper_orders` and `paper_trades`. Thread it through schemas, repository, services, matching, API routes, and CLI. Blank comment updates normalize to `None` and synchronize linked trades.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, pytest, uv, repo-local `tools/paper_trading_cli.py`.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3` for project tasks.
- A-share order symbols in CLI/user docs should use 6-digit stock codes without `.SH` or `.SZ` suffixes.
- Comment is optional and must not affect order validation, account validation, position checks, or matching rules.
- Empty comment updates clear the stored value to `NULL` on the order and linked trades.
- Do not change matching eligibility, fill price logic, fees, cash ledger, positions, or snapshots.

---

## File Structure

- `storage/model/paper_trading.py`: add nullable `comment` columns to `PaperOrder` and `PaperTrade`.
- `storage/storage_db.py`: extend `ensure_paper_trading_schema()` for legacy `comment` columns.
- `paper_trading/schemas/orders.py`: add create/update request fields and response fields.
- `paper_trading/storage/repository.py`: persist comments and synchronize order comment updates to trades.
- `paper_trading/services/order_service.py`: accept comments during order placement and expose comment update.
- `paper_trading/services/matching_service.py`: copy `order.comment` to generated trades.
- `paper_trading/api/routers/orders.py`: pass create comments and add `PATCH /paper/orders/{order_id}/comment`.
- `tools/paper_trading_cli.py`: add `order create --comment` and `order update-comment`.
- `docs/paper_trading.md`: document CLI/API usage.

---

### Task 1: Persistence and Schema Upgrade

**Files:**
- Modify: `storage/model/paper_trading.py:84-146`
- Modify: `paper_trading/storage/repository.py:183-214,424-449`
- Modify: `storage/storage_db.py:2296-2343`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/storage/test_blackroom_storage_db.py`

**Interfaces:**
- Produces: `PaperOrder.comment: str | None`
- Produces: `PaperTrade.comment: str | None`
- Produces: `PaperTradingRepository.create_order(..., comment: str | None = None) -> PaperOrder`
- Produces: `PaperTradingRepository.create_trade(..., comment: str | None = None) -> PaperTrade`
- Produces: `PaperTradingRepository.update_order_comment(order: PaperOrder, comment: str | None) -> PaperOrder`

- [ ] **Step 1: Write failing model-column test**

In `test/paper_trading/storage/test_models.py`, extend `test_paper_trading_tables_are_registered`:

```python
    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {"validity_status", "validity_reason", "validity_checked_at", "comment"} <= order_columns

    trade_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trades)}
    assert "comment" in trade_columns
```

- [ ] **Step 2: Write failing repository tests**

Add tests to `test/paper_trading/storage/test_repository.py`:

```python
def test_order_and_trade_comments_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comments.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 7, 18), OrderStatus.ACCEPTED, comment="突破买入")
    repo.create_trade(order.id, account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), Decimal("1000.00"), Decimal("5.00"), date(2026, 7, 18), comment="突破买入")

    assert repo.get_order(order.id).comment == "突破买入"
    assert repo.list_trades(account.id)[0].comment == "突破买入"
    engine.dispose()


def test_update_order_comment_syncs_linked_trades_and_clears_blank(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comment_update.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 7, 18), OrderStatus.ACCEPTED, comment="old")
    repo.create_trade(order.id, account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), Decimal("1000.00"), Decimal("5.00"), date(2026, 7, 18), comment="old")

    repo.update_order_comment(order, "new reason")
    assert repo.get_order(order.id).comment == "new reason"
    assert repo.list_trades(account.id)[0].comment == "new reason"

    repo.update_order_comment(order, "")
    assert repo.get_order(order.id).comment is None
    assert repo.list_trades(account.id)[0].comment is None
    engine.dispose()
```

- [ ] **Step 3: Write failing schema-upgrade assertion**

In `test/storage/test_blackroom_storage_db.py::TestEnsurePaperTradingSchema.test_migrates_legacy_paper_orders_columns`, create a legacy `paper_trades` table with columns `id, order_id, account_id, symbol, side, quantity, price, amount, fees, trade_date, trade_time`, then assert:

```python
        columns = {row["name"] for row in inspect(engine).get_columns("paper_orders")}
        trade_columns = {row["name"] for row in inspect(engine).get_columns("paper_trades")}
        assert "comment" in columns
        assert "comment" in trade_columns
```

- [ ] **Step 4: Run failing tests**

```bash
uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py::test_order_and_trade_comments_are_persisted test/paper_trading/storage/test_repository.py::test_update_order_comment_syncs_linked_trades_and_clears_blank test/storage/test_blackroom_storage_db.py::TestEnsurePaperTradingSchema::test_migrates_legacy_paper_orders_columns -q
```

Expected: FAIL because columns and repository comment support do not exist.

- [ ] **Step 5: Implement model columns**

In `storage/model/paper_trading.py`, add:

```python
class PaperOrder(Base):
    ...
    rejection_reason = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperTrade(Base):
    ...
    trade_date = Column(Date, nullable=False, index=True)
    comment = Column(Text, nullable=True)
    trade_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 6: Implement repository support**

Inside `PaperTradingRepository`, add:

```python
    @staticmethod
    def _normalize_comment(comment: str | None) -> str | None:
        if comment is None or comment == "":
            return None
        return comment
```

Add `comment: str | None = None` to `create_order` and `create_trade`, set `comment=self._normalize_comment(comment)` on model objects, and add:

```python
    def update_order_comment(self, order: PaperOrder, comment: str | None) -> PaperOrder:
        normalized = self._normalize_comment(comment)
        order.comment = normalized
        order.updated_at = datetime.now(timezone.utc)
        self.session.query(PaperTrade).filter(PaperTrade.order_id == order.id).update(
            {PaperTrade.comment: normalized},
            synchronize_session=False,
        )
        self.session.flush()
        return order
```

- [ ] **Step 7: Implement schema upgrade**

In `storage/storage_db.py::ensure_paper_trading_schema`, after existing paper order legacy columns, add:

```python
        if "comment" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_orders} ADD COLUMN comment TEXT"))

        if inspect(self.engine).has_table(tb_name_paper_trades):
            trade_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_trades)}
            if "comment" not in trade_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_trades} ADD COLUMN comment TEXT"))
```

- [ ] **Step 8: Verify Task 1**

```bash
uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py::test_order_and_trade_comments_are_persisted test/paper_trading/storage/test_repository.py::test_update_order_comment_syncs_linked_trades_and_clears_blank test/storage/test_blackroom_storage_db.py::TestEnsurePaperTradingSchema::test_migrates_legacy_paper_orders_columns -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add storage/model/paper_trading.py paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/storage/test_blackroom_storage_db.py
git commit -m "feat: persist paper trading order comments"
```

---

### Task 2: Service, Matching, and API Behavior

**Files:**
- Modify: `paper_trading/schemas/orders.py`
- Modify: `paper_trading/services/order_service.py`
- Modify: `paper_trading/services/matching_service.py`
- Modify: `paper_trading/api/routers/orders.py`
- Test: `test/paper_trading/api/test_orders_api.py`
- Test: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: `PaperTradingRepository.update_order_comment(order, comment) -> PaperOrder`
- Produces: `CreateOrderRequest.comment: str | None = None`
- Produces: `UpdateOrderCommentRequest.comment: str | None = None`
- Produces: `OrderResponse.comment: str | None = None`
- Produces: `TradeResponse.comment: str | None = None`
- Produces: `OrderService.place_order(..., comment: str | None = None) -> PaperOrder`
- Produces: `OrderService.update_order_comment(order_id: int, comment: str | None) -> PaperOrder`

- [ ] **Step 1: Write failing API test**

Add `test_order_comment_is_created_copied_to_trade_and_updated` to `test/paper_trading/api/test_orders_api.py`. Set up the app like `test_create_order_auto_matches_when_limit_is_touched`, but use symbol `000001`, date `2026-07-18`, and create the order with `"comment": "突破买入"`. Assert create response has `comment == "突破买入"`, trade list has the same comment, `PATCH /paper/orders/{order_id}/comment` with `{"comment": "回踩确认后买入"}` updates both order and trade, and `PATCH` with `{"comment": ""}` returns `comment is None` and makes the trade comment `None`.

- [ ] **Step 2: Write failing matching test**

Add to `test/paper_trading/services/test_matching_service.py`:

```python
def test_matching_copies_order_comment_to_trade(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), trade_date, comment="突破买入")

    matching_service.run(trade_date)
    session.commit()

    assert repo.get_order(order.id).comment == "突破买入"
    assert repo.list_trades(account.id)[0].comment == "突破买入"
    engine.dispose()
```

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest test/paper_trading/api/test_orders_api.py::test_order_comment_is_created_copied_to_trade_and_updated test/paper_trading/services/test_matching_service.py::test_matching_copies_order_comment_to_trade -q
```

Expected: FAIL because API/service/schema support is missing.

- [ ] **Step 4: Implement schemas**

In `paper_trading/schemas/orders.py`, add `comment: str | None = None` to `CreateOrderRequest`, `OrderResponse`, and `TradeResponse`. Add:

```python
class UpdateOrderCommentRequest(BaseModel):
    comment: str | None = None
```

- [ ] **Step 5: Implement service and matching**

In `paper_trading/services/order_service.py`, add `comment: str | None = None` to `place_order`, `_accept_buy_order`, and `_accept_sell_order`. Pass `comment=comment` into every `repo.create_order(...)` call. Add:

```python
    def update_order_comment(self, order_id: int, comment: str | None) -> PaperOrder:
        order = self.repo.get_order(order_id)
        return self.repo.update_order_comment(order, comment)
```

In `paper_trading/services/matching_service.py`, pass `comment=order.comment` to `repo.create_trade(...)`.

- [ ] **Step 6: Implement API route**

In `paper_trading/api/routers/orders.py`, import `UpdateOrderCommentRequest`, pass `request.comment` into `place_order`, and add:

```python
@router.patch("/orders/{order_id}/comment", response_model=OrderResponse)
def update_order_comment(order_id: int, request: UpdateOrderCommentRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    order = OrderService(repo, get_market_data_provider()).update_order_comment(order_id, request.comment)
    session.commit()
    return order
```

- [ ] **Step 7: Verify Task 2**

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_orders_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add paper_trading/schemas/orders.py paper_trading/services/order_service.py paper_trading/services/matching_service.py paper_trading/api/routers/orders.py test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_matching_service.py
git commit -m "feat: expose paper trading order comments in API"
```

---

### Task 3: CLI Comment Support

**Files:**
- Modify: `tools/paper_trading_cli.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: `PATCH /paper/orders/{order_id}/comment`
- Produces: `PaperTradingApiClient.create_order(..., comment: str | None = None) -> dict[str, Any]`
- Produces: `PaperTradingApiClient.update_order_comment(order_id: int, comment: str | None) -> dict[str, Any]`
- Produces: CLI `order create ... [--comment COMMENT]`
- Produces: CLI `order update-comment --order-id ID --comment COMMENT`

- [ ] **Step 1: Write failing CLI tests**

In `test/tools/test_paper_trading_cli.py`, add `comment` to mock order/trade payloads. Add a `TestOrderCreate.test_create_order_with_comment` that runs `order create ... --comment 突破买入` and asserts `client.create_order.assert_called_once_with(..., idempotency_key=None, comment="突破买入")`. Add `TestOrderUpdateComment.test_update_comment_calls_client` asserting `client.update_order_comment.assert_called_once_with(order_id=10, comment="回踩确认后买入")`. Add a clear-comment test with `--comment ""` asserting `comment=""` is forwarded.

- [ ] **Step 2: Run failing CLI tests**

```bash
uv run pytest test/tools/test_paper_trading_cli.py::TestOrderCreate::test_create_order_with_comment test/tools/test_paper_trading_cli.py::TestOrderUpdateComment -q
```

Expected: FAIL because parser/client methods do not support comments yet.

- [ ] **Step 3: Implement CLI client methods**

In `tools/paper_trading_cli.py`, update the usage string to include `[--comment TEXT]` and `order update-comment --order-id ID --comment TEXT`. Add `comment: str | None = None` to `PaperTradingApiClient.create_order`; if `comment is not None`, include `body["comment"] = comment`. Add:

```python
    def update_order_comment(self, order_id: int, comment: str | None) -> dict[str, Any]:
        return self._request("PATCH", f"/paper/orders/{order_id}/comment", json={"comment": comment})
```

- [ ] **Step 4: Implement CLI parser and handler**

In `_add_order_subparsers`, add `p_create.add_argument("--comment", default=None)`. Add an `update-comment` subparser with required `--order-id` and required `--comment`. In `_handle_order`, pass `comment=args.comment` to create and add:

```python
    if cmd == "update-comment":
        return client.update_order_comment(order_id=args.order_id, comment=args.comment)
```

- [ ] **Step 5: Verify Task 3**

```bash
uv run pytest test/tools/test_paper_trading_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add tools/paper_trading_cli.py test/tools/test_paper_trading_cli.py
git commit -m "feat: add paper trading comment CLI"
```

---

### Task 4: Documentation and Final Verification

**Files:**
- Modify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: CLI/API behavior from Tasks 2 and 3.
- Produces: User-facing examples for optional create comments and later updates.

- [ ] **Step 1: Update docs**

In `docs/paper_trading.md`, update order creation examples to include:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-18 --comment "突破买入"
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment "回踩确认后买入"
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment ""
```

Update API snippets so order and trade JSON examples include `comment`.

- [ ] **Step 2: Verify docs and touched tests**

```bash
uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_orders_api.py test/tools/test_paper_trading_cli.py test/storage/test_blackroom_storage_db.py::TestEnsurePaperTradingSchema -q
```

Expected: PASS.

- [ ] **Step 3: Run formatting/lint on touched Python files**

```bash
uv run ruff format storage/model/paper_trading.py paper_trading/storage/repository.py storage/storage_db.py paper_trading/schemas/orders.py paper_trading/services/order_service.py paper_trading/services/matching_service.py paper_trading/api/routers/orders.py tools/paper_trading_cli.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_matching_service.py test/tools/test_paper_trading_cli.py test/storage/test_blackroom_storage_db.py
uv run ruff check storage/model/paper_trading.py paper_trading/storage/repository.py storage/storage_db.py paper_trading/schemas/orders.py paper_trading/services/order_service.py paper_trading/services/matching_service.py paper_trading/api/routers/orders.py tools/paper_trading_cli.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_matching_service.py test/tools/test_paper_trading_cli.py test/storage/test_blackroom_storage_db.py
```

Expected: both commands pass.

- [ ] **Step 4: Commit Task 4**

```bash
git add docs/paper_trading.md docs/superpowers/plans/2026-07-18-paper-trading-order-comment.md docs/superpowers/specs/2026-07-18-paper-trading-order-comment-design.md
git commit -m "docs: document paper trading order comments"
```

---

## Self-Review

- Spec coverage: persistence, optional create comments, matching copy, update/clear, synchronization, API/CLI responses, tests, and docs are covered by Tasks 1-4.
- Placeholder scan: no TBD/TODO/fill-later placeholders; each task has concrete files, commands, and expected outcomes.
- Type consistency: the plan consistently uses `comment: str | None`, `UpdateOrderCommentRequest`, and `update_order_comment` across repository, service, API, and CLI.
