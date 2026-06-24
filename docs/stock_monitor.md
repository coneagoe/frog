# Stock Monitor CLI

## 管理命令入口

统一入口：`stock-monitor`

### 目标管理

- `stock-monitor target add --stock-code ... --market ... --condition ...`
- `stock-monitor target update --target-id ... [--stock-code ...] [--market ...] [--condition ...] [--note ...] [--frequency ...] [--reset-mode ...] [--enabled|--disabled] [--last-state|--last-state-false]`
- `stock-monitor target remove --target-id ...`
- `stock-monitor target list [--frequency daily|intraday] [--enabled|--disabled]`
- `stock-monitor target get --target-id ...`

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
