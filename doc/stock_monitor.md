# Stock Monitor CLI

## 管理命令入口

统一入口：`stock-monitor`

### 目标管理

- `stock-monitor target add --stock-code ... --market ... --condition ...`
- `stock-monitor target update --target-id ... [--stock-code ...] [--market ...] [--condition ...] [--note ...] [--frequency ...] [--reset-mode ...] [--enabled|--disabled] [--last-state|--last-state-false]`
- `stock-monitor target remove --target-id ...`
- `stock-monitor target list [--frequency daily|intraday] [--enabled|--disabled]`
- `stock-monitor target get --target-id ...`

### 状态查询

- `stock-monitor status`

## 输出约定

- 默认：人类可读输出，首行 `CODE: message`，如存在 `data` 则第二行输出 JSON。
- `--json`：输出稳定 JSON 结构：`{"success": bool, "code": str, "message": str, "data": ...}`。

## 退出码约定

- `0`：成功（`success=true`）
- `10`：参数/校验错误（`code=VALIDATION_ERROR`）
- `11`：资源不存在（`code=NOT_FOUND`）
- `12`：内部错误（`code=INTERNAL_ERROR` 或未知错误码）
