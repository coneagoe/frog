# HK OBOS 集成到 Airflow DAG 设计

## 背景

当前 `task/obos_hk.py` 以 Celery task 的形式存在，职责是：

1. 读取 `download_hk_ggt_history_daily` 写入 Redis 的下载结果。
2. 判断港股当日是否开市。
3. 执行 `backtest/obos_hk_9.py`。
4. 根据执行结果发送邮件。

现在希望把这段能力放到 Airflow 执行链路里，并在 `dags/download_hk_ggt_history_daily.py` 成功后自动触发。

## 目标

1. 让 `obos_hk` 在 Airflow 容器内运行，而不是依赖独立的 Celery task 入口。
2. 仅当 `download_hk_ggt_history_daily` 的下载分片和聚合任务成功后，才执行 `obos_hk`。
3. 保留现有 Redis 检查、开市判断、回测执行和邮件通知行为。
4. 让 `obos_hk` 具备独立的 Airflow task 日志、失败状态和重跑能力。

## 非目标

1. 不调整 `download_hk_ggt_history_daily` 的调度时间、分片数量、重试策略或 task 边界。
2. 不修改 `backtest/obos_hk_9.py` 的业务逻辑。
3. 不把 `obos_hk` 拆成新的独立 DAG。

## 方案对比

### 方案 A：在 DAG 中新增独立 task（采用）

在 `download_hk_ggt_history_daily` 中新增一个 `PythonOperator`，放在 `aggregate_results` 后面执行。将 `task/obos_hk.py` 的核心逻辑迁移为 Airflow 可直接调用的普通函数，由该 operator 调用。

优点：

- 依赖关系清晰：只在上游成功后触发。
- Airflow UI 中可单独查看日志、状态和重跑。
- 与现有 DAG 的“分片下载 -> 聚合结果”结构一致。

缺点：

- 需要把 Celery task 形式改造成 DAG 调用形式。

### 方案 B：在 `aggregate_results` 内联调用

把 `obos_hk` 的逻辑直接塞进 `aggregate_and_save_result()`。

优点：

- 改动最少。

缺点：

- 聚合和回测邮件混在一个 task 中，日志和失败原因不易区分。
- 单独重跑回测时必须连带重跑聚合。

### 方案 C：DAG 调用原 `task/obos_hk.py`

保留 `task/obos_hk.py`，由 DAG 用导入或 subprocess 方式调用。

优点：

- 迁移量较小。

缺点：

- Airflow 与 Celery 两套任务边界同时存在，职责分散。
- DAG 仍然依赖一个为 Celery 设计的入口，不够直接。

## 详细设计

### 代码放置

`task/obos_hk.py` 中的业务逻辑迁移到 Airflow 可直接使用的位置，优先做法是在 `dags/download_hk_ggt_history_daily.py` 内新增专用函数，例如：

- `run_obos_hk_backtest()`
- `build_obos_hk_command()`

迁移后不再依赖 `@app.task` 装饰器，也不再通过 `.delay()` 触发。

这样可以保证逻辑与当前 DAG 紧密绑定，避免引入新的公共抽象；如果后续有第二个 DAG 需要复用，再考虑提炼到公共模块。

### DAG 依赖

保持现有依赖不变：

`partition_tasks >> aggregate_results`

在此基础上新增：

`aggregate_results >> run_obos_hk`

这意味着：

- 任一分片失败时，聚合 task 不会成功，`run_obos_hk` 不会执行。
- 聚合 task 成功后，`run_obos_hk` 才会进入调度。

### Airflow 容器中的运行方式

Airflow 服务当前已经通过 `docker-compose.yml` 将整个仓库挂载到 `/opt/airflow/frog`，并设置：

- `PYTHONPATH=/opt/airflow/frog`
- `FROG_PROJECT_ROOT=/opt/airflow/frog`

因此 `backtest/obos_hk_9.py` 和相关模块在 Airflow 容器内天然可见，不需要为这次变更额外调整镜像构建逻辑。

`run_obos_hk` 中执行回测时，子进程命令应避免硬编码 `"python"`，改用当前解释器路径（如 `sys.executable`），以确保与 Airflow 运行环境一致。

### 运行逻辑

`run_obos_hk` 的执行顺序如下：

1. 调用 `conf.parse_config()` 初始化配置。
2. 读取 Redis 中的 `REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY`。
3. 若 Redis 记录不存在或结果不是 `success`，显式跳过 task。
4. 若港股当日休市，显式跳过 task。
5. 计算日期区间并执行 `backtest/obos_hk_9.py`。
6. 成功时发送成功邮件并返回结果。
7. 失败时发送失败邮件，并让 Airflow task 失败。

这里的“显式跳过”采用 Airflow 的 skip 语义，而不是简单返回字符串，以便在 UI 中明确表现为 `skipped`。

### 错误处理

错误处理遵循以下规则：

- 上游下载失败：由 Airflow 依赖关系保证 `run_obos_hk` 不运行。
- Redis 不可读、回测命令返回非 0、邮件发送相关异常：让 `run_obos_hk` task 失败并暴露错误。
- 可预期的非执行条件（例如 Redis 结果非 success、当日休市）：抛出 `AirflowSkipException`。

这样可以避免“看起来成功，实际没有执行”的静默失败。

### 对现有脚本的处理

`task/obos_hk.py` 的处理目标是“迁移出 task 入口”，即不再把它作为主执行路径。实现时优先选择以下方式之一：

1. 直接删除该文件，并把逻辑完全迁入 DAG。
2. 若当前仓库仍有其他入口依赖它，则将其改为薄包装并复用新函数。

本次实现会先检查 `task/__init__.py` 与其他调用点；只有在确认无必要保留时才删除旧入口。

## 测试设计

需要补充或更新以下验证：

1. DAG 结构测试：
   - 存在新的 `run_obos_hk` task。
   - `aggregate_results` 是 `run_obos_hk` 的直接上游。
2. 逻辑测试：
   - Redis 返回非 success 时，任务被跳过。
   - 市场休市时，任务被跳过。
   - 回测成功时发送成功邮件。
   - 回测失败时发送失败邮件并抛出异常。

测试应继续使用 pytest 和 mock/monkeypatch，避免真实 Redis、真实邮件和真实回测执行。

## 实施步骤

1. 梳理 `task/obos_hk.py` 的现有依赖和调用点。
2. 将核心逻辑迁移为 Airflow 可直接调用的函数。
3. 在 `download_hk_ggt_history_daily` 中新增 `run_obos_hk` operator 和依赖。
4. 清理或瘦身旧的 `task/obos_hk.py` 入口。
5. 补充针对 DAG 依赖和运行逻辑的测试。

## 风险与控制

### 风险 1：Airflow 与旧 Celery 入口并存导致行为分叉

控制方式：让 DAG 使用的新函数成为唯一核心实现，旧入口如需保留，只做透传。

### 风险 2：回测失败被误标记为成功

控制方式：子进程返回非 0 时抛出异常，不再返回成功形态的字符串。

### 风险 3：环境解释器不一致

控制方式：使用当前 Python 解释器执行回测脚本，而不是硬编码命令名。
