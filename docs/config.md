# 配置说明

你必须在`.env`中配置相关环境变量，否则docker image build时会失败。

## 必填变量

- `TUSHARE_TOKEN`：Tushare API Token（必填，用于数据下载）
  - 获取地址：https://tushare.pro/register
  - 登录后在个人中心获取

## 邮件告警配置

Airflow会通过邮件发送告警。

- `SMTP_HOST`：SMTP 服务器地址（例如：`smtp.qq.com`）
- `SMTP_PORT`：SMTP 端口（例如 QQ 常用 `465`）
- `SMTP_USER`：SMTP 用户名/账号（示例：`2485144732`）
- `SMTP_PASSWORD`：SMTP 密码或授权码（建议使用授权码）
- `SMTP_MAIL_FROM`：发件人邮箱地址（示例：`2485144732@qq.com`）
- `ALERT_EMAILS`：收件人列表（逗号分隔），示例：`a@x.com,b@y.com`
- `AIRFLOW_FERNET_KEY`：Airflow Fernet 加密密钥；所有 Airflow 服务必须使用同一个持久化值，禁止提交真实密钥

示例 `.env`：

```dotenv
TUSHARE_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_MAIL_FROM=xxxxxxxxxx@qq.com
SMTP_USER=xxxxxxxxxx
SMTP_PASSWORD=xxxxxxxxxxxxxxxx
ALERT_EMAILS=xxxxxxxx@xxxxxxx.com
AIRFLOW_FERNET_KEY=<generate-a-fernet-key>
```

注意：**不要**把`.env`添加到repo。

可使用以下命令生成 Fernet 密钥，并将结果写入本地 `.env`：

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

# 环境变量映射关系

对于Airflow：
- `SMTP_HOST` -> `AIRFLOW__SMTP__SMTP_HOST`
- `SMTP_PORT` -> `AIRFLOW__SMTP__SMTP_PORT`
- `SMTP_USER` -> `AIRFLOW__SMTP__SMTP_USER`
- `SMTP_PASSWORD` -> `AIRFLOW__SMTP__SMTP_PASSWORD`
- `SMTP_MAIL_FROM` -> `AIRFLOW__SMTP__SMTP_MAIL_FROM`

另外，程序还会用`utility.send_email`发送邮件，环境变量映射如下：
- `SMTP_HOST` -> `MAIL_SERVER`
- `SMTP_PORT` -> `MAIL_PORT`
- `SMTP_MAIL_FROM` -> `MAIL_SENDER`
- `SMTP_PASSWORD` -> `MAIL_PASSWORD`
- `ALERT_EMAILS` -> `MAIL_RECEIVERS`
