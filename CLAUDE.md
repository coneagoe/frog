# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Frog is a quantitative trading system for Chinese stock markets (A-shares, Hong Kong stocks, ETFs). It uses Apache Airflow for workflow orchestration, PostgreSQL/TimescaleDB for time-series data storage, and supports multiple data sources (akshare, baostock, tushare).

## Development Commands

```bash
# Docker operations
docker compose up -d                          # Start all services
docker compose down                           # Stop all services
docker compose logs -f [service]              # Follow logs for a service
docker compose exec [service] bash            # Enter a service shell
docker compose restart [service]              # Restart a service
docker compose build --no-cache               # Rebuild images
docker compose ps                             # List running services

# Environment setup
poetry install --with dev
poetry run pre-commit install

# Code quality
poetry run pre-commit run --all-files        # Run all checks on tracked files
poetry run black .                           # Format code
poetry run isort .                           # Sort imports
poetry run flake8 --max-line-length=120      # Linting
poetry run mypy                              # Type checking

# Testing
poetry run pytest test                       # Run all tests

# Code simplifier (for refactoring existing code)
# python3 tools/code_simplifier.py review [files...]
# python3 tools/code_simplifier.py review --staged
# python3 tools/code_simplifier.py verify
```


## Architecture

### Data Flow

```
Data Sources (akshare/baostock/tushare)
    ↓
Download Manager (download/)
    ↓
Storage Layer (storage/ - PostgreSQL/TimescaleDB)
    ↓
Analysis & Backtesting (indicator/, backtest/)
    ↓
Trading Strategies (trigger/)
    ↓
Workflow Orchestration (dags/ - Airflow DAGs)
```

### Key Components

**Market Abstraction (core/)**
- Uses registry pattern for multi-market support
- `IMarket` / `BaseMarket` define the interface all markets must implement
- `market_registry.py` manages market registration and retrieval
- Markets are auto-registered in `core/__init__.py`

**Download System (download/)**
- `DownloadManager` coordinates multiple data sources
- Supports akshare, baostock, tushare APIs
- Handles retry logic and error recovery

**Storage Layer (storage/)**
- SQLAlchemy-based abstraction over PostgreSQL
- TimescaleDB extension for time-series data optimization

**Airflow DAGs (dags/)**
- Scheduled data collection tasks
- `dags/common_dags.py` contains shared utilities for all DAGs:
  - `get_default_args()` - DAG default arguments with email alerting
  - `get_partition_count()` - Read from env or Airflow Variable
  - `get_partitioned_ids()` - Subset stock IDs for parallel execution
  - `get_alert_emails()` - Parse ALERT_EMAILS or MAIL_RECEIVERS env vars

### Code Simplification Rules

When simplifying code (per `doc/coding_rule.md`):

- **Semantics-Preserving**: Never change external behavior, outputs, I/O side effects, or timing
- **Scope**: Only modify files explicitly provided by user or current changeset
- **Airflow DAGs**: Never change schedule, dependencies, retries, SLA, or task boundaries
- **Verification Whitelist**: Only run these commands for validation:
  - `poetry run pre-commit run --all-files`
  - `poetry run pytest test`
  - `docker compose config`

### Type Checking

Mypy has relaxed exclusions for legacy code:
- `app.*`, `stock.*`, `fund.*`, `tools.*`, `frog_server`
- Third-party: `akshare.*`, `retrying.*`, `baostock.*`, `tushare.*`
- `backtest.deprecate.*`

When working in these directories, be aware type checking is disabled.

### Airflow Container Context

Airflow mounts code at `/opt/airflow/frog`. DAGs handle this via:
```python
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
```

This sys.path manipulation is in `dags/common_dags.py`.

## Docker Architecture

### Services

| Service | Image | Purpose | Ports |
|---------|-------|---------|-------|
| `db` | timescale/timescaledb:latest-pg16 | PostgreSQL + TimescaleDB (quant + airflow databases) | 127.0.0.1:5432:5432 |
| `redis` | redis:7-alpine | Celery broker + result backend | internal only |
| `app` | built from Dockerfile | Application container for manual tasks | none |
| `airflow-webserver` | frog-airflow:2.9.2-python3.12 | Airflow UI | 8080:8080 |
| `airflow-scheduler` | frog-airflow:2.9.2-python3.12 | Airflow scheduler | none |
| `airflow-worker` | frog-airflow:2.9.2-python3.12 | Airflow Celery worker | none |
| `airflow-init` | frog-airflow:2.9.2-python3.12 | One-time admin user creation | none |
| `db-init-airflow` | postgres:16-alpine | Ensures airflow metadata DB exists | none |
| `airflow-init-permissions` | busybox:latest | Fix log/plugin/DAG directory permissions | none |

### Volumes

| Volume | Mount Point | Purpose |
|--------|-------------|---------|
| `db_data` | /var/lib/postgresql/data | PostgreSQL persistent data |
| `./dags` | /opt/airflow/dags | Airflow DAG definitions |
| `./logs` | /opt/airflow/logs | Airflow task logs |
| `./plugins` | /opt/airflow/plugins | Airflow plugins |
| `./` | /opt/airflow/frog | Project code (read-only in containers) |
| `./docker/postgres/init` | /docker-entrypoint-initdb.d | PostgreSQL init scripts |

### Required Environment Variables (.env)

```bash
# Email/Alerting (required)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_password
SMTP_MAIL_FROM=alerts@example.com
ALERT_EMAILS=recipient1@example.com,recipient2@example.com

# Tushare API token (required)
TUSHARE_TOKEN=your_tushare_token_here

# Airflow admin (optional - defaults to admin/admin)
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=change_me_in_production
AIRFLOW_ADMIN_FIRSTNAME=Admin
AIRFLOW_ADMIN_LASTNAME=User
AIRFLOW_ADMIN_EMAIL=admin@example.com

# Airflow secrets (optional - change for production)
AIRFLOW__WEBSERVER__SECRET_KEY=frog_airflow_secret_key_change_me

# Airflow user (optional - default 1000)
AIRFLOW_UID=1000

# Download parallelism (optional - default 4)
DOWNLOAD_PROCESS_COUNT=4
```

### Database Configuration

- **Airflow Metadata DB**: `airflow` (created by `db-init-airflow`)
- **Business Data DB**: `quant`
- **Connection Strings**:
  - Airflow metadata: `postgresql+psycopg2://quant:quant@db:5432/airflow`
  - Business data: `postgresql://quant:quant@db:5432/quant`
- **Max Connections**: 200 (increased from default to handle Airflow + workers)

### Airflow Configuration

- **Executor**: CeleryExecutor
- **Celery Broker**: `redis://redis:6379/0`
- **Celery Result Backend**: `redis://redis:6379/1` (reduces Postgres connection pressure)
- **Worker Concurrency**: 2 (prevents Postgres connection exhaustion)
- **Timezone**: Asia/Shanghai
- **Connection Pool**:
  - Pool size: 5
  - Max overflow: 0
  - Pool recycle: 1800s
- **Task Queued Timeout**: 6 hours (21600s) - handles long queues when worker concurrency < partitions
- **DAG Bag Import Timeout**: 120s
- **Stale DAG Threshold**: 300s
