# Copilot Instructions for `frog`

## Build, test, and lint commands

- Use `poetry run` for Python commands in this repository. Do not use bare `python` or `python3`.
- Install dev dependencies: `poetry install --with dev`
- Install hooks once: `poetry run pre-commit install`
- Run all tracked-file checks: `poetry run pre-commit run --all-files`
- Run checks for touched files only: `poetry run pre-commit run --files <path1> <path2>`
- Format: `poetry run black .`
- Sort imports: `poetry run isort .`
- Lint: `poetry run flake8 --max-line-length=120`
- Type-check: `poetry run mypy`
- Run the full test suite: `poetry run pytest test`
- Run a verbose test sweep: `poetry run pytest -v test`
- Run a single test file: `poetry run pytest test/download/test_download_manager.py`
- Run a single test: `poetry run pytest test/download/dl/test_downloader.py::TestDownloader::test_dl_general_info_stock`
- Run focused subsystem tests when changing those areas, e.g. `poetry run pytest test/dags/test_common_dags.py` or `poetry run pytest test/monitor/test_monitor_runner.py`
- Validate compose config: `docker compose config`
- Build container images: `docker compose build`
- Start the local stack: `docker compose up -d`
- CI currently installs with Poetry, runs `poetry run pre-commit run --all-files`, and then `poetry run pytest test` on Python 3.12.

## High-level architecture

- Frog is a quantitative trading system for A-shares, Hong Kong stocks, and ETFs. The big-picture flow is: provider APIs (`akshare` / `baostock` / `tushare`) -> `download/` ingestion -> `storage/` persistence -> analysis/backtest/trigger logic -> Airflow/Celery orchestration and monitoring.
- `core/` provides the market abstraction layer (`IMarket`, `BaseMarket`, registry-based market lookup) that the rest of the system builds on.
- `conf/global_settings.py` is the main bootstrap path. Many scripts, backtests, and Celery tasks call `conf.parse_config()` first so `config.ini` values become environment variables and expected local data directories are created.
- `download/download_manager.py` coordinates full and incremental downloads, while `download/dl/downloader.py` is the provider switchboard that exposes stable `dl_*` methods and delegates to provider-specific implementations.
- `storage/storage_db.py` is the central PostgreSQL/TimescaleDB access layer. `storage/model/` defines table models and table-name constants, and `storage/__init__.py` re-exports the storage entrypoints most modules consume.
- `dags/common_dags.py` carries the shared Airflow contract: import-path bootstrapping, alert email parsing, default DAG args, and partition fan-out via `DOWNLOAD_PROCESS_COUNT`.
- DAGs usually create one task per active partition and then loop over security IDs inside each task rather than creating one Airflow task per security.
- `celery_app.py` wires Redis as broker/backend and autodiscovers jobs from `task/`; many `task/` modules are orchestration wrappers around script-style entrypoints in `tools/` or `backtest/`.
- `monitor/price_fetcher.py` mixes storage-backed historical reads with TuShare realtime fetches, so monitoring changes often cross the storage/live-data boundary.
- `docker-compose.yml` is the runtime wiring for local deployment: TimescaleDB/Postgres for data, Redis for Celery/Airflow coordination, and Airflow running with `CeleryExecutor`.

## Key conventions

- Prefer the actual runtime layout (`core/`, `download/`, `storage/`, `dags/`, `task/`, `monitor/`, `backtest/`) when reasoning about changes.
- Configuration usually enters through `conf.parse_config()` rather than ad hoc environment setup.
- Storage access is a PID-scoped singleton in `storage/storage_db.py`; use `reset_storage()` in tests when shared storage state must be cleared.
- Most code should import storage helpers from `storage` package exports rather than reaching into internal modules.
- Airflow code assumes the repo may be mounted at `/opt/airflow/frog`; DAG helpers also honor `FROG_PROJECT_ROOT` when resolving imports.
- `DOWNLOAD_PROCESS_COUNT` is the source of truth for DAG partition fan-out; `dags/common_dags.py` falls back to `4`.
- Preserve existing script-style entrypoints in `tools/`, `task/`, and `backtest/`; other modules may shell out to them.
- Tests usually patch provider/storage integrations instead of using live AkShare, BaoStock, TuShare, Redis, or database calls. Some tests also manipulate `sys.path` explicitly; follow the local pattern in that area.
- Mypy is intentionally relaxed for legacy areas such as `app.*`, `stock.*`, `fund.*`, `tools.*`, and `backtest.deprecate.*`; keep new code type-aware, but do not force broad refactors in excluded modules.
- Repository-local Copilot skills live under `.agents/skills/`, and custom agent definitions live under `.github/agents/`.
- Command and task names use underscores rather than hyphens.
- Chinese comments, messages, and column names are common and acceptable in this codebase.
- The repo enforces LF line endings via `.gitattributes`; `pre-commit` only runs on staged files during `git commit`, and the trailing-whitespace fixer excludes `*.csv`.
- When changing DAGs, avoid altering schedules, retries, dependencies, task boundaries, or SLA behavior unless explicitly requested.
