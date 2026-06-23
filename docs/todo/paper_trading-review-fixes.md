# Paper Trading 模块代码审查修复项

发现时间: 2026-06-23
来源: `paper_trading/` 全面代码审查（oracle review + 源码验证）

## 概览

对 `paper_trading/` 共 27 个 `.py` 文件的审查，发现了 11 个问题，其中 Critical 2 项、Important 6 项、Minor 3 项。核心风险集中在交易匹配过程的持久化完整性、输入校验缺失和 API 错误处理不一致。

---

## Critical

### C1. 撮合循环异常吞没导致部分持久化

- **位置**: `paper_trading/services/matching_service.py:35`
- **描述**: 逐订单的 `for` 循环使用宽泛 `except Exception`，但 `_fill_order()` 中的 `create_trade()` / `add_cash_event()` / `upsert_position()` 等操作均已调用 `session.flush()`。某个订单的 cash/position 更新已 flush 后如果后续出错被捕获，循环继续，最终 `session.commit()` 在 `paper_trading/api/routers/matching.py:28` 提交时可能包含不完整的状态（已有 trade 但缺少 cash/position 更新）。
- **影响**: 账本和持仓数据损坏，资金对不上。
- **修复方向**: 每个订单使用嵌套事务/savepoint，失败时 rollback；或直接让整个 matching run 原子化，出错整体回滚。

### C2. 快照唯一约束冲突

- **位置**: `paper_trading/services/matching_service.py:51`
- **描述**: 匹配完成后为每个受影响的账户生成快照。`storage/model/paper_trading.py:115` 定义了 `(account_id, trade_date)` 的唯一约束。若对同一账户/日期重复执行 matching run，第二次会因 `IntegrityError` 失败，且此时前面的订单已经部分完成。
- **影响**: API 返回 500，运行结果状态不明确，依赖事务边界可能回滚或残留。
- **修复方向**: 快照改为 upsert（按 `(account_id, trade_date)` 覆盖或跳过），并将快照失败纳入 matching run 状态。

---

## Important

### I1. `limit_price` 未校验正数

- **位置**: `paper_trading/services/order_service.py:91`
- **描述**: `_accept_buy_order()` 中 `amount = quantity * limit_price` 未校验 `limit_price > 0`。负数限价生成负的 `amount` 和 `frozen_cash`，进而在 `paper_trading/services/order_service.py:105` 的 `add_cash_event(FREEZE, -frozen_cash)` 中**增加**可用现金。
- **影响**: 用户可以下无效买单来"创造"现金。
- **修复方向**: 在 schema 层或 domain rules 层增加 `limit_price > 0` 校验。

### I2. 下单未校验账户存在

- **位置**: `paper_trading/api/routers/orders.py:21`
- **描述**: 下单接口未调用 `repo.get_account()` 确认账户存在，直接进入 `OrderService.place_order()`。无效 `account_id` 会导致创建 rejected order 关联不存在账户，或 FK `IntegrityError` 500。
- **影响**: API 行为不一致，应返回 404 而不是 500。
- **修复方向**: 在创建订单前检查账户存在并返回 `HTTPException(404)`。

### I3. Idempotency Key 全局唯一但无重放逻辑

- **位置**: `paper_trading/storage/repository.py:115`，模型约束见 `storage/model/paper_trading.py:90`
- **描述**: `idempotency_key` 设为 `unique=True`（全局唯一），但 `create_order()` 没有查询-返回已有订单的逻辑。重复请求触发 `IntegrityError` 500。
- **影响**: POST 幂等重试语义完全缺失。
- **修复方向**: 范围改为 `(account_id, idempotency_key)` (或移到应用层实现)，并实现先查后建的重放逻辑。

### I4. 卖单可卖量未遵守 T+1 / Lot 买入日期

- **位置**: `paper_trading/services/order_service.py:123`
- **描述**: 可卖量仅从 aggregate position 计算 (`total_quantity - frozen_quantity`)，忽略了 A 股 T+1 规则和 lot 买入日期。虽然 domain 层有 `ensure_lot_size` 和 A 股费用计算，但卖单接受逻辑并未按 lot 层级校验哪些是今日可卖的。
- **影响**: 同日买入的股票可在 matching run 中立即卖出，产生不现实的结算。
- **修复方向**: 实现基于 lot 的 T+1 可卖量计算，或明确文档化当前行为不做 T+1 限制。

### I5. 获取不存在的 order / matching run 返回 500

- **位置**: `paper_trading/storage/repository.py:137`（`get_order()` 抛 `KeyError`）、`paper_trading/storage/repository.py:296`（`get_matching_run()` 抛 `KeyError`）；API 层 `paper_trading/api/routers/orders.py:47`、`paper_trading/api/routers/matching.py:37` 未处理。
- **描述**: Repository 接口抛出 `KeyError`，API router 直接透传，FastAPI 默认返回 500。
- **影响**: 不符合 REST 惯例，客户端无法区分"不存在"和"服务器错误"。
- **修复方向**: API 层将 `KeyError` 转为 `HTTPException(404)`，或 repository 返回 None 让 API 层判空。

### I6. 卖出结算中 Lot 剩余量与持仓量未断言一致

- **位置**: `paper_trading/services/matching_service.py:146-153`
- **描述**: `_settle_sell()` 遍历 lot 扣减 `remaining`，循环结束后直接减 `position.total_quantity`，但未检查 `remaining == 0`。如果 lot 和 position 之间存在数据不一致（例如 `total_quantity` 大于所有 lot 的 `remaining_quantity` 之和），持仓会被扣过头。
- **影响**: 持仓数量或 PnL 出现负数等异常。
- **修复方向**: 循环后断言 `remaining == 0`，或失败时回滚该订单。

---

## Minor

### M1. `_session_factory()` 每次调用创建新 engine

- **位置**: `paper_trading/api/deps.py:27`
- **描述**: `get_session()` 每次请求创建新的 SQLAlchemy `engine` + `sessionmaker`。
- **影响**: 不必要的连接池抖动和延迟。
- **修复方向**: 提升为模块级单例 `engine` / `sessionmaker`。

### M2. GET 单个账户返回 200 null

- **位置**: `paper_trading/api/routers/accounts.py:30`
- **描述**: `response_model=AccountResponse | None`，不存在的账户返回 `200 null`，而 DELETE /{account_id} 正确返回了 404。
- **影响**: REST 行为不一致。
- **修复方向**: 改为返回 `HTTPException(404)`。

### M3. `initial_cash` 无非负校验

- **位置**: `paper_trading/schemas/accounts.py:6`
- **描述**: `CreateAccountRequest.initial_cash` 缺少 `>= 0` 约束。
- **影响**: 可创建负余额账户，DB 层无约束（`Numeric(20,4)` 允许负数）。
- **修复方向**: Pydantic `Field(ge=0)` 或 domain rules 层校验。

---

## 建议的测试覆盖

1. **C1 匹配回滚测试**: `create_trade()` 成功而 settlement 抛出异常时，验证无 trade/cash/position 残留。
2. **C2 快照幂等测试**: 重复对同一账户/日期做 matching run，验证不抛错且状态一致。
3. **I1 负价格/零价格 API 测试**: `POST /paper/accounts/{id}/orders` 传入 `limit_price=0/-1` 预期返回 4xx。
4. **I3 Idempotency Key 重放测试**: 相同 key 重复请求返回已有订单而非 500。
5. **I5 404 行为测试**: 不存在的 order / matching run / account 各 API 端点预期返回 404。
6. **M1-M2 行为测试**: GET 不存在的 account 应返回 404；连接池无需重复创建。
