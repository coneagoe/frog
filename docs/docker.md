# Dockerfile
- `airflow.Dockerfile`：用于构建Airflow docker image（固定基于 Airflow 2.9.2）

# 环境变量设置
参见`config.md`。

# 启动与访问

在仓库根目录执行：
- 启动：`docker compose up -d`
- 查看状态：`docker compose ps`

注：不要使用 `apache/airflow:slim-latest-*` 这类浮动 tag；仓库默认固定在 Airflow 2.9.2。

## 访问Airflow UI
参见`airflow.md`

# 停止与重启

- 停止（保留data volumn）：`docker compose down`
- 重启：`docker compose restart`

# 数据持久化

## 数据存在哪里

数据库服务 `db` 把数据目录挂载到 Docker **named volume**：

- 卷名：`db_data`
- 容器内路径：`/var/lib/postgresql/data`

这意味着：

- 重新构建镜像（`docker compose build` 或 `docker compose up -d --build`）不会影响数据库数据。
- 只要不删除data volumn `db_data`，DB 文件就一直存在。

## 哪些命令会导致数据丢失

以下命令会删除 named volume（包含 `db_data`），从而造成数据库数据丢失：

- `docker compose down -v`
- `docker compose down --volumes`

此外，清理命令也可能删除“未使用”的 volume（在栈停掉时尤其危险）：

- `docker system prune --volumes`

## 备份与恢复
用如下脚本import/export DB：
- `tools/db_export.sh`
- `tools/db_import.sh`
