# Poetry to uv and Ruff Migration Design

**Goal**

将仓库从 Poetry 彻底迁移到 uv，并用 Ruff 统一替代 Black、isort、Flake8，覆盖本地开发、pre-commit、CI、Docker 与开发者文档中的全部相关入口。

**Scope**

- 全仓库迁移，不保留 Poetry 作为并行入口。
- 依赖管理、锁文件、代码质量工具、命令示例、CI 与 Docker 全部切换。
- 不改业务逻辑，不顺带做无关重构。

## Current State

- `pyproject.toml` 已采用 `[project]` 描述主依赖，但构建后端与开发依赖仍保留 Poetry 专属配置。
- 仓库当前通过 `poetry.lock` 锁定依赖，通过 `poetry install --with dev` 安装开发环境。
- 代码质量工具分散在 `black`、`isort`、`flake8`、`mypy` 与 `pre-commit` 上。
- CI、Docker、README 及多处文档/提示文本仍直接使用 `poetry` 命令。

## Chosen Approach

采用一次性迁移方案：

1. 使用 `uv` 作为唯一依赖与命令执行入口。
2. 删除 Poetry 专属配置与 `poetry.lock`。
3. 增加 `uv` 所需锁文件与依赖分组配置。
4. 用 Ruff 统一接管格式化、导入排序和基础静态检查。
5. 保留 `pytest`、`mypy`、`pre-commit`，仅迁移它们的安装与执行入口。

该方案虽然一次性改动面较大，但能避免仓库长期处于“双工具链”状态，减少后续维护和认知负担。

## Architecture

### 1. Dependency Management

- `uv` 成为唯一环境同步工具，统一使用：
  - `uv sync`
  - `uv sync --group dev`
  - `uv run <command>`
- `pyproject.toml` 继续以 `[project]` 作为依赖定义中心。
- 现有 `[tool.poetry.group.dev.dependencies]` 迁移为 `uv` 兼容的开发依赖分组。
- Poetry 专属构建后端与元数据删除，构建系统切换为标准、最小化且与当前非打包模式相容的配置。
- 现有镜像源配置从 `[[tool.poetry.source]]` 迁移为 `uv` 可识别的索引配置，保持当前阿里云/腾讯/清华镜像的意图不变。

### 2. Lockfile Strategy

- 删除 `poetry.lock`。
- 生成并提交 `uv.lock`。
- CI、Docker、本地开发全部只依赖 `uv.lock`，不再维护 Poetry 锁文件。

### 3. Lint and Format Consolidation

- `black` → `ruff format`
- `isort` → Ruff import sorting（`I` 规则）
- `flake8` → `ruff check`
- `mypy` 继续保留，配置与排除范围尽量不变。

Ruff 配置原则：

- 行宽保持 `120`，与当前 Black/Flake8 约束一致。
- 导入排序行为尽量贴近现有 `isort` + `black` 组合。
- 初始阶段只启用实现当前替代目标所必需的规则，避免引入与本次迁移无关的大规模风格震荡。

### 4. Execution Surfaces

以下入口全部统一改为 `uv`：

- 本地开发命令
- pre-commit hooks
- GitHub Actions CI
- Docker build/runtime 安装流程
- README 与开发文档中的命令示例
- 代码中的用户提示字符串（例如缺少依赖时的安装提示）

## File-Level Plan

### Core Configuration

- `pyproject.toml`
  - 删除 Poetry 专属构建和依赖定义。
  - 增加 `uv` 开发依赖分组与索引配置。
  - 增加 Ruff 配置。
  - 保留并尽量原样延续 `pytest`、`mypy` 等现有工具配置。
- `uv.lock`
  - 新增，作为唯一锁文件。
- `poetry.lock`
  - 删除。

### Developer Tooling

- `.pre-commit-config.yaml`
  - 移除 Black、isort、Flake8 hooks。
  - 改为 Ruff format + Ruff check hooks。
  - 保留 mypy hook。

### CI

- `.github/workflows/ci.yml`
  - 移除 Poetry 安装与缓存逻辑。
  - 替换为 uv 安装、缓存与依赖同步。
  - 全部命令改为 `uv run ...`。

### Docker

- `Dockerfile`
  - 移除 Poetry 安装。
  - 安装 uv。
  - 复制 `uv.lock` 与 `pyproject.toml`。
  - 使用 `uv sync` 或等价方式安装运行所需依赖。
  - 避免引入虚拟环境路径问题，确保容器中的命令执行模型清晰一致。

### Docs and Command References

- `README.md`
  - 将安装与 pre-commit 说明改为 uv。
- 仓库内所有面向开发者的文档和说明
  - 将 `poetry install` / `poetry run` / `black` / `isort` / `flake8` 示例统一替换为 uv/Ruff 版本。
- 代码中的错误提示/帮助文本
  - 若文案写死 Poetry 命令，同步替换。

## Constraints

- 不修改业务行为。
- 不调整 DAG 调度、依赖、重试、任务边界或 SLA。
- 不借机扩大 Ruff 规则集来做额外清理。
- 不强制重写现有 mypy 例外范围。
- 保持 Python 版本约束为 `>=3.11,<3.13`。

## Validation Plan

验证由 Orchestrator 在实现后执行，顺序如下：

1. `uv sync --group dev`
2. `uv run pre-commit run --all-files`
3. `uv run pytest test`
4. `uv run ruff check .`
5. `uv run ruff format --check .`
6. `uv run mypy`
7. Docker 镜像构建验证

优先接受“与本次迁移直接相关”的失败并修复；若出现与现有遗留问题无关的既有失败，只记录并说明，不扩大处理范围。

## Risks and Mitigations

### uv 索引配置与 Poetry 不同

- 风险：镜像源迁移方式不当会导致依赖解析异常。
- 缓解：显式梳理当前 `[[tool.poetry.source]]` 意图，按 uv 支持的配置方式落地，并通过一次完整 `uv sync --group dev` 验证。

### Ruff 与原 Flake8/Black/isort 存在细微差异

- 风险：pre-commit 或 CI 中出现额外格式/规则变更。
- 缓解：仅启用等价替代所需的最小规则集合，先追求兼容，再追求收紧。

### 文档与提示文本分布零散

- 风险：遗留 `poetry` 命令，导致仓库对外说明不一致。
- 缓解：做一次仓库级全文检索，覆盖 README、docs、脚本帮助文本与代码内安装提示。

### Docker 中的环境路径差异

- 风险：从 Poetry 切到 uv 后，容器里的命令执行路径或虚拟环境位置变化，导致运行失败。
- 缓解：选择清晰、单一的容器安装模式，并通过镜像构建及基本启动验证确认最终行为。

## Success Criteria

- 仓库不再依赖 Poetry。
- `poetry.lock` 被移除，`uv.lock` 成为唯一锁文件。
- `black`、`isort`、`flake8` 不再作为仓库主工具链出现。
- `ruff format` + `ruff check` 成为统一格式化与基础静态检查入口。
- CI、Docker、README、pre-commit、文档命令示例全部切换到 uv/Ruff。
- 目标验证命令能在当前仓库环境中跑通，或仅暴露与本次迁移无关的既有问题。
