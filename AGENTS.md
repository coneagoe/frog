# Project Guidelines

## Command Rules
- Critical: use `poetry run` for Python commands in this repo. Do not use bare `python` or `python3` for project tasks.
- Prefer the AGENTS command set below over ad-hoc alternatives.
- Repository-local agent skills live under `.agents/skills/`; `update_doc` can still be used manually, and the root commit skill now invokes it automatically before Copilot-driven commits when doc sync is being checked.

## Build And Test
```bash
# Setup
poetry install --with dev
poetry run pre-commit install

# Quality
poetry run pre-commit run
poetry run pre-commit run --all-files
poetry run black .
poetry run isort .
poetry run flake8 --max-line-length=120
poetry run mypy

# Tests
poetry run pytest test
poetry run pytest -v test
poetry run pytest test/download/dl/test_downloader.py
poetry run pytest test/download/dl/test_downloader.py::TestDownloader::test_dl_general_info_stock
```

## Architecture
- `core/`: market abstraction and registry pattern (`IMarket`, `BaseMarket`, `market_registry.py`).
- `download/`: data source orchestration (akshare, baostock, tushare) via `DownloadManager` and downloader modules.
- `storage/`: SQLAlchemy-based persistence for PostgreSQL/TimescaleDB.
- `dags/`: Airflow orchestration; shared DAG helpers live in `dags/common_dags.py`.
- End-to-end flow: data download -> storage -> analysis/backtest -> triggers/strategies.

## Conventions
- Python: 3.11+ (CI targets 3.12).
- Formatting: Black with 120-char line length.
- Imports: isort with Black profile; stdlib, third-party, local grouping.
- Naming: `snake_case` for functions/variables/files, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Domain conventions: Chinese comments/messages and Chinese column names are acceptable and common.
- Config entry point: `conf.parse_config()`.

## Testing Patterns
- Use pytest with Arrange-Act-Assert.
- Mock external providers (`akshare`, `baostock`, `tushare`) instead of live calls.
- Many tests rely on explicit import-path setup:
```python
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
```
- Storage layer uses singleton-style helpers; reset shared state in tests when needed (for example via `reset_storage()`).

## Airflow And Environment Notes
- Airflow container path fallback is typically `/opt/airflow/frog`; DAGs may also read `FROG_PROJECT_ROOT`.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA unless explicitly requested.
- Line endings are LF-enforced via `.gitattributes`. On Windows, if needed, run `git add --renormalize .` once.

## Type Checking Scope
- Mypy is intentionally relaxed for legacy areas and excludes parts of the repo (see `pyproject.toml`).
- Keep changes type-aware where checking is enabled, but do not force large refactors in excluded modules.
