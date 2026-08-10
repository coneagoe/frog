# Task 3 Verification Report

Date: 2026-08-09
Worktree: `/data/frog/.worktrees/isolated-postgresql-test-runner`
Branch: `isolated-postgresql-test-runner`

## Scope

Verified the isolated `test_db` lifecycle. No `.env` file or unrelated application code was changed.

Initial worktree state included the unrelated untracked file
`docs/superpowers/plans/2026-08-09-isolated-postgresql-test-runner.md`; it was left untouched.

## Compose Configuration

Command:

```bash
env SMTP_HOST=placeholder SMTP_PORT=25 SMTP_USER=placeholder \
  SMTP_PASSWORD=placeholder SMTP_MAIL_FROM=placeholder@example.invalid \
  ALERT_EMAILS=placeholder@example.invalid TUSHARE_TOKEN=placeholder \
  PAPER_TRADING_API_TOKEN=placeholder docker compose config --format json
```

Exit status: 0.

Relevant resolved `test_db` output:

```json
"ports": [{
  "host_ip": "127.0.0.1",
  "target": 5432,
  "published": "5433",
  "protocol": "tcp"
}],
"volumes": [{
  "type": "volume",
  "target": "/var/lib/postgresql/data",
  "volume": {}
}]
```

This confirms a localhost-only `127.0.0.1:5433:5432` mapping and an anonymous PostgreSQL data volume.

## Lifecycle Verification

Initial required command:

```bash
tools/run_tests.sh test/storage/test_enum_governance_smoke.py -v
```

Initial output and exit status: failed before service startup because Compose parses the entire file and required `ALERT_EMAILS` was absent:

```text
error while interpolating x-airflow-email-env.ALERT_EMAILS: required variable ALERT_EMAILS is missing a value: ALERT_EMAILS is required
```

Root-cause confirmation command:

```bash
env SMTP_HOST=placeholder SMTP_PORT=25 SMTP_USER=placeholder \
  SMTP_PASSWORD=placeholder SMTP_MAIL_FROM=placeholder@example.invalid \
  ALERT_EMAILS=placeholder@example.invalid TUSHARE_TOKEN=placeholder \
  PAPER_TRADING_API_TOKEN=placeholder \
  tools/run_tests.sh test/storage/test_enum_governance_smoke.py -v
```

Output: `test_db` was created, started, and became `Healthy`; pytest collected four tests and executed against `postgresql://quant:***@127.0.0.1:5433/quant`. Results were 3 passed and 1 failed.

Correction: `tools/run_tests.sh` now supplies the necessary Compose-only placeholders through its `compose()` wrapper for both `up` and its exact `rm -sfv test_db` cleanup. `TEST_POSTGRESQL_URL` remains the runner's exported test URL. A focused regression test removes those variables from the caller environment and asserts the Compose subprocess receives them.

Post-correction required command:

```bash
tools/run_tests.sh test/storage/test_enum_governance_smoke.py -v
```

Output: `test_db` was created, started, and reached `Healthy`; pytest collected and ran all four tests against `127.0.0.1:5433`, confirming it was not skipped for a missing `TEST_POSTGRESQL_URL`. Results remained 3 passed and 1 failed in 4.99 seconds.

Service cleanup command:

```bash
env SMTP_HOST=placeholder SMTP_PORT=25 SMTP_USER=placeholder \
  SMTP_PASSWORD=placeholder SMTP_MAIL_FROM=placeholder@example.invalid \
  ALERT_EMAILS=placeholder@example.invalid TUSHARE_TOKEN=placeholder \
  PAPER_TRADING_API_TOKEN=placeholder docker compose ps test_db
```

Exit status: 0. Output after each runner invocation:

```text
NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS
```

No `test_db` service remained. The runner cleanup path used exactly `docker compose rm -sfv test_db` through the wrapper. No `db` service was started or changed.

## Focused Quality Checks

Commands and outputs after correction:

```bash
uv run ruff check test/tools/test_run_tests.py
# All checks passed!

uv run pytest test/tools/test_run_tests.py
# 3 passed in 0.07s

uv run ruff format --check test/tools/test_run_tests.py
# 1 file already formatted

git diff --check
# no output; exit status 0
```

An attempted `uv run ruff format --check tools/run_tests.sh test/tools/test_run_tests.py` correctly rejected the Bash runner as non-Python. Formatting verification was then run only on the applicable Python source, as required.

## Correction and Commit

Necessary correction committed:

```text
4e59072 fix: scope Compose placeholders in test runner
```

Committed files:

```text
tools/run_tests.sh
test/tools/test_run_tests.py
```

## Concerns

The PostgreSQL-gated test exposes an unrelated existing application failure and was not modified:

```text
test_postgresql_governed_writer_smoke_uses_canonical_labels
AssertionError: expected one PaperCashLedger row for account_id=1 and event_type="freeze", got zero
```

The failure occurs after `test_db` is healthy and PostgreSQL-backed tests execute, so it is not a runner lifecycle or missing-URL skip issue. There is also a non-failing environment warning during the runner command:

```text
bash: warning: setlocale: LC_ALL: cannot change locale (en_US.UTF-8)
```

## Final-Fix Review Follow-Up

### Changes

- Scoped `TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5433/quant`
  to the `uv run pytest test "$@"` command. Compose startup and cleanup no
  longer inherit the URL.
- Extended the fake-executable runner tests to log `TEST_POSTGRESQL_URL` at
  each subprocess boundary. They require both Docker Compose invocations to
  receive an empty value and uv to receive the fixed PostgreSQL URL.
- Isolated the `test_db` Compose text block before asserting its image, port,
  and anonymous-volume settings, so another service cannot satisfy those
  requirements.

### RED Command And Result

```bash
uv run pytest test/tools/test_run_tests.py -v
```

Result: 1 passed, 2 failed. The expected failures showed that both
`docker compose up -d --wait test_db` and `docker compose rm -sfv test_db`
inherited `TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5433/quant`
from the runner's global export.

### GREEN Commands And Results

```bash
uv run pytest test/tools/test_run_tests.py -v
# 3 passed in 0.07s

uv run ruff format --check test/tools/test_run_tests.py
# 1 file already formatted

uv run ruff check test/tools/test_run_tests.py
# All checks passed!

git diff --check
# no output; exit status 0
```

The focused fake-executable tests now prove the desired boundary behavior:
Docker receives no test database URL, uv receives the exact IPv4 URL, cleanup
runs, and a pytest status of 1 is preserved.

## Caller URL Isolation Follow-Up

### Changes

- Updated `compose()` to invoke Docker through
  `env -u TEST_POSTGRESQL_URL` while preserving its command-scoped Compose
  placeholder variables.
- Updated the fake-executable test environment to deliberately provide
  `TEST_POSTGRESQL_URL=postgresql://sentinel:sentinel@127.0.0.1:5433/sentinel`.
  Both Docker calls must still observe an empty value; uv must observe the
  fixed `postgresql://quant:quant@127.0.0.1:5433/quant` value.

### RED Command And Result

```bash
uv run pytest test/tools/test_run_tests.py -v
```

Result: 1 passed, 2 failed. Both `docker compose up -d --wait test_db` and
`docker compose rm -sfv test_db` received the caller-provided sentinel URL,
confirming that command-scoping the pytest assignment alone did not clear a
parent environment value for Compose.

### GREEN Commands And Results

```bash
uv run pytest test/tools/test_run_tests.py -v
# 3 passed in 0.06s

uv run ruff check test/tools/test_run_tests.py
# All checks passed!

uv run ruff format --check test/tools/test_run_tests.py
# 1 file already formatted

git diff --check
# no output; exit status 0
```

The runner now clears caller-supplied test database URLs for both Compose
invocations and assigns the exact fixed IPv4 URL only to pytest.
