# Airflow Docker Setup

这个 Docker Compose 配置包含了自动权限修复功能，
无需手动设置目录权限。

## 特性

- ✅ 自动权限修复：通过 `airflow-init-permissions` 容器自动设置目录权限
- ✅ 支持自定义 UID：通过环境变量 `AIRFLOW_UID` 配置
  （Airflow 官方镜像要求 `GID=0`，此处已写死为 0）
- ✅ 完整的 Airflow 栈：包含 webserver、scheduler、worker 和数据库

## 使用方法

### 1. 启动服务

注意：启动前请先在仓库根目录配置 `.env`：
- `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`
- `SMTP_MAIL_FROM`、`ALERT_EMAILS`
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

Airflow 2.x 支持在容器内用 CLI 重置密码：

```bash
# 交互式（推荐，不会把密码留在 shell history）
docker compose exec -it airflow-webserver airflow users reset-password --username admin

# 非交互式（会出现在 shell history，请谨慎）
docker compose exec airflow-webserver airflow users reset-password --username admin --password 'REPLACE_WITH_STRONG_PASSWORD'
```

如果你用的不是 `admin` 用户名，把 `--username` 改成实际用户名即可。

### 4. 查看日志

```bash
# 查看所有服务状态
docker compose ps

# 查看 webserver 日志
docker compose logs airflow-webserver

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
更多细节见 [doc/docker.md](doc/docker.md)。

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

- DAG 最多创建 **16** 个分片任务（`p00` ~ `p15`）
- 可以通过environment variable `DOWNLOAD_PROCESS_COUNT` 配置（默认为 2）
- 超出分片数的任务会自动 `skip`

1) 在仓库根目录 `.env` 增加（可选）：

```bash
DOWNLOAD_PROCESS_COUNT=4
```

### 额外说明

- 建议 `DOWNLOAD_PROCESS_COUNT` 不要超过 Celery worker 的实际并发能力（否则会排队，且对 DB/网络压力更大）。
- 周末 QFQ DAG 会先清空表再分片下载（全量重建）。

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
