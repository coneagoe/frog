# Stock Monitor CLI

## 共享监控目标控制台

认证用户可通过 Paper Trading 控制台的 `/monitor` 页面管理手工创建的共享监控目标（`workflow` 为 `None`）：可按市场、频率、启用状态和条件类型筛选，并可创建、编辑、启用或禁用，以及永久删除目标。

该控制台严格隔离工作流管理的目标，不显示或修改工作流目标。控制台不提供暂停或恢复操作；工作流专用的 pause/resume 行为和 CLI 命令保持不变。编辑目标时使用右侧滑出面板，创建和编辑均提供逐字段校验。页面持续显示告警专用提示，明确说明不会执行任何交易。

### 运行健康视图

`/monitor` 在保留仅面向手工目标的创建、编辑、启用、禁用和删除操作的同时，为认证用户提供只读运行健康视图。该视图显示手工和工作流目标，并汇总 `running`、`paused`、`disabled`、`triggered`、`daily` 与 `intraday` 数量。目标状态优先级为 `disabled` > `paused` > `running`；`triggered` 独立于 `last_state`。最后检查时间仅表示已完成且数据并非不足的运行器评估，配置变更、同步和刷新不会伪造该时间。错误信息只展示固定的安全摘要，以及已脱敏、截断的详情，不展示原始错误；表格不提供工作流目标的修改操作。

### 告警投递可靠性

触发边沿会先写入 `monitor_notifications` outbox，再由每分钟的投递任务异步发送邮件。PostgreSQL 首次访问 outbox 时会先完成监控域 enum 引导和校验，再创建或使用表。投递任务以 `claimed_at` 作为租约令牌：成功和失败落库都必须匹配当前 `processing` 租约，过期工作者不能覆盖后来工作者的结果。任务统计会分别记录 `cancelled` 和 `lost_claim`；后者表示租约已由其他工作者接管，而非目标被取消。

监控目标和投递记录是单用户共享的运维数据；登录只用于防止未授权篡改，不表示按用户隔离数据。邮件收件人来自全局配置（`MAIL_RECEIVERS`，由 `[email].email_receivers` 或部署的 `ALERT_EMAILS` 设置），而非逐目标配置。

投递记录状态及含义如下：`pending` 表示等待投递或下一次重试；`processing` 表示已被投递工作者租约领取；`delivered` 表示投递成功的终态；`failed` 表示达到重试上限后的失败终态；`cancelled` 表示目标删除或取消后抑制投递。失败按现有的有界指数退避计划重试：第 1 至第 4 次失败后分别等待 2、4、8、16 分钟，第 5 次失败后进入 `failed`，每分钟投递任务仍按既有计划运行。

通知 UUID 是支持排障、审计和去重时使用的句柄。投递语义为至少一次：发生超时或租约恢复时，外部收件人可能收到重复邮件，调用方不得据此假设 exactly-once。

## 管理命令入口

统一入口：`stock-monitor`

### 目标管理

- `stock-monitor target add --stock-code ... --market ... --condition ...`
- `stock-monitor target update --target-id ... [--stock-code ...] [--market ...] [--condition ...] [--note ...] [--frequency ...] [--reset-mode ...] [--enabled|--disabled] [--last-state|--last-state-false]`
- `stock-monitor target remove --target-id ...`
- `stock-monitor target list [--frequency daily|intraday] [--enabled|--disabled]`
- `stock-monitor target get --target-id ...`
- `stock-monitor target pause --target-id ...`
- `stock-monitor target resume --target-id ...`

### 监控条件

- `{"type":"close_cross_ma","direction":"above","period":20}`：仅适用于 A 股日频监控，读取截至监控业务日期的存储前复权日线最终收盘价，要求真实发生 MA20 向上穿越；数据不足或过期时保留监控状态。
- 旧版 `price_vs_ma` 目标会迁移为 `close_cross_ma`；非 A 股日频目标会被显式禁用并保留原目标元数据。

### 业绩预告数据

Tushare `forecast` 数据可经 `DownloadManager.download_forecast(ann_date=...)` 下载并保存到 `forecasts` 表。保存数据会标准化沪深 A 股代码及公告/报告期日期；候选查询只返回当前报告期内最新公告、类型为 `预增`、增长下限不低于 50%、且当前为非 ST 的上市 A 股。

不可变业绩预告快照由 `create_forecast_snapshot` 命令和同名 DAG 入口创建。操作员必须显式提供报告期结束日和公告日期起止范围；服务会校验返回行覆盖每一个请求公告日，某天没有提供方记录会作为成功的空覆盖处理。提供方、必需字段、日期归属、数值标准化或持久化失败会把快照运行标记为失败并保留诊断；失败快照和诊断记录不会成为后续候选同步输入。

### 业绩预增社保基金监控同步

每日工作流从公告截止日期不晚于业务日期的已完成不可变业绩预告快照中，确定性选择公告截止日期、完成时间和运行 ID 最新的一个快照。后续同步窗口可以使用较早完成、但公告截止日期不晚于该业务日期的快照；公告截止日期晚于业务日期的快照不会提前激活。它只使用该快照报告期内、业务日期当日或之前每只股票的最新公告；同日重复记录以提供方最后的源顺序为准。候选当前仅支持沪深 A 股代码，且须是当前上市、非 ST，预告类型严格为 `预增`，增长下限为不低于 50 的数值；工作流使用业务日期当日或之前最新的前十大流通股东披露进行既有 SSF 和两个月新鲜度检查。当前上市/ST 判断依赖本地 A 股基础数据快照，若上市状态或名称标记未及时刷新，候选分类也会受该数据时点限制。快照 ID、范围、完成时间、选中的公告和源顺序，以及股东、黑屋和目标审计证据都会保存到 `forecast_ssf_candidates` 表。候选状态包括 `eligible`、`deferred`、`blackroom`、`ineligible`、`delisted_or_unlisted` 和 `paused`；其中 `ineligible` 表示仍在上市但不再符合条件，`delisted_or_unlisted` 表示经上市状态校验后退市或不在上市数据中，退役是非破坏性的，审计记录会保留。

工作流只管理标记为 `workflow: "forecast_ssf_ma20"` 的日频 `close_cross_ma` 目标。`stock-monitor target pause --target-id ...` 会立即禁用该工作流目标，但工作流仍会继续收集审计证据；`stock-monitor target resume --target-id ...` 只解除暂停，目标须在随后一次成功同步中重新满足条件后才会自动启用。缺失或过期的股东证据会产生 `deferred`，不会禁用仍处于活动状态的目标。活跃黑屋、离开合格范围、报告期被更新报告取代，或退市/非上市分类，只会禁用并保留对应的日频工作流目标及其候选链接；手工创建的目标和盘中目标保持不变。禁用、恢复、元数据刷新和候选重连都不会重置目标的 `last_state`，因此一个重新启用时已经位于 MA20 上方的目标不会产生迁移或恢复导致的补告警；只有之后先跌回/等于均线、再以上穿收盘确认，才会产生新的边沿告警。

`close_cross_ma` 使用存储中的前复权（HFQ）日线最终收盘价，不读取实时价格。有效触发必须满足同一 HFQ 序列内的 `previous_close <= previous_ma20` 且 `current_close > current_ma20`；缺失收盘价、少于 `period + 1` 根有效 K 线、最新 K 线日期不等于监控业务日期，或非 A 股日频目标都会被视为数据不足并保留现有状态。

该工作流仅用于研究和监控。它不会下单、不会调整仓位、不会决定买卖数量，也不会替代人工交易执行决策。

### 业绩预增社保基金同步 DAG

`forecast_ssf_ma20_sync` 每个日历日 15:05（`5 15 * * *`）运行，且同一时间只允许一个活跃实例。它只同步由业绩预告和 SSF 证据生成的 `forecast_ssf_ma20` 候选目标，不负责日线完整性检查或监控执行。非交易日跳过同步；`monitor_stock_daily` 仍在 15:30 扫描这些目标。

没有符合条件的已完成快照时，同步服务会在修改候选或目标前失败。已确认不符合条件的工作流目标会被禁用并保留候选链接；暂时无法确认的证据会标记为 `deferred` 并保留目标。

单只股票的生命周期持久化失败不会阻止其他股票完成同步，但会使 DAG 以包含每只失败股票详细信息的结构化错误失败。

### 黑屋管理（全局禁买）

- `stock-monitor blackroom ban --stock-code ... --market ... --ban-days ... [--note ...]`
- `stock-monitor blackroom add --stock-code ... --market ... --ban-days ... [--note ...]`（兼容旧命令，等价于 `ban`）
- `stock-monitor blackroom update --id ... [--ban-days ...] [--note ...] [--enabled|--disabled] [--start-at ...] [--expire-at ...]`
- `stock-monitor blackroom unban --id ...`
- `stock-monitor blackroom unban --stock-code ... --market ...`
- `stock-monitor blackroom remove --id ...`（兼容旧命令，等价于 `unban --id`）
- `stock-monitor blackroom list [--active-only] [--stock-code ...]`
- `stock-monitor blackroom get --id ...`
- `stock-monitor blackroom status`
- `stock-monitor blackroom countdown`
- `stock-monitor blackroom sync-shareholder-selling --start-date ... --end-date ... [--ban-days ...]`

### 状态查询

- `stock-monitor status`

## 输出约定

- 默认：人类可读输出，首行 `CODE: message`，如存在 `data` 则第二行输出 JSON。
- `--json`：输出稳定 JSON 结构：`{"success": bool, "code": str, "message": str, "data": ...}`。
- `target list/get` 默认文本输出使用统一标题：有备注时显示 `股票代码 股票名称 备注`，未指定备注时显示 `股票代码 股票名称 监控条件`。

## 退出码约定

- `0`：成功（`success=true`）
- `10`：参数/校验错误（`code=VALIDATION_ERROR`）
- `11`：资源不存在（`code=NOT_FOUND`）
- `12`：内部错误（`code=INTERNAL_ERROR`、`STORAGE_ERROR` 或未知错误码）

## OpenClaw 接入示例

OpenClaw 可直接通过 shell 调用 CLI，并解析 `--json` 输出：

```bash
poetry run python -m tools.stock_monitor_cli --json target add \
  --stock-code 600519 \
  --market A \
  --condition '{"type":"price_threshold","direction":"below","value":1400}' \
  --frequency daily \
  --reset-mode auto
```

期望：进程退出码 `0`，stdout 为可解析 JSON，例如：

```json
{"success": true, "code": "OK", "message": "target created", "data": {"id": 1}}
```

### 黑屋接入示例

```bash
# 封禁股票进入黑屋（禁买 30 天）
poetry run python -m tools.stock_monitor_cli --json blackroom ban \
  --stock-code 600519 \
  --market A \
  --ban-days 30 \
  --note "股东减持公告"

# 查询黑屋列表（仅有效记录）
poetry run python -m tools.stock_monitor_cli --json blackroom list --active-only

# 按股票代码过滤
poetry run python -m tools.stock_monitor_cli --json blackroom list --stock-code 600519

# 更新记录（禁用）
poetry run python -m tools.stock_monitor_cli --json blackroom update --id 1 --disabled

# 按记录 ID 解禁
poetry run python -m tools.stock_monitor_cli --json blackroom unban --id 1

# 按股票和市场解禁
poetry run python -m tools.stock_monitor_cli --json blackroom unban --stock-code 600519 --market A

# 执行每日倒计时：remaining_days - 1，归零记录会删除
poetry run python -m tools.stock_monitor_cli --json blackroom countdown

# 查询黑屋统计
poetry run python -m tools.stock_monitor_cli --json blackroom status
```

兼容说明：`blackroom add` 仍可用，等价于 `blackroom ban`；`blackroom remove --id ...` 仍可用，等价于 `blackroom unban --id ...`。黑屋相关命令在首次访问存储时会自动补齐 legacy `blackroom_records.remaining_days` 字段，并按已有 `ban_days` 回填旧记录。

### 同步股东减持公告到黑屋（sync-shareholder-selling）

该命令从 Tushare `stk_holdertrade` 拉取股东减持公告（`in_de=DE`），去重后将未被黑屋禁止的标的加入黑屋记录。注意：实际运行需要在环境中设置 TUSHARE_TOKEN。

- 命令：

```bash
# 使用默认禁买天数（180 天），注意 CLI 直接将参数原样传给同步服务
poetry run python -m tools.stock_monitor_cli --json blackroom sync-shareholder-selling \
  --start-date 20240101 \
  --end-date 20240131

# 指定自定义禁买天数（例如 365 天）
poetry run python -m tools.stock_monitor_cli --json blackroom sync-shareholder-selling \
  --start-date 20240201 \
  --end-date 20240229 \
  --ban-days 365
```

- 说明：
- CLI 要求 `--start-date` / `--end-date` 使用 `YYYYMMDD`（如 `20240101`），并将该字符串原样传递给同步服务。同步服务内部会在需要时解析或校验日期格式。
  - 同步过程中会调用黑屋禁买检查，并对未禁买的股票调用 `BlackroomService.ban`（source 字段为 "shareholder_selling"）。
  - 成功时返回 JSON（使用 --json 输出）示例：

```json
{"success": true, "code": "OK", "message": "sync completed", "data": {"fetched": 12, "unique_stocks": 8, "added": 5, "skipped": 3, "records": [{"stock_code":"000001","market":"A","ann_date":"20240115","holder_name":"股东X"}]}}
```

如果未设置 TUSHARE_TOKEN 或发生外部调用错误，命令会返回失败（例如 code 为 STORAGE_ERROR 或 INTERNAL_ERROR）。
