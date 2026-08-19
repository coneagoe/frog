# Isolated PostgreSQL Test Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one repository command that starts an isolated PostgreSQL database, runs all tests with PostgreSQL integration coverage enabled, and always removes the temporary database.

**Architecture:** `docker-compose.yml` will define a standalone `test_db` service with a host-only port distinct from the development database and an anonymous volume. `tools/run_tests.sh` will own that service lifecycle, export a fixed `TEST_POSTGRESQL_URL`, invoke pytest through `uv`, and clean up through a shell trap. A focused Python test will replace Docker and uv on `PATH` to verify the runner without starting containers.

**Tech Stack:** Docker Compose, TimescaleDB/PostgreSQL 16, Bash, pytest, uv.

## Global Constraints

- Do not add `TEST_POSTGRESQL_URL` to `.env`; only the runner process exports it.
- Preserve the existing `db` service and its persistent `./docker/db` volume unchanged.
- `test_db` must use an anonymous volume and be removed by `docker compose rm -sfv test_db` on every runner exit path.
- Bind `test_db` only to `127.0.0.1:5433` to avoid conflicts with development `db` on `127.0.0.1:5432`.
- Use `uv run` for all Python project commands.
- The runner must forward every command-line argument after `tools/run_tests.sh` to `pytest test`.

---

### Task 1: Define the isolated Compose database service

**Files:**
- Modify: `docker-compose.yml:127-146`
- Test: `test/tools/test_run_tests.py`

**Interfaces:**
- Consumes: `docker compose up -d --wait test_db` from `tools/run_tests.sh`.
- Produces: Compose service `test_db`, reachable at `postgresql://quant:quant@localhost:5433/quant` and removable with `docker compose rm -sfv test_db`.

- [ ] **Step 1: Write the failing Compose contract test**

Create `test/tools/test_run_tests.py` with this test. It reads Compose as YAML text only, avoiding a new YAML dependency:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_isolated_test_database() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  test_db:\n" in compose
    assert "timescale/timescaledb:latest-pg16" in compose
    assert 'ports: ["127.0.0.1:5433:5432"]' in compose
    assert "- /var/lib/postgresql/data" in compose
    assert "./docker/db:/var/lib/postgresql/data" in compose
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `uv run pytest test/tools/test_run_tests.py::test_compose_defines_isolated_test_database -v`

Expected: FAIL because `test_db` is absent.

- [ ] **Step 3: Add the `test_db` service beside `db`**

Insert this service before the existing `db` service. It deliberately has no named host path; Docker allocates an anonymous volume that the runner can remove.

```yaml
  test_db:
    image: timescale/timescaledb:latest-pg16
    command: ["postgres", "-c", "max_connections=200"]
    environment:
      <<: *postgres-common-env
    ports: ["127.0.0.1:5433:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - /var/lib/postgresql/data
```

- [ ] **Step 4: Run the Compose contract test to verify it passes**

Run: `uv run pytest test/tools/test_run_tests.py::test_compose_defines_isolated_test_database -v`

Expected: PASS.

- [ ] **Step 5: Commit the Compose service and contract test**

```bash
git add docker-compose.yml test/tools/test_run_tests.py
git commit -m "test: add isolated PostgreSQL service"
```

### Task 2: Add the lifecycle-managed test runner

**Files:**
- Create: `tools/run_tests.sh`
- Modify: `test/tools/test_run_tests.py`
- Modify: `README.md`
- Test: `test/tools/test_run_tests.py`

**Interfaces:**
- Consumes: Docker Compose service `test_db` and any caller arguments (`"$@"`).
- Produces: executable command `bash tools/run_tests.sh [pytest args...]`; it exports `TEST_POSTGRESQL_URL=postgresql://quant:quant@localhost:5433/quant`, starts and waits for `test_db`, calls `uv run pytest test "$@"`, and removes `test_db` with its anonymous volume before exit.

- [ ] **Step 1: Write failing runner behavior tests**

Append helpers and tests to `test/tools/test_run_tests.py`. The fake executables record arguments and environment, make `uv` return a controlled pytest status, and allow assertions after the shell exits:

```python
import os
import subprocess

import pytest


def _run_runner(tmp_path: Path, *arguments: str, pytest_status: int = 0) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "commands.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'printf "docker %s\\n" "$*" >> "$COMMAND_LOG"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'printf "uv %s|%s\\n" "$*" "$TEST_POSTGRESQL_URL" >> "$COMMAND_LOG"\n'
        "exit \"$PYTEST_STATUS\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    environment = os.environ | {
        "COMMAND_LOG": str(log_file),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PYTEST_STATUS": str(pytest_status),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "tools" / "run_tests.sh"), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    return result, log_file.read_text(encoding="utf-8").splitlines()


def test_runner_starts_test_database_exports_url_forwards_arguments_and_cleans_up(tmp_path: Path) -> None:
    result, commands = _run_runner(tmp_path, "-k", "enum")

    assert result.returncode == 0
    assert commands == [
        "docker compose up -d --wait test_db",
        "uv run pytest test -k enum|postgresql://quant:quant@localhost:5433/quant",
        "docker compose rm -sfv test_db",
    ]


def test_runner_cleans_up_and_preserves_pytest_failure_status(tmp_path: Path) -> None:
    result, commands = _run_runner(tmp_path, pytest_status=1)

    assert result.returncode == 1
    assert commands[-1] == "docker compose rm -sfv test_db"
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run: `uv run pytest test/tools/test_run_tests.py -v`

Expected: the new runner tests FAIL because `tools/run_tests.sh` does not exist.

- [ ] **Step 3: Implement the shell runner**

Create executable `tools/run_tests.sh` with this complete content:

```bash
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose rm -sfv test_db >/dev/null 2>&1 || true
}

trap cleanup EXIT

export TEST_POSTGRESQL_URL="postgresql://quant:quant@localhost:5433/quant"
docker compose up -d --wait test_db
uv run pytest test "$@"
```

Mark it executable with `chmod +x tools/run_tests.sh`.

- [ ] **Step 4: Document the canonical test command**

Locate the existing test command in `README.md` and replace or supplement it with:

```markdown
Run the full test suite, including PostgreSQL integration tests:

```bash
tools/run_tests.sh
```

The command starts an isolated `test_db`, sets `TEST_POSTGRESQL_URL` for the
test process, and removes the test database and its data after pytest exits.
```

- [ ] **Step 5: Run runner tests to verify success**

Run: `uv run pytest test/tools/test_run_tests.py -v`

Expected: PASS. The tests prove command order, fixed URL export, argument forwarding, cleanup, and pytest failure-status propagation.

- [ ] **Step 6: Commit the runner, tests, and documentation**

```bash
git add tools/run_tests.sh test/tools/test_run_tests.py README.md
git commit -m "test: add PostgreSQL test runner"
```

### Task 3: Verify the real service lifecycle and integration execution

**Files:**
- Verify: `docker-compose.yml`
- Verify: `tools/run_tests.sh`
- Verify: `test/tools/test_run_tests.py`

**Interfaces:**
- Consumes: `tools/run_tests.sh` from Task 2.
- Produces: fresh evidence that real PostgreSQL-gated tests run through `test_db` and that its container does not survive the command.

- [ ] **Step 1: Validate the Compose configuration**

Run: `docker compose config`

Expected: exit code 0 and a resolved `test_db` service with a localhost `5433` mapping and anonymous data volume.

- [ ] **Step 2: Run a focused PostgreSQL-gated test through the runner**

Run: `tools/run_tests.sh test/storage/test_enum_governance_smoke.py -v`

Expected: test collection reports PostgreSQL cases executing rather than `TEST_POSTGRESQL_URL is unavailable`. Record any functional failures separately; a failing application assertion is not a runner lifecycle failure.

- [ ] **Step 3: Verify cleanup after the focused run**

Run: `docker compose ps test_db`

Expected: no running or retained `test_db` container.

- [ ] **Step 4: Run focused static and runner checks**

Run: `uv run ruff format --check docker-compose.yml tools/run_tests.sh test/tools/test_run_tests.py && uv run ruff check test/tools/test_run_tests.py && uv run pytest test/tools/test_run_tests.py && git diff --check`

Expected: all commands exit 0. If Ruff does not accept non-Python files in this repository, run the applicable format/check commands for `test/tools/test_run_tests.py` and retain `git diff --check` for shell and Compose whitespace validation.

- [ ] **Step 5: Commit verification-only corrections if required**

```bash
git status --short
```

Do not create an empty commit. Do not stage unrelated pre-existing files.
