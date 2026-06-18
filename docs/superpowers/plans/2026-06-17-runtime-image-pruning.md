# Runtime Image Pruning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `factor/`, `backtest/`, and `test/` from the business runtime images and runtime container mounts, and move `alphapurify` out of the default dependency set so Docker builds stop paying for local factor-research dependencies.

**Architecture:** First prove the runtime boundary with tests: default dependencies exclude `alphapurify`, and the business runtime import surface does not need `factor/` or `backtest/`. Then prune the runtime dependency set in `pyproject.toml`, tighten the `Dockerfile` to copy only runtime files, and finally remove `.:/app` from the business services in `docker-compose.yml` so the runtime containers cannot see the research directories through bind mounts.

**Tech Stack:** Python 3.11+, uv dependency groups, Docker, Docker Compose, Celery, FastAPI, pytest.

## Global Constraints

- Preserve the existing `uv`-based toolchain and `uv.lock` workflow.
- Do not change business behavior, Airflow DAG schedule/dependencies/retries/task boundaries/SLA, or unrelated modules.
- Keep `app`, `paper-trading`, and `celery-worker` as the business runtime boundary; Airflow services may keep their broader dev-oriented mounts unless directly required by this change.
- Remove `alphapurify` from the default dependency set and place it in a local research-only dependency group.
- Ensure default runtime installs do not include the research dependency group.
- Ensure runtime images and runtime mounts for `app`, `paper-trading`, and `celery-worker` do not expose `factor/`, `backtest/`, or `test/`.
- Update only the docs directly affected by the changed local research workflow.

---

## File Structure

- Modify `pyproject.toml`: move `alphapurify` from `project.dependencies` to a research-only dependency group.
- Modify `uv.lock`: refresh the lockfile after dependency-group changes.
- Modify `Dockerfile`: prune `COPY` list to runtime-only files and keep runtime install on the default dependency set.
- Modify `docker-compose.yml`: remove `.:/app` from `app`, `paper-trading`, and `celery-worker`, or replace it with narrower non-code mounts only if necessary.
- Modify `README.md`: document how to install the local research dependency group for factor-analysis workflows.
- Create `test/tools/test_runtime_dependency_boundary.py`: assert that default dependencies exclude `alphapurify` and that a research dependency group includes it.
- Create `test/tools/test_runtime_image_boundary.py`: assert that `Dockerfile` and `docker-compose.yml` no longer expose `factor/`, `backtest/`, and `test/` to the business runtime services.

### Task 1: Move `alphapurify` To A Research Dependency Group

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `test/tools/test_runtime_dependency_boundary.py`

**Interfaces:**
- Consumes: current main dependency list in `pyproject.toml`
- Produces: a default runtime dependency set without `alphapurify`, plus a research-only dependency group that restores it for local use

- [ ] **Step 1: Write the failing dependency-boundary test**

Create `test/tools/test_runtime_dependency_boundary.py`:

```python
from pathlib import Path

import tomllib


def test_alphapurify_moves_out_of_default_dependencies():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = data["project"]["dependencies"]
    assert not any(str(item).startswith("alphapurify") for item in dependencies)

    dependency_groups = data.get("dependency-groups", {})
    assert "research" in dependency_groups
    assert any(str(item).startswith("alphapurify") for item in dependency_groups["research"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_runtime_dependency_boundary.py -q
```

Expected: FAIL because `alphapurify` is still in `project.dependencies` and the `research` group does not yet exist.

- [ ] **Step 3: Write the minimal dependency-group migration**

Edit `pyproject.toml` to move `alphapurify` out of the main dependency list and add a `research` dependency group:

```toml
[dependency-groups]
dev = [
    "pre-commit>=4.2.0,<5.0.0",
    "ruff>=0.12.0,<1.0.0",
    "types-requests>=2.32.4.20250913,<3.0.0.0",
    "mypy>=1.18.2,<2.0.0",
    "pandas-stubs>=2.3.2.250926,<3.0.0.0",
    "types-tqdm>=4.67.0.20250809,<5.0.0.0",
    "types-psycopg2>=2.9.21.20251012,<3.0.0.0",
    "scipy-stubs>=1.16.3.0,<2.0.0.0",
]
research = [
    "alphapurify>=0.1.8,<0.2.0",
]
```

And remove this exact entry from `project.dependencies`:

```toml
"alphapurify (>=0.1.8,<0.2.0)",
```

Then refresh the lockfile:

```bash
uv lock
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_runtime_dependency_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock test/tools/test_runtime_dependency_boundary.py
git commit -m "chore: isolate research dependencies"
```

### Task 2: Prune The Runtime Image Contents

**Files:**
- Modify: `Dockerfile`
- Create: `test/tools/test_runtime_image_boundary.py`

**Interfaces:**
- Consumes: research dependency group from Task 1 and current runtime module layout
- Produces: a Docker image definition that excludes `factor/`, `backtest/`, and `test/` from the business runtime image

- [ ] **Step 1: Write the failing image-boundary test**

Create `test/tools/test_runtime_image_boundary.py`:

```python
from pathlib import Path


def test_dockerfile_excludes_research_directories_from_runtime_image():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY factor ./factor" not in content
    assert "COPY backtest ./backtest" not in content
    assert "COPY test ./test" not in content
    assert "uv sync --frozen --no-dev" in content
```

- [ ] **Step 2: Run the test to verify it fails if needed**

Run:

```bash
uv run pytest test/tools/test_runtime_image_boundary.py -q
```

Expected: FAIL if any research directories are still copied, or PASS immediately if the current `Dockerfile` already satisfies the runtime-boundary rule after prior cleanup.

- [ ] **Step 3: Write the minimal image pruning**

Edit `Dockerfile` so the runtime image copies only the runtime file set. Keep entries in this shape:

```dockerfile
COPY celery_app.py celery_config.py start_celery.sh config.py config.ini ./
COPY *.csv ./
COPY common ./common
COPY conf ./conf
COPY download ./download
COPY fund ./fund
COPY indicator ./indicator
COPY monitor ./monitor
COPY ocr ./ocr
COPY stock ./stock
COPY storage ./storage
COPY task ./task
COPY tools ./tools
COPY trigger ./trigger
COPY utility ./utility
COPY paper_trading ./paper_trading
```

And do not add any of these:

```dockerfile
COPY factor ./factor
COPY backtest ./backtest
COPY test ./test
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_runtime_image_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile test/tools/test_runtime_image_boundary.py
git commit -m "chore: prune runtime image contents"
```

### Task 3: Remove Broad Code Mounts From Business Runtime Services

**Files:**
- Modify: `docker-compose.yml`
- Modify: `test/tools/test_runtime_image_boundary.py`

**Interfaces:**
- Consumes: runtime image file boundary from Task 2
- Produces: compose services `app`, `paper-trading`, and `celery-worker` that no longer regain `factor/`, `backtest/`, and `test/` through `.:/app`

- [ ] **Step 1: Extend the failing runtime-boundary test**

Append this test to `test/tools/test_runtime_image_boundary.py`:

```python
from pathlib import Path


def test_business_runtime_services_do_not_bind_mount_repo_root():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'volumes: [".:/app"]' not in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_runtime_image_boundary.py -q
```

Expected: FAIL because `app`, `paper-trading`, and `celery-worker` still use `.:/app`.

- [ ] **Step 3: Write the minimal compose pruning**

Edit `docker-compose.yml` so these business runtime services no longer mount the repo root:

```yaml
  app:
    build:
      context: .
    depends_on: [db, redis]
    environment:
      <<: [*app-common-env, *airflow-email-env]

  paper-trading:
    build:
      context: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      <<: *db-common-env
      DATABASE_URL: postgresql://quant:quant@db:5432/quant
      PAPER_TRADING_API_TOKEN: ${PAPER_TRADING_API_TOKEN:?PAPER_TRADING_API_TOKEN is required in .env}
    ports:
      - "127.0.0.1:8000:8000"

  celery-worker:
    build:
      context: .
    command: ["celery", "-A", "celery_app", "worker", "--loglevel=info"]
    depends_on: [db, redis]
    environment:
      <<: *app-common-env
    profiles: ["worker"]
```

Do not change the Airflow service volume mounts in this task.

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_runtime_image_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml test/tools/test_runtime_image_boundary.py
git commit -m "chore: tighten runtime service mounts"
```

### Task 4: Update Local Research Workflow Docs And Verify Runtime Builds

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: research dependency group and runtime boundaries from Tasks 1-3
- Produces: documented local research install path plus verified business runtime images

- [ ] **Step 1: Write the failing docs test**

Append this test to `test/tools/test_runtime_dependency_boundary.py`:

```python
from pathlib import Path


def test_readme_documents_research_group_install():
    content = Path("README.md").read_text(encoding="utf-8")

    assert "uv sync --group research" in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_runtime_dependency_boundary.py -q
```

Expected: FAIL because the README does not yet document the research group.

- [ ] **Step 3: Write the minimal docs update**

Add a short section to `README.md` in this shape:

```markdown
## Factor Research

Local factor-analysis workflows use the research dependency group:

- `uv sync --group dev --group research`

Business runtime images do not include the research group.
```

- [ ] **Step 4: Run focused verification**

Run:

```bash
uv run pytest test/tools/test_runtime_dependency_boundary.py test/tools/test_runtime_image_boundary.py -q
```

Expected: PASS.

- [ ] **Step 5: Run runtime build verification**

Run:

```bash
docker compose build app && docker compose build celery-worker && docker compose build paper-trading
```

Expected: all three business runtime images build successfully without installing `alphapurify`.

- [ ] **Step 6: Commit**

```bash
git add README.md test/tools/test_runtime_dependency_boundary.py test/tools/test_runtime_image_boundary.py
git commit -m "docs: document local research dependency workflow"
```

## Self-Review Notes

- Spec coverage: the plan covers dependency pruning, image pruning, compose mount pruning, docs, and runtime verification.
- Placeholder scan: each task names exact files, commands, and expected outputs.
- Interface consistency: the runtime boundary is established in Task 1, enforced in Task 2, protected at runtime in Task 3, and documented plus build-verified in Task 4.
