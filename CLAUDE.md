# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Frog is a quantitative trading system for Chinese stock markets (A-shares, Hong Kong stocks, ETFs). It uses Apache Airflow for workflow orchestration, PostgreSQL/TimescaleDB for time-series data storage, and supports multiple data sources (akshare, baostock, tushare).

## Development Commands

```bash
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
python3 tools/code_simplifier.py review [files...]
python3 tools/code_simplifier.py review --staged
python3 tools/code_simplifier.py verify
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
