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

```bash
# 启动所有服务
docker compose up -d

# 如需显式初始化（可选）
docker compose run --rm airflow-init
```

### 2. 访问 Airflow UI

- URL: http://localhost:8080
- 用户名: admin
- 密码: admin

### 3. 查看日志

```bash
# 查看所有服务状态
docker compose ps

# 查看 webserver 日志
docker compose logs airflow-webserver

# 查看权限初始化日志
docker compose logs airflow-init-permissions
```

### 4. 停止服务

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
