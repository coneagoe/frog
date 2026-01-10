# Coding Rules / 编码规范（Code Simplifier）

本文档用于配合仓库内的 Copilot Chat 自定义 agents（Code Simplifier / Apply）工作，目标是：**在不改变外部行为（Semantics-Preserving）的前提下提升可读性与可维护性**。

## Scope / 范围

- 默认只处理：
  - 用户明确给出的文件列表（preferred / 优先）；或
  - 用户当前选区（selection）；或
  - 当前变更集（changeset）。
- 若无选区且变更集为空：必须由用户提供目标文件列表后再继续。
- 扩大范围必须获得用户明确同意（例如“可以改动其他文件/重构更多上下文”）。

## Semantics-Preserving / 语义不变

- 最高优先级：**不改变功能、输出、外部接口语义、默认值语义、I/O 副作用、并发/时序行为**。
- 如不确定是否等价：先停下提出问题或保守不改。
- 优先可读性与明确性；避免“为了少几行”引入晦涩技巧。

## Python / 通用规则

- 以仓库现状工具链为硬约束：
  - Python 版本约束见 `pyproject.toml`（CI 使用 3.12）。
  - 风格与检查由 `.pre-commit-config.yaml` 驱动（black/isort/flake8/mypy 等）。
- 推荐做：
  - 减少嵌套与重复，提取清晰的辅助函数（但避免过度拆分导致跳转困难）。
  - 清晰命名（变量/函数/异常信息），让控制流更容易读。
  - 早返回（guard clauses）减少深层缩进。
- 避免做：
  - 过度“聪明”的 one-liner；难 debug 的元编程；隐式魔法默认值。

## Airflow DAG / DAG 规则

- 允许简化结构与命名，但必须保持语义不变：
  - 不改变 schedule、依赖关系、retries、SLA、pool、并发/资源相关配置的行为。
  - 不改变任务的 I/O 副作用（写库、发请求、落文件等）。
  - 不改变任务边界（哪些逻辑在哪个 task 内执行）。

## Docker / Compose / 容器相关

- 允许做：
  - 去重复、合理变量化、提升可读性（例如拆分长命令、显式环境变量）。
- 不允许默认做（除非用户明确要求）：
  - 修改 CI 工作流 `.github/workflows/*`。
  - 修改 `.pre-commit-config.yaml`。

## Config Files（ini/yaml/etc）/ 配置文件

- 允许做：
  - 统一命名、去冗余、补充必要注释（仅当能减少误用）。
- 约束：
  - 不改变默认配置语义与运行时行为。

## Verification Whitelist / 验证白名单（Apply Agent 仅允许执行这些命令）

只允许执行以下三条命令（不启用 autoApprove，每次运行需人工审批）：

- `poetry run pre-commit run --all-files`
- `poetry run pytest test`
- `docker compose config`

说明：本仓库的 mypy/flake8 已集成到 pre-commit 中，无需单独执行 `poetry run mypy` 或 `poetry run flake8`。

## VS Code Usage / 在 VS Code 中使用

- 将自定义 agent 文件放在 `.github/agents/` 下（例如 `code-simplifier.agent.md`），VS Code Copilot Chat 会自动识别并在 agent 选择器中显示。
- 推荐工作流：
  1) 先使用 Code Simplifier（Review）生成 Change List。
  2) 点击 handoff 按钮交给 Code Simplifier Apply（Apply）落地修改并跑白名单验证。
