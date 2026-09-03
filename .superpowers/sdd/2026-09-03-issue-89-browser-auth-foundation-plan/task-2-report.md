# Task 2 Report

Status: DONE

Commit: `1dacc64` (`feat: add browser auth persistence models`)

Implemented User and AuthToken SQLAlchemy persistence models, including normalized unique user emails, session version defaults, timezone-aware timestamps, token foreign keys, purpose/expiry indexing, and no raw-token storage. Exported the models and table names through `storage.model` and `storage`, and registered the auth tables in the startup metadata DDL path.

Tests and checks:

- `uv run pytest test/paper_trading/storage/test_auth_models.py test/paper_trading/api/test_api_auth.py -v`: 3 passed
- `uv run ruff check storage/model/auth.py storage/model/__init__.py storage/__init__.py storage/storage_db.py test/paper_trading/storage/test_auth_models.py`: passed
- `git diff --check`: passed

Concerns: the API smoke test emits an existing Starlette/httpx deprecation warning; it does not affect the result.

## Fix Round 1

Status: DONE

Reviewer findings resolved:

- Added `users` and `auth_tokens` to `tools/db_common.sh` `BUSINESS_TABLES`; the existing coverage test now confirms both metadata tables are included in the database export/import management list.
- Expanded auth model tests to verify User and AuthToken creation, foreign-key target, purpose/expiry composite index, field types and nullability, absence of raw-token fields, and whitespace/case email normalization before the unique constraint check.
- Removed the redundant `_AUTH_TABLES` exception from `storage/storage_db.py`; auth tables are not in the PostgreSQL excluded set, so startup DDL behavior is unchanged.

Fix round checks:

- `uv run pytest test/paper_trading/storage/test_auth_models.py test/tools/test_db_common.py -v`: 11 passed
- `uv run ruff check storage/model/auth.py storage/model/__init__.py storage/__init__.py storage/storage_db.py test/paper_trading/storage/test_auth_models.py`: passed
- `bash -n tools/db_common.sh`: passed
- `git diff --check`: passed
