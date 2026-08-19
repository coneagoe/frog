# Dynamic Test Database Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run PostgreSQL-backed tests on an available loopback port instead of failing when host port 5433 is occupied.

**Architecture:** Keep PostgreSQL on container port 5432. Parameterize the Compose host-port mapping through `TEST_DB_HOST_PORT`, selected by `tools/run_tests.sh`, and use the same value in `TEST_POSTGRESQL_URL`.

**Tech Stack:** Bash, Docker Compose, pytest.

## Global Constraints

- The container PostgreSQL port remains `5432`.
- The host mapping must bind only to `127.0.0.1`.
- Port selection begins at `5433` and chooses an available host port.
- `TEST_POSTGRESQL_URL` must use the selected host port.
- Use `uv run` for Python commands.

---

### Task 1: Dynamically Map the Test Database Port

**Files:**
- Modify: `docker-compose.yml:139`
- Modify: `tools/run_tests.sh:4-25`
- Modify: `test/tools/test_run_tests.py:12-90`

**Interfaces:**
- Consumes: optional `TEST_DB_HOST_PORT` Compose environment value.
- Produces: `TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:<selected_port>/quant` for pytest.

- [ ] **Step 1: Write the failing test**

Update the fake Docker command to log `TEST_DB_HOST_PORT`. Add an assertion that a simulated selected port is passed to both Compose and pytest.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/tools/test_run_tests.py -q`
Expected: FAIL because the runner does not select or export `TEST_DB_HOST_PORT`.

- [ ] **Step 3: Write minimal implementation**

Parameterize the test-db Compose host mapping:

```yaml
ports: ["127.0.0.1:${TEST_DB_HOST_PORT:-5433}:5432"]
```

Add a Bash helper that probes loopback TCP ports beginning at `5433`, exports the first available `TEST_DB_HOST_PORT` for Compose, and builds `TEST_POSTGRESQL_URL` with it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/tools/test_run_tests.py -q`
Expected: PASS.

- [ ] **Step 5: Run a PostgreSQL-backed verification**

Run: `tools/run_tests.sh test/paper_trading/storage/test_matching_status_migration.py -q`
Expected: Docker starts `test_db` on a dynamically selected host port and pytest passes.
