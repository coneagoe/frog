# Issue #89 Task 6 Report

## Commits

- `f9a6ca0` `fix: align auth email validation`
- `32d77c6` `fix: validate auth email inputs`
- `7accb8b` `fix: align auth validation and login handling`
- `ee1d850` `fix: use dummy hash for empty auth passwords`
- `82221d2` `fix: preserve auth cookies through proxy`

## Current Fix

- Added authoritative backend email validation shared by register and login. It trims and lowercases valid emails and rejects empty values, missing local parts, missing domains, and domains without a suffix.
- Invalid login emails receive a schema validation response before user lookup or password verification, without revealing whether an account exists.
- Added API coverage confirming invalid registration emails return 422 and do not create users, plus invalid-login validation coverage.

## Validation

- `uv run pytest test/paper_trading/api/test_auth_api.py test/paper_trading/auth/test_auth_service.py -q`: PASS, 78 tests.
- `tools/run_tests.sh test/paper_trading/api/test_auth_api.py test/paper_trading/storage/test_auth_models.py -q`: PASS, 21 tests against a fresh PostgreSQL test database. The runner created and waited for `issue-89-auth-foundation-test_db-1`; cleanup completed.
- `uv run pytest test/paper_trading/api/test_auth_api.py test/paper_trading/auth/test_auth_service.py test/paper_trading/storage/test_auth_models.py -q`: PASS, 85 tests.
- `uv run ruff check paper_trading/auth/__init__.py paper_trading/auth/service.py paper_trading/api/routers/auth.py test/paper_trading/auth/test_auth_service.py test/paper_trading/api/test_auth_api.py test/paper_trading/storage/test_auth_models.py`: PASS.
- `uv run mypy paper_trading/auth/__init__.py paper_trading/auth/service.py paper_trading/api/routers/auth.py`: PASS.
- Frontend auth focused tests: PASS, 38 tests.
- Frontend `npm run lint`: PASS.
- Frontend `npm run build`: PASS. Auth proxy route included.
- Frontend complete `npm test`: 244 passed, 2 existing analytics failures in `features/analytics/analytics-page.test.tsx`.
- `git diff --check`: PASS.

## Known Limitations

- The full frontend suite still has two pre-existing analytics chart-rendering failures; analytics files were not changed.
- Backend auth tests emit existing Starlette/httpx deprecation and short test JWT key warnings.
- No ownership, DAG, proxy implementation outside auth, PRODUCT.md, or data files were changed.

## Final Review Fix Round 2

- Aligned the frontend email validator exactly with the backend authority: `^[^\s@]+@[^\s@]+\.[^\s@]+$`, with trim/lower normalization preserved.
- Added the `a@b@c.com` cross-layer boundary case and kept invalid registration emails from creating users.
- Added a real PostgreSQL schema test that drops and creates `users` and `auth_tokens`, runs `create_all` twice, verifies indexes and the foreign key, and inserts a linked user/token.

### Validation

- `uv run pytest test/paper_trading/api/test_auth_api.py test/paper_trading/auth/test_auth_service.py -q`: PASS, 78 tests.
- `tools/run_tests.sh test/paper_trading/api/test_auth_api.py test/paper_trading/storage/test_auth_models.py test/paper_trading/storage/test_auth_postgresql.py -q`: PASS, 23 tests, fresh PostgreSQL database.
- Same `tools/run_tests.sh ...` command a second time: PASS, 23 tests, fresh PostgreSQL database.
- Frontend auth tests: PASS, 39 tests.
- Frontend `npm run lint`: PASS.
- Frontend `npm run build`: PASS.
- Frontend complete `npm test`: 244 passed, 2 existing analytics failures in `features/analytics/analytics-page.test.tsx`.
- Auth ruff and mypy checks: PASS.
- `git diff --check`: PASS.

### Limitations

- The full frontend suite retains the two existing analytics failures; no analytics code was changed.
- Existing backend test warnings remain for Starlette/httpx and short test JWT keys.

## Final Verification: Test Module Rename

- Renamed `test/paper_trading/auth/test_service.py` to `test/paper_trading/auth/test_auth_service.py` to avoid pytest's duplicate-basename imported-module mismatch with `test/forecast_snapshot/test_service.py`.
- Synchronized active Task 1 and Task 3 briefs/reports and Task 6 command references. Historical review diffs and pytest cache entries were left unchanged as historical/generated artifacts.
- No runtime source, analytics, `PRODUCT.md`, or `data/` files were changed.

### Validation

- `tools/run_tests.sh`: collection completed successfully; 2487 passed, 9 skipped, 17 unrelated pre-existing business-test failures. The prior imported-module mismatch did not recur.
- `uv run pytest test/paper_trading/auth/test_auth_service.py -v`: PASS, 64 tests.
- `uv run ruff check paper_trading/auth test/paper_trading/auth/test_auth_service.py`: PASS.
- `uv run mypy paper_trading/auth`: PASS, no issues found in 2 source files.
- `git diff --check`: PASS.

### Concerns

- The full backend suite remains non-green because of 17 unrelated existing failures in corporate actions, ledger rebuild, historical ETF repair, matching, order deletion, and repository replay tests. The failure set is unrelated to this filename-only change.
