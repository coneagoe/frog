# Stock Monitor CLI

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

- `{"type":"price_vs_ma","direction":"above","period":20}`：以日线最新收盘价持续高于 20 日简单均线时成立。它不同于 `price_cross_ma`，不要求当天发生上穿。
- 日频 `price_vs_ma` 仅使用同一前复权日线序列的最终收盘价和均线；数据不足时不会改变监控目标的边沿触发状态。
- `{"type":"close_cross_ma","direction":"above","period":20}`：仅适用于 A 股日频监控，读取截至监控业务日期的存储前复权日线最终收盘价，要求真实发生 MA20 向上穿越；数据不足或过期时保留监控状态。

### 业绩预告数据

Tushare `forecast` 数据可经 `DownloadManager.download_forecast(ann_date=...)` 下载并保存到 `forecasts` 表。保存数据会标准化沪深 A 股代码及公告/报告期日期；候选查询只返回当前报告期内最新公告、类型为 `预增`、增长下限不低于 50%、且当前为非 ST 的上市 A 股。

### 业绩预增社保基金监控同步

每日工作流使用既有的合格业绩预告、活跃黑屋过滤和既有 SSF 检测器生成监控候选，并将业绩预告、股东、黑屋及目标的审计证据保存到 `forecast_ssf_candidates` 表。候选状态包括 `eligible`、`deferred`、`blackroom`、`ineligible`、`delisted_or_unlisted` 和 `paused`；其中 `ineligible` 表示仍在上市但不再符合条件，`delisted_or_unlisted` 表示经上市状态校验后退市或不在上市数据中，退休是非破坏性的，审计记录会保留。

工作流只管理标记为 `workflow: "forecast_ssf_ma20"` 的日频目标。`stock-monitor target pause --target-id ...` 会立即禁用该工作流目标，但工作流仍会继续收集审计证据；`stock-monitor target resume --target-id ...` 只解除暂停，目标须在随后一次成功同步中重新满足条件后才会自动启用。缺失或过期的股东证据会产生 `deferred`，不会禁用仍处于活动状态的目标。活跃黑屋、离开合格范围、报告期被更新报告取代，或退市/非上市分类，只会禁用对应的日频工作流目标；手工创建的目标和盘中目标保持不变。

### 业绩预增社保基金同步 DAG

`forecast_ssf_ma20_sync` 每个日历日 15:05（`5 15 * * *`）运行，且同一时间只允许一个活跃实例。它只同步由业绩预告和 SSF 证据生成的 `forecast_ssf_ma20` 候选目标，不负责日线完整性检查或监控执行。非交易日跳过同步；`monitor_stock_daily` 仍在 15:30 扫描这些目标。

同步服务对已确认不符合条件的工作流目标执行删除，但保留候选证据；暂时无法确认的证据会标记为 `deferred` 并保留目标。

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
