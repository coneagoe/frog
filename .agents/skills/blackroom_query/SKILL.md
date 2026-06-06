---
name: blackroom_query
description: >
  Use when handling 股票小黑屋 / blackroom 查询或管理请求，例如“在不在小黑屋”、
  blackroom ban、unban、list、get、status、countdown、sync-shareholder-selling。
triggers:
  - 小黑屋
  - blackroom
  - 在不在小黑屋
  - 黑屋查询
  - 黑屋管理
  - blackroom ban
  - blackroom unban
  - blackroom status
  - sync-shareholder-selling
---

# Blackroom Query Skill

你的任务是把用户关于“小黑屋”的自然语言请求，稳定映射为 `tools/stock_monitor_cli.py` 的 `blackroom` 子命令调用。

## 执行约束

- 必须在仓库根目录执行命令。
- Python 命令必须使用 `poetry run`。
- 统一调用入口：
  - `poetry run python tools/stock_monitor_cli.py blackroom ...`
- 当用户要求结构化输出时，附加全局 `--json`。
- 不要绕过 CLI 直接调用 `BlackroomService`。
- 用户只给股票名而未给代码时，默认先补问，不自行猜测代码。

## 常见查询场景

1. 查询单只股票是否在小黑屋
   - 使用：`poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>`
   - 解释规则：返回 `data` 非空表示“在小黑屋”；返回空列表表示“不在小黑屋”。
2. 批量查询多只股票
   - 对每个股票代码分别执行：`poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>`
   - 汇总为逐只结论，不要把多个代码拼成一个 CLI 参数。
3. 查看当前活跃小黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom list --active-only`
4. 查看全部黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom list`
5. 查询单条黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom get --id <record_id>`
6. 查看黑屋状态汇总
   - `poetry run python tools/stock_monitor_cli.py blackroom status`

## 管理命令映射

1. 封禁股票进入小黑屋
   - 主推荐：`poetry run python tools/stock_monitor_cli.py blackroom ban --stock-code <code> --market <A|HK|ETF> --ban-days <days> [--note <text>]`
   - `add` 是兼容旧命令，不作为首选表达。
2. 更新黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom update --id <record_id> [--ban-days <days>] [--note <text>] [--enabled|--disabled] [--start-at <iso>] [--expire-at <iso>]`
3. 按记录 ID 删除
   - `poetry run python tools/stock_monitor_cli.py blackroom remove --id <record_id>`
4. 解除小黑屋封禁
   - 按记录 ID：`poetry run python tools/stock_monitor_cli.py blackroom unban --id <record_id>`
   - 按股票代码和市场：`poetry run python tools/stock_monitor_cli.py blackroom unban --stock-code <code> --market <A|HK|ETF>`
5. 执行剩余天数倒计时
   - `poetry run python tools/stock_monitor_cli.py blackroom countdown`
6. 同步股东减持公告进入小黑屋
   - `poetry run python tools/stock_monitor_cli.py blackroom sync-shareholder-selling --start-date <YYYYMMDD> --end-date <YYYYMMDD> [--ban-days <days>]`

## 参数与补问规则

- 查询“是否在小黑屋”必须有股票代码；未明确市场时默认按 `A` 股处理。
- 用户只给股票名时，先补问股票代码。
- `ban` 必须有 `stock_code`、`market`、`ban_days`。
- `update` 必须有 `record_id`，且至少一个更新字段。
- `unban` 必须满足 `record_id` 或 `stock_code + market` 其中一种。
- `remove` / `get` 必须有 `record_id`。
- `sync-shareholder-selling` 必须有 `start_date`、`end_date`；`ban_days` 不提供时默认 180。

## 结果处理

- 查询类请求可以在命令输出外层补一层简洁结论，例如：`宁德时代(300750)：不在小黑屋`。
- 用户要求 JSON 时，优先返回 CLI 原始 JSON 输出。
- 管理类请求直接返回命令原始语义，不伪造附加业务字段。
- 退出码语义：
  - `0`: 成功
  - `10`: VALIDATION_ERROR
  - `11`: NOT_FOUND
  - `12`: INTERNAL_ERROR / STORAGE_ERROR / 未知内部错误

## 典型示例

```bash
# 查询 300750 是否在小黑屋
poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code 300750

# 查询当前全部活跃小黑屋记录
poetry run python tools/stock_monitor_cli.py blackroom list --active-only

# 封禁 600519 进入小黑屋 30 天
poetry run python tools/stock_monitor_cli.py blackroom ban --stock-code 600519 --market A --ban-days 30 --note "手工封禁"

# 按股票代码解禁
poetry run python tools/stock_monitor_cli.py blackroom unban --stock-code 600519 --market A

# 查询黑屋状态
poetry run python tools/stock_monitor_cli.py --json blackroom status
```
