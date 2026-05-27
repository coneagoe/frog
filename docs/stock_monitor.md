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

- `stock-monitor blackroom add --stock-code ... --market ... --ban-days ... [--note ...]`
- `stock-monitor blackroom update --id ... [--ban-days ...] [--note ...] [--enabled|--disabled] [--start-at ...] [--expire-at ...]`
- `stock-monitor blackroom remove --id ...`
- `stock-monitor blackroom list [--active-only] [--stock-code ...]`
- `stock-monitor blackroom get --id ...`
- `stock-monitor blackroom status`

### 状态查询

- `stock-monitor status`

## 输出约定

- 默认：人类可读输出，首行 `CODE: message`，如存在 `data` 则第二行输出 JSON。
- `--json`：输出稳定 JSON 结构：`{"success": bool, "code": str, "message": str, "data": ...}`。

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
# 添加黑屋记录（禁买 30 天）
poetry run python -m tools.stock_monitor_cli --json blackroom add \
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

# 删除记录
poetry run python -m tools.stock_monitor_cli --json blackroom remove --id 1

# 查询黑屋统计
poetry run python -m tools.stock_monitor_cli --json blackroom status
```
