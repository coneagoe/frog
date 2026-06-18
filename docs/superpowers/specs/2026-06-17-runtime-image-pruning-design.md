# Runtime Image Pruning Design

**Goal**

缩小业务运行镜像的代码和依赖边界，让 `app`、`celery-worker`、`paper-trading` 这些运行容器不再包含 `factor/`、`backtest/`、`test/`，并且不再因为本地因子研究依赖 `alphapurify` 而拖慢 Docker 构建。

**Scope**

- 收紧业务运行镜像的 `COPY` 范围。
- 收紧业务运行容器在 `docker-compose.yml` 中的 bind mount 范围。
- 将 `alphapurify` 从主依赖迁移到本地研究专用依赖组。
- 保留 Airflow 开发/调度服务当前的整仓库挂载方式，除非发现它与本次目标直接冲突。
- 不做与镜像边界无关的业务逻辑重构。

## Current State

- `Dockerfile` 当前会把大量仓库目录复制进镜像，其中包括业务运行并不需要的 `backtest/` 和 `factor/`。
- `docker-compose.yml` 中的 `app`、`paper-trading`、`celery-worker` 都通过 `.:/app` 把整仓库重新挂回容器，导致即使镜像层不含某些目录，运行时仍然能看到它们。
- `pyproject.toml` 的主依赖中包含 `alphapurify`，它会连带拉入 `duckdb`、`scikit-learn`、`pyarrow`、`scipy` 等重型依赖。
- Docker 构建时间主要消耗在 `uv sync --frozen --no-dev` 安装这批重型依赖以及其在 Alpine/musl 环境下的下载/构建上。

## Chosen Approach

采用“运行时最小文件集 + 研究依赖分组”的方案：

1. 为业务运行镜像定义最小化文件集，只复制运行时需要的模块和入口文件。
2. 为业务运行容器收紧 bind mount，避免宿主机整仓库把研究目录重新暴露到容器中。
3. 将 `alphapurify` 从默认主依赖移到本地研究专用组，使默认运行镜像不再安装它。
4. 在实施前先做 import 追踪，确认 `task/`、`paper_trading/`、`celery_app.py` 路径下没有对 `factor/`、`backtest/` 的硬依赖，避免盲删目录。

该方案直接命中构建慢的根因，同时保持本地研究工作流可用。

## Architecture

### 1. Runtime Image Boundary

业务运行镜像只应包含以下类别：

- 入口文件：如 `celery_app.py`、`celery_config.py`、`start_celery.sh`、必要配置文件
- 运行时公共模块：如 `common/`、`conf/`、`download/`、`monitor/`、`storage/`、`tools/`、`utility/`
- 业务服务模块：如 `task/`、`paper_trading/`

默认排除这些研究/验证型目录：

- `factor/`
- `backtest/`
- `test/`

若后续 import 追踪显示某个运行路径仍依赖被排除目录，不是直接恢复整目录，而是先判断：

- 这条运行路径是否本就不该出现在业务运行镜像里；或
- 是否应把真正需要的最小公共逻辑抽回到运行时模块中。

### 2. Runtime Compose Boundary

以下服务需要一起收紧运行时文件暴露：

- `app`
- `paper-trading`
- `celery-worker`

当前它们都通过 `.:/app` 获得整仓库访问权限，这会抵消镜像裁剪效果。迁移后，这些服务应满足以下其中一种方式：

1. 不再挂载代码目录，完全使用镜像内代码运行；或
2. 只挂载运行时确实需要的少量配置/数据目录，而不是整仓库。

Airflow 相关服务可继续保留整仓库挂载，因为它们是调度/开发环境，目标不同，不是本次“业务运行镜像最小化”的核心对象。

### 3. Dependency Boundary

- `alphapurify` 不再属于默认主依赖。
- 它迁移到本地研究专用依赖组，例如 `research` 或 `factor`。
- 默认的运行时安装路径不应包含该组，从而避免安装：
  - `duckdb`
  - `pyarrow`
  - `scikit-learn`
  - `scipy`
  - 以及相关重型链路

本地研究工作流则通过显式启用该组来恢复因子分析能力。

### 4. Import-Safety Gate

在真正删减镜像文件集前，需要做 repo 级 import 追踪，重点检查：

- `task/` 是否 import `factor/` 或 `backtest/`
- `paper_trading/` 是否依赖这些目录
- `celery_app.py` 自动发现的任务链是否会触发这些依赖

只有在确认业务运行路径不需要这些目录，或已经完成最小必要抽离后，才执行镜像和 volume 收紧。

## File-Level Plan

### Runtime Packaging

- `Dockerfile`
  - 精简 `COPY` 列表，只保留运行时目录与入口文件。
  - 默认运行依赖安装路径不再包含研究依赖组。

### Compose Runtime Isolation

- `docker-compose.yml`
  - 收紧 `app`、`paper-trading`、`celery-worker` 的 `volumes`。
  - 不再使用 `.:/app` 这种整仓库挂载方式。

### Dependency Grouping

- `pyproject.toml`
  - 将 `alphapurify` 从主依赖移出。
  - 增加研究专用依赖组。
  - 确保默认运行安装不包含该组。

### Verification Support

- 需要新增或调整测试/验证脚本，覆盖：
  - 运行镜像不含研究目录
  - 默认依赖集合不含 `alphapurify`
  - 关键运行服务依然能启动/import

## Constraints

- 不为了裁镜像去修改业务行为。
- 不扩大到 Airflow 镜像重构，除非发现直接阻塞本次目标。
- 不顺手做无关目录清理或依赖升级。
- 研究型工作流仍需保留，只是改为本地显式启用。

## Validation Plan

实现后验证顺序如下：

1. 校验主依赖与研究依赖分组边界。
2. 校验 `Dockerfile` 不再复制 `factor/`、`backtest/`、`test/`。
3. 校验 `docker-compose.yml` 中目标业务服务不再挂 `.:/app`。
4. 构建目标镜像：
   - `docker compose build app`
   - `docker compose build celery-worker`
   - `docker compose build paper-trading`
5. 对关键服务做最小运行验证，确认 import/启动路径完整。

## Risks and Mitigations

### 运行时隐式依赖研究目录

- 风险：某些 Celery 任务或服务模块间接 import `factor/` 或 `backtest/`。
- 缓解：先做 import 追踪，再决定是移除任务职责还是抽离最小公共逻辑，避免直接恢复整目录。

### bind mount 收紧影响开发便利性

- 风险：开发时无法像现在一样实时改代码即在容器中生效。
- 缓解：本次目标聚焦“业务运行容器”；如有需要，可后续单独设计 dev-only compose 覆盖层，而不污染运行时边界。

### 研究依赖分组后本地命令变化

- 风险：本地做因子分析的人需要额外启用研究组。
- 缓解：同步更新 README/文档中的本地研究命令说明。

## Success Criteria

- `app`、`paper-trading`、`celery-worker` 的镜像与运行时都不再暴露 `factor/`、`backtest/`、`test/`。
- 默认运行依赖集合不再包含 `alphapurify`。
- Docker 构建不再因为因子研究依赖链而引入明显的重型安装成本。
- 业务运行路径保持可启动、可 import、可执行。
