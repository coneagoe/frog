# Paper Trading 净值曲线起点分析

发现时间: 2026-08-25
范围: `paper_trading` analytics 页面净值曲线

## 结论

当前净值曲线不保证从 `1.0` 开始。直接原因是前端绘制的是最早一条账户快照中的 `net_asset_value`，而不是账户创建时初始化的单位净值 `1.0`。

这不是 `lightweight-charts` 的坐标轴问题，而是初始净值没有进入快照序列、且前端没有补初始点导致的数据序列定义问题。

## 当前数据流

1. 创建账户时，系统设置：

   ```text
   share_count = initial_cash
   net_asset_value = 1.000000
   ```

   位置: `paper_trading/storage/repository.py:274-298`

2. 创建账户时只写入账户记录和初始现金流水，没有创建 `PaperAccountSnapshot`。

3. 快照通常在撮合日、账户存在订单或持仓时生成。快照净值计算为：

   ```text
   total_assets = cash_available + cash_frozen + market_value + pending_settlement
   net_asset_value = total_assets / share_count
   ```

   位置: `paper_trading/services/snapshot_service.py:23-73`

4. snapshots API 按交易日升序返回快照，未插入账户创建时的初始点。

   位置: `paper_trading/storage/repository.py:676-682`

5. 前端 `AssetChart` 直接使用快照值绘图：

   ```tsx
   value: Number(snapshot.net_asset_value ?? snapshot.total_assets)
   ```

   位置: `frontend/paper-trading/features/analytics/asset-chart.tsx:23-27`

## 为什么首值可能不是 1

首个交易快照的资产值可能已经受到以下因素影响：

- 持仓按当日价格重新估值
- 买卖手续费
- 冻结资金或待结算资金变化
- 首个快照生成日并非账户创建日

因此首个快照可能是 `1.01`、`0.99` 或其他值。例如现有测试验证过，持仓市值变化后首个 snapshot NAV 可以是 `1.010000`：

`test/paper_trading/services/test_snapshot_service.py:137-145`

## 相关问题

### 前端 fallback 使用了绝对资产值

如果 `snapshot.net_asset_value` 为空，前端会回退到 `snapshot.total_assets`。这会把现金金额（例如 `100000`）当作净值绘制，数值更不可能从 `1.0` 开始。

### 后端 analytics 也以首个快照作为部分指标基准

`analytics_service.py` 优先使用快照中的 `net_asset_value`，收益率和风险序列通常从第一条快照开始，而不是自动插入账户创建时的 `NAV=1.0`。

位置:

- `paper_trading/services/analytics_service.py:53-85`
- `paper_trading/services/analytics_service.py:317-353`

因此，仅调整图表库或坐标轴无法解决这个问题。

## 修复方向

推荐由后端或统一的前端数据适配层明确构造包含初始点的净值序列：

1. 账户创建时生成一条初始 snapshot，日期使用账户创建日，`net_asset_value=1.0`。
2. 或由 analytics/equity-series API 返回一个明确的初始 NAV 点，再返回后续交易快照。
3. 如果账户创建日与首个交易日之间存在现金流，应根据产品规则决定是否显示这些日期，以及现金流是否通过份额调整处理。
4. 不建议简单执行“当前值 / 首个快照值”归一化。这样只能让第一条交易快照变成 `1.0`，无法表达账户从创建到首个交易日之间的真实净值变化。
5. 对缺少 `net_asset_value` 的快照，应优先修复数据生成逻辑；不建议把绝对的 `total_assets` 静默当作单位净值绘制。

## 验收标准

- 有账户初始点时，净值曲线的第一个点明确为 `1.000000`。
- 首个交易快照仍保留真实交易日和真实净值。
- 追加入金、出金不会被错误地当作投资收益。
- 没有单位净值的快照不会被静默绘制为绝对资产金额。
- analytics 总收益、风险指标和曲线使用一致的基准定义。

## Task 7 Verification Report

The documentation review corrections were applied to this report and to
`docs/paper_trading.md`. The review confirms that corporate-action ordering is
documented as deterministic listing/audit ordering only; newly submitted
actions apply to current state and full historical event replay is not claimed.
Internal/domain/storage `ROUND_HALF_UP` quantization is separated from public
Decimal response serialization/display behavior. `Numeric(30, 12)` is scoped
to account, ledger, snapshot, and corporate-action amount/quantity fields,
with legacy position, lot cost, and price precision explicitly retained.

### Verification Output

`uv run pre-commit run --files docs/paper_trading.md
docs/todo/paper_trading-nav-baseline-analysis.md`:

```text
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
mixed line ending........................................................Passed
ruff format..........................................(no files to check)Skipped
ruff (legacy alias)..................................(no files to check)Skipped
mypy.................................................(no files to check)Skipped
```

`git diff --check -- docs/paper_trading.md
docs/todo/paper_trading-nav-baseline-analysis.md` produced no output and
returned exit code 0.

### Self-review

- Confirmed only the two authorized documentation files are included in the
  fix commit.
- Confirmed stale corporate-action historical replay claims were removed
  without changing the documented event semantics, idempotency behavior,
  migration limitations, or NAV baseline corrections.
- Confirmed public Decimal serialization/display wording does not claim that
  the public serializer uses `ROUND_HALF_UP` or that display values are
  strings.
