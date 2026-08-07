# Final Review Fix Report

## Files Changed

- `tools/db_export.sh`: rejects `--clean --table NAME` after argument parsing
  and before output-directory creation, output-file creation, PostgreSQL access,
  or `pg_dump`; removes the unreachable selected-table `DROP TABLE ... CASCADE`
  generation and catalog-query helper; documents `--clean` as full-database only.
- `test/tools/test_db_scripts.py`: replaces selected-table clean-export success
  expectations with portable script-level rejection coverage that verifies the
  requested output remains unchanged and Docker is not invoked.
- `test/tools/test_db_scripts_postgresql.py`: verifies rejected selected-table
  clean export preserves an existing output file, the selected table, and its
  inbound foreign keys; retains destination importer-guard coverage.
- `docs/paper_trading.md`: documents that selected-table dumps contain no clean
  drops and directs clean selected-table recovery to guarded
  `db_import.sh --clean --table NAME`.

## Red Evidence

Before changing production code, ran:

```bash
uv run pytest test/tools/test_db_scripts.py::test_clean_selected_table_export_is_rejected_before_output_or_database_access
```

Output: `1 failed`. The current script exited `0` for
`db_export.sh --no-gzip --clean --table paper_orders --out <existing-file>`,
showing it did not reject the unsafe request before the export path.

## Green Evidence

After the guard and removal of selected-table clean-drop generation:

```bash
uv run pytest test/tools/test_db_scripts.py
```

Output: `10 passed in 1.00s`.

```bash
TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py -v
```

Output: `2 passed in 1.37s`.

```bash
bash -n tools/db_export.sh && bash -n tools/db_import.sh && bash -n tools/db_common.sh
uv run ruff format --check test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py
uv run ruff check test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py
git diff --check
```

Output: shell syntax succeeded (with environment locale warnings), Ruff format
reported `2 files already formatted`, Ruff reported `All checks passed!`, and
`git diff --check` produced no output.

## Commit

Implementation commit: `9409df5 Reject clean selected-table exports`

## Concerns

- `uv run ruff check tools/db_export.sh ...` is not applicable because Ruff
  parses Python, not Bash; the command produced syntax diagnostics for the Bash
  script. Ruff was rerun only on changed Python files, and Bash syntax was
  checked with `bash -n`.
- The shell syntax commands emitted existing `LC_ALL=en_US.UTF-8` availability
  warnings, but exited successfully.
