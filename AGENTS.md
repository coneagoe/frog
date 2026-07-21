# Project Guidelines

## Command Rules
- Critical: use `uv run` for Python commands in this repo. Do not use bare `python` or `python3` for project tasks.
- Repository-local agent skills live under `.agents/skills/`; the commit workflow invokes `update_doc` before committing.
- Command and task names use underscores (`_`), not hyphens (`-`).
- Docker Compose commands:
  ```bash
  docker compose up -d                 # Start local services
  docker compose down                  # Stop local services
  docker compose logs -f <service>     # Follow service logs
  docker compose exec <service> bash   # Open a service shell
  docker compose restart <service>     # Restart a service
  docker compose build --no-cache      # Rebuild images
  docker compose ps                    # List service status
  docker compose config                # Validate Compose configuration
  ```

## Build And Test
```bash
uv sync --group dev
uv run pre-commit install

# CI gates, in order
uv run pre-commit run --all-files
uv run pytest test

# Focused checks
uv run ruff format .
uv run ruff check .
uv run mypy

# Single test
uv run pytest test/path/to/test_file.py::TestClass::test_method

# Focused subsystem test examples
uv run pytest test/dags/test_common_dags.py
uv run pytest test/monitor/test_monitor_runner.py
```

## Architecture
- `download/`: data source orchestration (akshare, baostock, tushare) via `DownloadManager` and `download/dl/downloader.py` (the provider switchboard).
- `storage/`: SQLAlchemy-based persistence for PostgreSQL/TimescaleDB; singleton via `get_storage()`, reset with `reset_storage()`.
- `conf/global_settings.py` is the bootstrap entrypoint: `conf.parse_config()` reads `config.ini` into env vars and is called by many scripts/tasks.
- `dags/`: Airflow orchestration; shared helpers in `dags/common_dags.py` (import bootstrap via `FROG_PROJECT_ROOT` or `/opt/airflow/frog`, alert parsing, partition fan-out).
- `task/`: Celery task wrappers around `tools/` and `backtest/` entrypoints; wired via `celery_app.py`.
- `core/`: market abstraction layer; `IMarket`/`BaseMarket` define the market interface, while `market_registry.py` manages registration and lookup. Markets are auto-registered in `core/__init__.py`.
- `monitor/price_fetcher.py`: combines storage-backed historical data with TuShare real-time data; monitoring changes can cross the storage/live-data boundary.
- `docker-compose.yml`: local runtime wiring for TimescaleDB/Postgres, Redis, and Airflow with `CeleryExecutor`.
- End-to-end data flow: provider APIs -> `download/` -> `storage/` -> analysis/backtest -> triggers -> Airflow/Celery orchestration and monitoring.

## Conventions
- Python 3.11+ (CI targets 3.12). Formatting/import sorting/linting: Ruff; type checking: mypy.
- uv `package = false`; tests set `pythonpath = ["."]`, so imports rely on the repo root rather than an installed package.
- Chinese comments/messages and Chinese column names are common and acceptable.
- Commit messages must be written in English.
- Generate commit-message subjects from the core diff; use the body for concrete changes rather than a generic summary.
- Storage tables: when adding or removing, update `tools/db_common.sh` so `db_export.sh`/`db_import.sh` stay in sync.
- LF line endings enforced via `.gitattributes`; `pre-commit` runs on staged files only; trailing-whitespace fixer excludes `*.csv`.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA unless explicitly requested.
- Code simplification/refactoring tasks must follow `docs/coding_rule.md`; keep that file as the source of truth instead of duplicating its full contents here.
- Prefer the repository's runtime layout (`core/`, `download/`, `storage/`, `dags/`, `task/`, `monitor/`, `backtest/`) when reasoning about changes.
- Initialize configuration through `conf.parse_config()` rather than ad hoc environment setup.
- Prefer storage helpers exported by `storage` over imports from its internal modules.
- `DOWNLOAD_PROCESS_COUNT` controls DAG partition fan-out and defaults to `4` in `dags/common_dags.py`.
- Preserve script-style entrypoints in `tools/`, `task/`, and `backtest/`; other modules may invoke them.

## Testing Patterns
- Mock external providers (`akshare`, `baostock`, `tushare`) instead of live calls.
- Many tests manipulate `sys.path` explicitly:
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
```
- Storage singleton must be reset in tests via `reset_storage()` when shared state needs clearing.

## Type Checking Scope
- Mypy is intentionally relaxed for legacy areas: `app.*`, `stock.*`, `fund.*`, `tools.*`, `backtest.deprecate.*`, and third-party libs without stubs (`akshare`, `retrying`, `baostock`, `tushare`). See `pyproject.toml` for full overrides.
- Keep changes type-aware where checking is enabled; do not force large refactors in excluded modules.

## Detailed Reference
- Local containers mount the repository at `/opt/airflow/frog`; DAG helpers also honor `FROG_PROJECT_ROOT` for import resolution.
- Docker services use TimescaleDB/Postgres for Airflow metadata and business data, Redis for Celery broker/results, and Airflow with `CeleryExecutor`. Consult `docker-compose.yml` for the authoritative service, volume, and environment-variable configuration.
