---
name: stock_monitor
description: >
  使用现有 tools/stock_monitor_cli.py 管理监控目标。支持 add/update/remove/list/get/status，
  并统一输出可读结果或 JSON。
triggers:
  - stock monitor
  - 监控目标
  - 股票监控
  - stock_monitor
  - target add
  - target update
  - target remove
  - target list
  - target get
  - monitor status
---

# Stock Monitor CLI Skill

你的任务是把用户的“监控目标管理”请求，稳定映射为 `tools/stock_monitor_cli.py` 的命令调用。

## 执行约束

- 必须在仓库根目录执行命令。
- Python 命令必须使用 `poetry run`。
- 统一调用入口：
  - `poetry run python tools/stock_monitor_cli.py ...`
- 当用户要求结构化输出时，附加 `--json`。

## 命令映射

1. 添加目标
   - `poetry run python tools/stock_monitor_cli.py target add --stock-code <code> --market <A|HK|ETF> --condition '<json>' [--note <text>] [--frequency <freq>] [--reset-mode <mode>] [--disabled] [--last-state] [--json]`
2. 更新目标
   - `poetry run python tools/stock_monitor_cli.py target update --target-id <id> [--stock-code <code>] [--market <A|HK|ETF>] [--condition '<json>'] [--note <text>] [--frequency <freq>] [--reset-mode <mode>] [--enabled|--disabled] [--last-state|--last-state-false] [--json]`
3. 删除目标
   - `poetry run python tools/stock_monitor_cli.py target remove --target-id <id> [--json]`
4. 列表查询
   - `poetry run python tools/stock_monitor_cli.py target list [--frequency <freq>] [--enabled|--disabled] [--json]`
5. 查询单个目标
   - `poetry run python tools/stock_monitor_cli.py target get --target-id <id> [--json]`
6. 状态汇总
   - `poetry run python tools/stock_monitor_cli.py status [--json]`

## 参数与输入规范

- `--condition` 必须是合法 JSON 字符串，优先使用单引号包裹整体，例如：
  - `'{"metric":"price","op":">","value":10}'`
- `target add` 默认启用；需要禁用时使用 `--disabled`。
- `target update` 只传用户明确要改的字段，不要构造隐式默认覆盖。
- 若缺少必填信息（例如 add 缺 `stock_code`、`market`、`condition`，update/get/remove 缺 `target_id`），先向用户补充确认再执行。

## 结果处理

- 直接返回命令输出，保持原始语义。
- 退出码语义：
  - `0`: 成功
  - `10`: VALIDATION_ERROR
  - `11`: NOT_FOUND
  - `12`: INTERNAL_ERROR
- 当命令失败时，明确报告失败原因和对应错误码，不伪造成功。

## 典型示例

```bash
# 添加 A 股监控目标（JSON 输出）
poetry run python tools/stock_monitor_cli.py --json target add \
  --stock-code 000001 \
  --market A \
  --condition '{"metric":"price","op":">","value":12.5}' \
  --note "突破提醒" \
  --frequency daily

# 将目标 7 设置为禁用，并修改备注
poetry run python tools/stock_monitor_cli.py target update \
  --target-id 7 \
  --disabled \
  --note "临时停用"

# 查看当前状态汇总
poetry run python tools/stock_monitor_cli.py --json status
```
