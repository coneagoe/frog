# 小黑屋查询与管理 skill 设计

## 背景

仓库已经具备完整的小黑屋能力：

- 业务服务在 `monitor/blackroom_service.py`。
- CLI 入口在 `tools/stock_monitor_cli.py` 的 `blackroom` 子命令。
- 已有 `stock_monitor` skill 负责监控目标管理，但没有单独面向“小黑屋查询/管理”的 skill。

当前常见需求是自然语言查询“某几只股票在不在小黑屋里”，以及后续的封禁、解禁、列表、同步等运维操作。

## 目标

新增一个 repo-local skill，把用户关于“小黑屋”的自然语言请求稳定映射到现有 CLI：

```bash
poetry run python tools/stock_monitor_cli.py blackroom ...
```

设计目标：

- 查询优先：优先覆盖“是否在小黑屋”“当前有哪些活跃记录”等高频场景。
- 管理完整：同时覆盖 `ban`、`unban`、`update`、`remove`、`status`、`countdown`、`sync-shareholder-selling`。
- 不新增业务逻辑，不绕过现有 CLI。
- 保持与现有 `.agents/skills/stock_monitor/SKILL.md` 风格一致。

## 推荐位置

推荐新增：

```text
.agents/skills/blackroom_query/
  SKILL.md
```

skill 名称建议使用 `blackroom_query`，文件夹名与 frontmatter `name` 保持一致。

## 职责边界

### skill 负责的事

- 识别用户意图：查询、封禁、解禁、更新、列表、状态、倒计时、股东减持同步。
- 把自然语言请求映射成正确 CLI 命令。
- 缺关键参数时先补问，不盲猜。
- 需要结构化输出时追加 `--json`。
- 返回 CLI 原始语义，查询场景可在结果外层补一层简洁说明。

### skill 不负责的事

- 不直接调用 `BlackroomService`，统一走 CLI。
- 不重写“小黑屋判断”逻辑。
- 不自动提供投资建议。
- 不默认做股票简称到代码的猜测映射。

## 命令入口约束

- 必须在仓库根目录执行。
- Python 命令必须使用 `poetry run`。
- 统一入口：

```bash
poetry run python tools/stock_monitor_cli.py blackroom ...
```

- 用户要求 JSON 时，使用：

```bash
poetry run python tools/stock_monitor_cli.py --json blackroom ...
```

## 推荐命令映射

### 查询类

#### 查询单只股票是否在小黑屋

现有 CLI 没有单独 `check` 子命令，skill 统一通过活跃列表过滤实现：

```bash
poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>
```

解释规则：

- 返回 `data` 非空：在小黑屋。
- 返回 `data` 为空列表：不在小黑屋。

#### 批量查询多只股票

对每个股票代码逐只执行：

```bash
poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>
```

然后聚合为简洁结论。

#### 查看当前活跃小黑屋记录

```bash
poetry run python tools/stock_monitor_cli.py blackroom list --active-only
```

#### 查看全部黑屋记录

```bash
poetry run python tools/stock_monitor_cli.py blackroom list
```

#### 查询单条黑屋记录

```bash
poetry run python tools/stock_monitor_cli.py blackroom get --id <record_id>
```

#### 查看状态汇总

```bash
poetry run python tools/stock_monitor_cli.py blackroom status
```

### 管理类

#### 封禁股票进入小黑屋

skill 主推荐 `ban`，不主推兼容别名 `add`：

```bash
poetry run python tools/stock_monitor_cli.py blackroom ban --stock-code <code> --market <A|HK|ETF> --ban-days <days> [--note <text>]
```

#### 更新黑屋记录

```bash
poetry run python tools/stock_monitor_cli.py blackroom update --id <record_id> [--ban-days <days>] [--note <text>] [--enabled|--disabled] [--start-at <iso>] [--expire-at <iso>]
```

#### 按记录 ID 删除

```bash
poetry run python tools/stock_monitor_cli.py blackroom remove --id <record_id>
```

#### 解除封禁

按记录 ID：

```bash
poetry run python tools/stock_monitor_cli.py blackroom unban --id <record_id>
```

按股票代码 + 市场：

```bash
poetry run python tools/stock_monitor_cli.py blackroom unban --stock-code <code> --market <A|HK|ETF>
```

### 运维类

#### 执行剩余天数倒计时

```bash
poetry run python tools/stock_monitor_cli.py blackroom countdown
```

#### 同步股东减持公告进入小黑屋

```bash
poetry run python tools/stock_monitor_cli.py blackroom sync-shareholder-selling --start-date <YYYYMMDD> --end-date <YYYYMMDD> [--ban-days <days>]
```

## 参数补问规则

### 查询类

- “查某只/多只股票是否在小黑屋”：必须有 `stock_code`。
- `market` 未提供时，默认按 `A` 股处理，并在 skill 中写明该默认行为。
- “查单条记录”：必须有 `record_id`。
- “查列表 / 查状态”：无需补问，直接执行。

### 管理类

- `ban`：必须有 `stock_code`、`market`、`ban_days`。
- `update`：必须有 `record_id`，且至少一个更新字段。
- `unban`：必须满足 `record_id` 或 `stock_code + market` 二选一。
- `remove`：必须有 `record_id`。
- `sync-shareholder-selling`：必须有 `start_date`、`end_date`；`ban_days` 可缺省，默认 180。

## 名称与代码处理策略

采用保守策略：

- 优先使用用户明确提供的股票代码。
- 用户只给股票名时，默认先补问，不自行猜测代码。
- 用户同时给了名称和代码时，以代码为准。
- 如果名称与代码明显不一致，可提醒一次，再按用户最终确认结果执行。

这样可以避免简称冲突、口误或误封/误查。

## 输出策略

### 查询类

查询类在保留 CLI 原始语义的前提下，可补充一层简洁结论，例如：

- `宁德时代(300750)：不在小黑屋`
- `某股票(XXXXXX)：在小黑屋`

如果用户明确要求 JSON，则直接返回原始 JSON 或基于原始 JSON 的稳定汇总结构。

### 管理类

管理类直接返回 CLI 原始输出语义，不额外发明新的业务字段。

### 错误码

沿用现有 CLI 约定：

- `0`：成功
- `10`：`VALIDATION_ERROR`
- `11`：`NOT_FOUND`
- `12`：`INTERNAL_ERROR` / `STORAGE_ERROR` / 未知内部错误

## 推荐文档结构

`SKILL.md` 建议按以下顺序组织：

1. frontmatter（`name`、`description`、必要触发词）
2. 概览
3. 执行约束
4. 常见查询场景
5. 管理命令映射
6. 参数补问规则
7. 输出与错误处理
8. 典型示例

这样可以保证：

- 前半部分优先服务“查询”高频场景。
- 后半部分完整覆盖日常黑屋管理。

## 与现有 skill 的关系

- `stock_monitor` 继续负责监控目标管理与通用状态查询。
- 新 skill 专注“小黑屋”语义，不混入监控目标的 `target add/update/remove/list/get/status`。
- 两者都复用 `tools/stock_monitor_cli.py`，风格保持一致。

## 验证

实现 skill 后至少验证：

1. 查询单只股票是否在小黑屋时，是否映射到 `blackroom list --active-only --stock-code`。
2. 查询多只股票时，是否逐只查询并正确汇总。
3. `ban` / `unban` / `update` / `status` / `countdown` / `sync-shareholder-selling` 的命令模板是否准确。
4. 缺关键参数时，skill 是否先补问而不是盲猜。
5. 股票名但无代码时，skill 是否遵循保守策略。

如果后续需要提高“股票名直接查询”的易用性，应设计独立的名称解析能力，而不是把猜测逻辑写进本 skill。
