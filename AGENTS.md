# Project Guidelines

## Command Rules
- Critical: use `uv run` for Python commands in this repo. Do not use bare `python` or `python3` for project tasks.
- Repository-local agent skills live under `.agents/skills/`; the commit workflow invokes `update_doc` before committing.

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
```

## Architecture
- `download/`: data source orchestration (akshare, baostock, tushare) via `DownloadManager` and `download/dl/downloader.py` (the provider switchboard).
- `storage/`: SQLAlchemy-based persistence for PostgreSQL/TimescaleDB; singleton via `get_storage()`, reset with `reset_storage()`.
- `conf/global_settings.py` is the bootstrap entrypoint: `conf.parse_config()` reads `config.ini` into env vars and is called by many scripts/tasks.
- `dags/`: Airflow orchestration; shared helpers in `dags/common_dags.py` (import bootstrap via `FROG_PROJECT_ROOT` or `/opt/airflow/frog`, alert parsing, partition fan-out).
- `task/`: Celery task wrappers around `tools/` and `backtest/` entrypoints; wired via `celery_app.py`.
- End-to-end data flow: provider APIs -> download/ -> storage/ -> analysis/backtest -> triggers.

## Conventions
- Python 3.11+ (CI targets 3.12). Formatting: Black, 120-char line length. Imports: isort with Black profile.
- uv `package = false`; tests set `pythonpath = ["."]`, so imports rely on the repo root rather than an installed package.
- Chinese comments/messages and Chinese column names are common and acceptable.
- Commit messages must be written in English.
- Storage tables: when adding or removing, update `tools/db_common.sh` so `db_export.sh`/`db_import.sh` stay in sync.
- LF line endings enforced via `.gitattributes`; `pre-commit` runs on staged files only; trailing-whitespace fixer excludes `*.csv`.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA unless explicitly requested.

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
- `CLAUDE.md` in the repo root contains comprehensive Docker setup, service topology, env vars, and Airflow config.
- `.github/copilot-instructions.md` has additional architecture and convention notes.
