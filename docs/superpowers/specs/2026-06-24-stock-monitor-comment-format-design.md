# Stock Monitor Comment Format Design

## Background

`stock monitor` 当前在不同输出路径里对监控目标的人类可读标题有不一致风险：

- 告警展示路径会在 `note/comment` 与 `condition` 之间做回退。
- CLI 的 `target list/get` 也会单独拼接人类可读文本。

这次变更要统一规则：

- 如果指定了 `comment`，显示 `股票代码 股票名称 comment`
- 如果没有指定 `comment`，显示 `股票代码 股票名称 监控条件`

本次只改人类可读展示，不改数据库结构、命令参数语义、JSON 输出结构。

## Goals

- 统一告警展示与 CLI 人类可读输出的标题格式。
- 将格式规则收敛到单一共享实现，避免未来漂移。
- 保持现有 `--json` 输出稳定，避免影响脚本调用方。

## Non-Goals

- 不修改 `target` 的存储字段定义。
- 不新增 CLI 参数。
- 不调整监控条件的业务含义。
- 不修改黑屋（blackroom）相关输出。

## Recommended Approach

在监控模块内新增一个共享的人类可读标题格式化函数，输入监控目标展示所需字段，输出稳定标题字符串。所有需要展示“股票代码 股票名称 xxx”的地方都改为调用它，而不是各自拼字符串。

推荐原因：

- 变更范围小，符合当前需求。
- 告警与 CLI 共享同一规则，可靠性更高。
- 不把展示逻辑下沉到存储层，职责更清晰。

## Formatting Rules

共享格式化函数遵循以下规则：

1. 基础前缀始终为 `股票代码 股票名称`。
2. 当 `comment` 有值时，末尾使用 `comment`。
3. 当 `comment` 缺失时，末尾使用监控条件的人类可读文本。
4. `comment` 的“缺失”定义包括：`None`、空字符串、仅包含空白字符。
5. 最终输出格式为单行，字段之间使用单个空格分隔。

示例：

- `600519 贵州茅台 突破提醒`
- `600519 贵州茅台 price_threshold below 1400`

## Component Changes

### Shared Formatter

新增或抽取一个共享的格式化函数，职责仅限于生成监控目标的人类可读标题：

- 输入：`stock_code`、`stock_name`、`condition`、`note/comment`
- 输出：单个标题字符串

该函数不做：

- 数据库存取
- CLI 参数解析
- JSON 序列化

### CLI Output

`tools/stock_monitor_cli.py` 中 `target list/get` 的默认文本输出改为调用共享格式化函数。

约束：

- 只修改人类可读输出路径。
- `--json` 输出字段和值保持不变。

### Alert Rendering

`monitor/monitor_runner.py` 中告警标题，以及任何当前直接依赖 `note or condition` 的等价展示位置，统一改为调用共享格式化函数。

约束：

- 仅统一标题/展示文案来源。
- 不调整告警触发逻辑。
- 若正文里仍需要单独展示 `备注` 与 `触发条件`，保留现有语义。

## Condition Fallback Source

当 `comment` 缺失时，回退值必须来自当前系统已有的监控条件人类可读表示，而不是新的自定义格式。

如果 CLI 与告警路径当前使用了不同的条件文本转换方式，本次顺手统一为同一个来源，以确保用户在不同入口看到一致的条件描述。

## Error Handling

- 如果 `comment` 为空白字符串，先做去空白判断，再决定是否回退到条件文本。
- 如果 `stock_name` 在既有数据流中本就可为空，则继续沿用当前上游保障方式；本次不新增兜底命名策略。
- 共享格式化函数不吞掉异常；上层保持现有错误处理行为。

## Testing Strategy

本次变更按 TDD 执行，先补测试，再改实现。

### CLI Tests

新增或调整 `target list/get` 相关测试，覆盖：

- 指定 `comment` 时，文本输出为 `代码 名称 comment`
- 未指定 `comment` 时，文本输出为 `代码 名称 condition`
- `comment` 为空字符串或仅空白时，回退为 `condition`
- `--json` 输出结构和字段保持不变

### Alert / Runner Tests

新增或调整告警渲染测试，覆盖：

- 告警标题使用统一格式化结果
- 有 `comment` 时优先显示 `comment`
- 无 `comment` 或空白 `comment` 时回退显示 `condition`

## Impact

- 用户在 CLI 文本输出和告警里看到一致的人类可读标题。
- 依赖 `--json` 的脚本和自动化流程不受影响。
- 后续如果再新增展示入口，可直接复用该共享格式化函数。

## Implementation Notes

- 优先在已有监控模块中放置共享函数，避免新建不必要文件。
- 尽量复用现有条件文本格式化逻辑，不引入新的 condition 文案格式。
- 文档仅在存在受影响示例输出时最小更新。
