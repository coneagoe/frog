# 配置说明（Airflow / Email）

本项目使用 Docker Compose 启动 Airflow。邮件告警（`email_on_failure`）与项目内的 `utility.send_email` 均通过环境变量配置。

> 重点：Compose 不会自动读取 `.secrets/smtp_password.txt` 去填变量；它只会读取项目根目录的 `.env` 来做 `${VAR}` 插值。

## 1. 邮件配置（必填，来自 .env）

在项目根目录创建/编辑 `.env`（与 `docker-compose.yml` 同级），填写以下变量：

- `SMTP_HOST`：SMTP 服务器地址（例如：`smtp.qq.com`）
- `SMTP_PORT`：SMTP 端口（例如 QQ 常用 `465`）
- `SMTP_USER`：SMTP 用户名/账号（示例：`2485144732`）
- `SMTP_PASSWORD`：SMTP 密码或授权码（建议使用授权码）
- `SMTP_MAIL_FROM`：发件人邮箱地址（示例：`2485144732@qq.com`）
- `ALERT_EMAILS`：收件人列表（逗号分隔），示例：`a@x.com,b@y.com`

示例 `.env`：

```dotenv
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_MAIL_FROM=2485144732@qq.com
SMTP_USER=2485144732
SMTP_PASSWORD=xxxxxxxxxxxxxxxx
ALERT_EMAILS=coneagoe@hotmail.com
```

## 2. 为什么“没配置就 build 失败”

`docker-compose.yml` 里使用了 Compose 的必填变量语法 `${VAR:?message}`。因此只要缺少任何必填变量（例如 `SMTP_PASSWORD`），在执行 `docker compose build`/`docker compose config`/`docker compose up` 时都会直接失败，并提示缺少哪个变量。

你可以用下面命令快速检查是否配置齐全：

```bash
# 仅检查配置/插值是否能通过
docker compose config
```

## 3. Airflow 邮件与项目邮件的变量映射

在 `docker-compose.yml` 中，我们把 `.env` 的值同时映射到：

- Airflow SMTP 配置（让 `email_on_failure` 真正发信）
  - `AIRFLOW__SMTP__SMTP_HOST`  <- `SMTP_HOST`
  - `AIRFLOW__SMTP__SMTP_PORT`  <- `SMTP_PORT`
  - `AIRFLOW__SMTP__SMTP_USER`  <- `SMTP_USER`
  - `AIRFLOW__SMTP__SMTP_PASSWORD` <- `SMTP_PASSWORD`
  - `AIRFLOW__SMTP__SMTP_MAIL_FROM` <- `SMTP_MAIL_FROM`

- DAG 告警收件人（DAG 内读取）
  - `ALERT_EMAILS`（以及 `MAIL_RECEIVERS`） <- `ALERT_EMAILS`

- 项目内 `utility.send_email` 兼容变量（如果你仍会运行 Celery/脚本发送邮件）
  - `MAIL_SERVER` <- `SMTP_HOST`
  - `MAIL_PORT` <- `SMTP_PORT`
  - `MAIL_SENDER` <- `SMTP_MAIL_FROM`
  - `MAIL_PASSWORD` <- `SMTP_PASSWORD`
  - `MAIL_RECEIVERS` <- `ALERT_EMAILS`

## 4. 生成密码（从 secret 文件写入 .env 的可选方式）

如果你已经把授权码写在 `.secrets/smtp_password.txt`，可以把它追加进 `.env`：

```bash
# 追加 SMTP_PASSWORD（如果已存在请先手动删除旧行）
printf '\nSMTP_PASSWORD=%s\n' "$(cat .secrets/smtp_password.txt)" >> .env
```

> 注意：Compose 不会自动读取 `.secrets/smtp_password.txt`。你必须把 `SMTP_PASSWORD` 放进 `.env`（或改成使用 Compose secrets 的方式）。

## 5. 安全建议

- 不建议把真实 `SMTP_PASSWORD` 提交到 Git。
- 推荐把 `.env`、`.secrets/` 加入 `.gitignore`（如果尚未加入）。
- QQ 邮箱建议使用“SMTP 授权码”而不是登录密码。
