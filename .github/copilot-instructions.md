# Copilot Instructions for `frog`

## Build, test, and lint commands

- Use `poetry run` for Python commands in this repository. Do not use bare `python` or `python3` for project tasks.
- Install dev dependencies: `poetry install --with dev`
- Install hooks once: `poetry run pre-commit install`
- Run repository checks: `poetry run pre-commit run --all-files`
- Run checks for touched files only: `poetry run pre-commit run --files <path1> <path2>`
- Format: `poetry run black .`
- Sort imports: `poetry run isort .`
- Lint: `poetry run flake8 --max-line-length=120`
- Type-check: `poetry run mypy`
- Run the full test suite: `poetry run pytest test`
- Run a test file: `poetry run pytest test/download/test_download_manager.py`
- Run a single test: `poetry run pytest test/download/dl/test_downloader.py::TestDownloader::test_dl_general_info_stock`
- Run focused subsystem tests when working in those areas, e.g. `poetry run pytest test/dags/test_common_dags.py` or `poetry run pytest test/monitor/test_monitor_runner.py`
- Build container images: `docker compose build`
- Start the local stack: `docker compose up -d`
- Validate compose config: `docker compose config`

## High-level architecture

- This repository is a quantitative trading system for A-shares, Hong Kong stocks, and ETFs. The main runtime layers are data download, storage, orchestration, monitoring, and backtesting.
- `conf/global_settings.py` is the main config bootstrap. Many scripts, backtests, and Celery tasks call `conf.parse_config()` first; it reads `config.ini`, populates environment variables, and creates expected local data directories.
- `download/` is the ingestion layer. `download/dl/` contains source-specific downloader adapters for providers such as AkShare, BaoStock, and TuShare, and `download/download_manager.py` coordinates full and incremental downloads before handing DataFrames to storage.
- `download/dl/downloader.py` is the provider switchboard: the `Downloader` class exposes a stable set of `dl_*` methods while delegating each method to the current provider-specific implementation.
- `storage/` is the persistence layer. `storage/model/` defines table models and table-name constants, while `storage/storage_db.py` is the central PostgreSQL/TimescaleDB access layer used across the project.
- `storage/__init__.py` re-exports `get_storage()`, `reset_storage()`, `get_table_name()`, and commonly used table-name constants, so most code imports storage APIs from the package root rather than from internal modules.
- `dags/` contains Airflow orchestration. Shared behavior lives in `dags/common_dags.py`, which sets up import paths, default DAG args, alert email handling, and task partitioning through `DOWNLOAD_PROCESS_COUNT`.
- DAGs usually build one task per active partition and then process per-security loops inside each task rather than dynamically mapping every security into its own Airflow task.
- `task/` contains Celery entrypoints for long-running jobs and backtest-style workflows. `celery_app.py` wires Redis as broker/backend and autodiscovers tasks from `task/`.
- Some `task/` modules shell out to script-style entrypoints in `tools/` or `backtest/` and then trigger follow-up work or email notifications. Treat those as orchestration wrappers around existing scripts, not as the place where core business logic lives.
- `monitor/` is a separate alerting flow: it loads persisted monitoring targets, fetches current and recent price data, evaluates conditions, and sends edge-triggered email alerts.
- `monitor/price_fetcher.py` reads historical series from storage but uses EastMoney real-time prices for current quotes, so monitor changes often span both storage-backed history and live fetch behavior.
- `backtest/` contains many script-style strategy runners that operate on downloaded/stored market data rather than a single unified application service.
- Deployment/runtime wiring is in `docker-compose.yml`: PostgreSQL/TimescaleDB for business data, Redis for Celery/Airflow coordination, and Airflow with `CeleryExecutor`.

## Key conventions

- Prefer the actual current code layout (`download/`, `storage/`, `dags/`, `task/`, `monitor/`, `backtest/`) when reasoning about architecture.
- Configuration usually enters through `conf.parse_config()` rather than ad hoc environment setup.
- Storage access is built around a PID-scoped singleton in `storage/storage_db.py`; use `reset_storage()` in tests when shared storage state must be cleared.
- Airflow code assumes the project may be mounted at `/opt/airflow/frog`; DAG helpers also honor `FROG_PROJECT_ROOT` when resolving imports.
- `DOWNLOAD_PROCESS_COUNT` controls DAG partition fan-out. `dags/common_dags.py` treats the environment variable as the source of truth and falls back to `4`.
- Command and task names use underscores rather than hyphens.
- Chinese comments, messages, and column names are common and acceptable in this codebase.
- When changing DAGs, avoid altering schedules, retries, dependencies, task boundaries, or SLA behavior unless the user explicitly asks for that.
- Prefer preserving the existing script-style entrypoints in `tools/`, `task/`, and `backtest/`; many of them are invoked by subprocess from other modules.
- Tests commonly patch provider/storage integrations instead of making live network calls. Prefer `monkeypatch` or targeted mocks around AkShare, BaoStock, TuShare, Redis, and storage helpers.
- Some tests manipulate `sys.path` explicitly to import repo modules or DAG helpers; follow the local test pattern instead of normalizing every test to one import style.
