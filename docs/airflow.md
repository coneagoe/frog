# Airflow Docker Setup

这个 Docker Compose 配置包含了自动权限修复功能，
无需手动设置目录权限。

## 特性

- ✅ 自动权限修复：通过 `airflow-init-permissions` 容器自动设置目录权限
- ✅ 支持自定义 UID：通过环境变量 `AIRFLOW_UID` 配置
  （Airflow 官方镜像要求 `GID=0`，此处已写死为 0）
- ✅ 完整的 Airflow 3 栈：包含 API server、scheduler、dag processor、worker 和数据库

## 使用方法

### 1. 启动服务

注意：启动前请先在仓库根目录配置 `.env`：
- `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`
- `SMTP_MAIL_FROM`、`ALERT_EMAILS`
- `AIRFLOW_FERNET_KEY`（必填；用于所有 Airflow 服务统一加密连接凭据）
否则 `docker compose` 会提示 “is required” 并退出。

同时建议在 `.env` 里配置 Airflow 管理员账号密码（首次初始化时使用）：

- `AIRFLOW_ADMIN_USERNAME`（默认 `admin`）
- `AIRFLOW_ADMIN_PASSWORD`（必填；不要使用弱口令）
- `AIRFLOW_ADMIN_EMAIL`（可选；默认 `admin@example.com`）

说明：这些变量只会在一次性初始化容器 `airflow-init`（profile `init`）里用于创建管理员用户。

```bash
# 仅首次部署/新库时：初始化 DB + 创建管理员用户
docker compose --profile init up --abort-on-container-exit airflow-init

# 正常启动所有服务
docker compose up -d
```

### 2. 访问 Airflow UI

- URL: http://localhost:8080

登录信息：

- 用户名：`AIRFLOW_ADMIN_USERNAME`（默认 `admin`）
- 密码：首次初始化时设置的 `AIRFLOW_ADMIN_PASSWORD`

> !注意
> 如果你已经启动过并且数据库里已存在用户，修改 `.env` 里的 `AIRFLOW_ADMIN_PASSWORD` 不会自动修改旧用户的密码；需要用下面的“重置密码”命令。

### 3. 重置/修改 Airflow 密码

Airflow 3.x 使用 API server 容器内的 CLI 重置密码：

```bash
# 交互式（推荐，不会把密码留在 shell history）
docker compose exec -it airflow-apiserver airflow users reset-password --username admin

# 非交互式（会出现在 shell history，请谨慎）
docker compose exec airflow-apiserver airflow users reset-password --username admin --password 'REPLACE_WITH_STRONG_PASSWORD'
```

如果你用的不是 `admin` 用户名，把 `--username` 改成实际用户名即可。

### 4. 查看日志

```bash
# 查看所有服务状态
docker compose ps

# 查看 API server 日志
docker compose logs airflow-apiserver

# 查看权限初始化日志
docker compose logs airflow-init-permissions
```

### 5. 停止服务

```bash
docker compose down
```

说明：数据库数据保存在 Docker named volume `db_data` 中，
重建镜像不会丢数据；请勿使用：
- `docker compose down -v/--volumes`
- `docker system prune --volumes`
否则会删除数据卷导致数据丢失。
更多细节见 [docker.md](docker.md)。

### 6. 手动创建业绩预告快照

在 Airflow UI 手动触发 `create_forecast_snapshot` DAG，并在运行配置中填写公告日期范围：

```json
{
  "report_end_date": "2026-06-30",
  "announcement_start_date": "2026-07-01",
  "announcement_end_date": "2026-07-31"
}
```

该 DAG 只处理显式指定的范围，不会改变现有的滚动业绩预告下载或回填任务。

## 工作原理

1. **权限初始化容器** (`airflow-init-permissions`):
   - 使用 `busybox` 镜像以 root 权限运行
   - 创建必要的目录结构
   - 将 `logs/`、`plugins/`、`dags/` 目录的所有权设置为 `1000:0`
     （UID 可通过 `AIRFLOW_UID` 覆盖；GID 固定为 0）
   - 在所有 Airflow 服务启动前完成

2. **依赖关系**:
   - 所有 Airflow 服务都依赖于权限初始化容器
   - 确保权限修复在服务启动前完成

## 自定义配置

如果需要使用不同的 UID，可以设置环境变量：

```bash
export AIRFLOW_UID=1000
docker compose up -d
```

## 下载任务并发（股票历史）

由于不能在 Celery task 里发起多进程（否则会触发 `daemonic processes are not allowed to have children`），所以我们用 **Airflow 分片并行**：

- 分片数不再由 DAG 级 `MAX_PARTITIONS` 控制，而是统一读取共享的 `DOWNLOAD_PROCESS_COUNT`
- `DOWNLOAD_PROCESS_COUNT` 是唯一配置来源；未设置时默认值为 `4`
- 已迁移的 DAG 会在解析时冻结当前分片数，并通过 `op_kwargs` 显式传给分片任务和港股汇总任务，避免 scheduler 与 worker 分别导入 DAG 时出现分片数漂移

1) 在仓库根目录 `.env` 增加（可选）：

```bash
DOWNLOAD_PROCESS_COUNT=4
```

### 额外说明

- 建议 `DOWNLOAD_PROCESS_COUNT` 不要超过 Celery worker 的实际并发能力（否则会排队，且对 DB/网络压力更大）。
- 周末 QFQ DAG 会先清空表再分片下载（全量重建）。

### A 股日线日期语义

- `download_stock_history_weekdays` 当前按 `Asia/Shanghai` 时区于每个工作日 `18:00` 运行，以便在 Baostock 收盘数据通常可用后再执行 BFQ/HFQ 下载和 EOD 模拟交易匹配。
- A 股 BFQ/HFQ 日线 DAG 从 Airflow `context['logical_date']` 转换为 `Asia/Shanghai` 后，只派生一个业务日期，并将同一日期作为两类下载的 `end_date`；周末及非交易日会跳过。`data_interval_end` 仅表示数据区间右边界，不作为该工作流的交易业务日期。
- 汇总完成后，EOD 模拟交易匹配也使用这个相同的显式日期。
- 其余仍按墙上时钟运行的路径包括：周末 QFQ 历史 DAG、`daily_basic`/`stk_limit`/`suspend_d` DAG，以及调用方未传 `end_date` 时 `DownloadManager` 的通用回退逻辑。

### A 股 BFQ 统一缺口恢复（Issue #113）

Issue #123 将该恢复任务扩展到 HK Connect BFQ 缺口，不改变其调度、依赖、重试或任务边界。HK 自动恢复仅在目标日期 HK Connect 日历、日期限定普通股资格、明确非停牌状态和新鲜 authority 证据均满足时执行；任一证据未知或过期都会跳过写入并保留重试/升级路径。恢复按市场路由 provider 和行情存储：A 股使用六位代码，HK Connect 使用五位代码和 HK provider fallback。每个 provider 必须返回目标日期唯一行情行，恢复会执行市场限定的精确读回并拒绝重复或冲突记录；候选、尝试和告警证据保留 authority、停牌和实际 provider 信息。

每日 BFQ/HFQ 全部分片完成后，日线汇总允许成功或带警告的下载结果继续进入模拟交易匹配；匹配成功（包括带逐证券 warning 的完成状态）后，DAG 再运行统一的普通 A 股 BFQ 精确日期缺口恢复。任一分片或匹配任务失败都会使恢复任务跳过，不会把不完整的批次当作可恢复输入。单个证券的 provider、写入或匹配 warning 不会阻断其他证券继续处理。

恢复按证券缺口幂等执行：已有精确 BFQ 数据的缺口会被标记为已解决，未解决缺口可独立重试，不会重复写入已恢复的行情行。每次批次、尝试及缺口摘要都会保留 routing/classification 和 provider/结果证据，便于审计和重试。阈值升级、不可变候选记录、待浏览器审批、告警及账户修复均属于匹配后的恢复流程；升级候选在审批前不会自动写入行情。

## 每日监控与黑屋任务

`monitor_stock_daily` 每天 15:30 运行一次。DAG 中的每日股票监控任务仍会在非 A 股交易日自动跳过；股东减持公告同步黑屋任务不受交易日限制，会在每个 DAG 运行日执行，并使用当前 Airflow logical date 作为 Tushare 查询日期。黑屋剩余天数倒计时任务在股东减持同步之后执行，并允许在每日股票监控被跳过时继续运行。

## 数据库连接管理

### Storage 层（业务数据）

`storage.get_storage()` 使用 **PID-scoped singleton** 模式：
- 每个进程维护自己的 `StorageDb` 实例和 SQLAlchemy 连接池
- 避免多进程共享连接导致的冲突
- 避免每次调用都创建新引擎/连接池导致的 "too many clients already"

SQLAlchemy 连接池默认设置（可通过环境变量覆盖）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STORAGE_DB_POOL_SIZE` | 1 | 每个进程的连接池大小 |
| `STORAGE_DB_MAX_OVERFLOW` | 0 | 超出 pool_size 后允许的额外连接数 |
| `STORAGE_DB_POOL_RECYCLE` | 1800 | 连接回收时间（秒） |
| `STORAGE_DB_POOL_PRE_PING` | true | 使用连接前检测是否存活 |

### Celery Result Backend

Celery task 状态/结果存储在 **Redis**（DB index 1），而非 Postgres：
- Broker: `redis://redis:6379/0`
- Result Backend: `redis://redis:6379/1`

这样做可以减少 Postgres 连接压力。注意：
- Redis 未配置持久化，重启后 task 结果会丢失
- Airflow metadata（DAG runs, task instances 等）仍存储在 Postgres
- 业务数据（股票历史等）仍通过 storage 层写入 Postgres

## 故障排除

如果遇到权限问题：

1. 检查权限初始化容器日志：
   ```bash
   docker compose logs airflow-init-permissions
   ```

2. 手动验证权限：
   ```bash
   ls -la logs/ plugins/ dags/
   ```

3. 如果你之前运行导致宿主机目录 owner/group 被改坏（例如 DAG 无法编辑），
   可在宿主机执行一次：
   ```bash
   sudo chown -R $(id -u):$(id -g) dags logs plugins
   ```
