# Paper Trading 港股通旧数据库升级修复设计

## 背景

港股通支持向 SQLAlchemy 模型新增了账户港股费率、订单/成交/持仓/有效性检查的市场标识，以及账户快照的待结算金额。现有数据库启动时调用的 `StorageDb.ensure_paper_trading_schema()` 未补齐这些字段。

因此，运行在旧数据库上的服务查询 `PaperAccount` 时会选择不存在的 `paper_accounts.hk_commission_rate` 等列，并在 `GET /paper/accounts` 返回 HTTP 500。

## 目标

让现有 paper trading 数据库在服务启动时以幂等方式补齐港股通新增字段；不要求手工 SQL，不改变已有数据；使当前服务重启后账户查询不再因缺列而失败。

## 方案

扩展 `storage/storage_db.py` 中的 `StorageDb.ensure_paper_trading_schema()`。

对存在的旧表通过 schema inspection 检查列是否存在；仅对缺失列执行 `ALTER TABLE ... ADD COLUMN`。列定义与 `storage/model/paper_trading.py` 中的 ORM 模型保持一致：

- `paper_accounts`：7 个可空 `hk_*` 费率字段。
- `paper_positions`、`paper_orders`、`paper_trades`、`paper_trade_validity_checks`：非空 `market VARCHAR(20)`，默认 `a_share`。
- `paper_account_snapshots`：非空 `pending_settlement NUMERIC(20, 4)`，默认 `0`。

现有的 `PaperPendingSettlement.__table__.create(..., checkfirst=True)` 保持不变，以继续创建缺失的待结算表。

## 数据兼容性

- 非空市场字段提供服务器默认值 `a_share`，因此旧数据保留为 A 股市场语义。
- 快照待结算金额默认 `0`，因此旧快照资产数值不变。
- 港股费率字段允许为空，服务沿用现有港股费率默认值逻辑。
- 所有变更仅添加列/表，不删除或重写已有数据。
- 每次服务启动重复执行升级时，由列存在性检查保证无副作用。

## 测试与验证

先添加回归测试，构造缺少港股通字段的旧 paper trading schema；调用 `ensure_paper_trading_schema()` 后验证：

1. 所有港股通新增列存在，且默认值允许旧记录保持兼容。
2. 旧库可通过 `PaperAccount` ORM 查询，不再产生缺列错误。
3. 既有 paper trading 测试保持通过。

应用阶段重启 `paper-trading` 服务以触发升级，再以认证请求调用 `GET /paper/accounts`。成功标准是响应不再是 HTTP 500，且服务日志没有 `UndefinedColumn`。

## 非目标

- 不在本次修复中引入新的迁移框架。
- 不变更港股通业务规则、费用计算或前端市场选择器。
- 不处理持仓唯一约束、持仓 lot 或 round trip 的跨市场建模问题；它们不导致当前缺列 500。
