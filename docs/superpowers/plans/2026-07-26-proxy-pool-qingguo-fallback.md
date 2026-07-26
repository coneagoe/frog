# ProxyPool Qingguo Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a private ProxyPool service and use it as the preferred proxy source only when AkShare proxy recovery is triggered, with Qingguo as an automatic fallback.

**Architecture:** Docker Compose runs `proxy_pool` and a dedicated `proxy_redis` without publishing either port. `utility.proxy` remains the sole provider boundary and selects providers by `PROXY_PROVIDER`: the default `auto` path asks the local ProxyPool API first, validates a returned endpoint through the current proxy health path, and uses the existing Qingguo allocator only when the local source cannot supply a usable proxy. `change_proxy` stays restricted to the existing AkShare-decorated calls.

**Tech Stack:** Python 3.11+, `requests`, `pytest`, Docker Compose, `jhao104/proxy_pool`, Redis 7.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Keep ProxyPool API port `5010` and ProxyPool Redis port `6379` private to the Compose network; do not add host `ports` mappings.
- Use a dedicated `proxy_redis`; do not share the current Airflow/Celery `redis` service.
- Only `utility.proxy` may consume `PROXY_POOL_URL`; do not set global `http_proxy` or `https_proxy` in Compose.
- Preserve the existing direct-first, bounded `change_proxy` behavior for AkShare and never apply it to unrelated providers.
- Treat public proxies as untrusted; do not log Qingguo credentials or proxy URL userinfo.
- Default provider mode is `auto`; `qingguo` remains the rollback setting and `proxy_pool` is an explicit no-fallback mode.

---

## File Structure

- `docker-compose.yml`: private `proxy_pool` and `proxy_redis` services plus internal URL/provider environment mapping for services that execute downloads.
- `utility/proxy.py`: provider-independent allocation orchestration, ProxyPool API adapter, Qingguo adapter, health validation, and best-effort local-pool eviction.
- `test/utility/test_proxy.py`: isolated unit coverage for provider selection, payload contracts, proxy mappings, fallback, eviction, and existing decorator behavior.
- `test/download/dl/test_downloader_akshare.py`: integration-style guard that AkShare retains bounded proxy refresh behavior through `utility.proxy.get_proxy`.
- `tools/test_proxy.py`: opt-in diagnostic for the configured provider mode without requiring Qingguo credentials in ProxyPool-only mode.
- `test/tools/test_test_proxy.py`: deterministic tests for diagnostic configuration and sanitized output.
- `README.md`: deployment, configuration, diagnostics, rollback, and public-proxy safety documentation.

### Task 1: Lock Provider Selection and ProxyPool API Contracts

**Files:**
- Modify: `test/utility/test_proxy.py:15-147`
- Modify: `utility/proxy.py:1-135`

**Interfaces:**
- Consumes: `PROXY_PROVIDER` (`auto`, `proxy_pool`, `qingguo`) and `PROXY_POOL_URL` (default `http://proxy_pool:5010`).
- Produces: `get_proxy(max_attempts: int = 3) -> dict[str, str]`, returning `{"http": proxy_url, "https": proxy_url}` or raising `requests.exceptions.ProxyError`.
- Produces: provider helpers `_get_proxy_from_proxy_pool() -> tuple[str, dict[str, str]]`, `_get_proxy_from_qingguo() -> dict[str, str]`, and `_delete_proxy_from_pool(proxy_server: str) -> None`.

- [ ] **Step 1: Write failing tests for a valid ProxyPool endpoint and no-credential pool-only mode**

```python
def test_get_proxy_uses_proxy_pool_without_qingguo_credentials(monkeypatch):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.setenv("PROXY_POOL_URL", "http://pool:5010/")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)

    calls = []

    class PoolResponse:
        def json(self):
            return {"proxy": "127.0.0.1:8080", "https": True}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return PoolResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    assert proxy_module.get_proxy() == {
        "http": "http://127.0.0.1:8080",
        "https": "http://127.0.0.1:8080",
    }
    assert calls == [
        ("http://pool:5010/get/", {"params": {"type": "https"}, "timeout": 5})
    ]


@pytest.mark.parametrize("payload", [{"code": 0, "src": "no proxy"}, {}, {"proxy": 42}])
def test_proxy_pool_rejects_empty_or_malformed_payload(monkeypatch, payload):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")

    class PoolResponse:
        def json(self):
            return payload

    monkeypatch.setattr(proxy_module.requests, "get", lambda *args, **kwargs: PoolResponse())
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with pytest.raises(ProxyError, match="Failed to get working proxy after 1 attempts"):
        proxy_module.get_proxy(max_attempts=1)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest test/utility/test_proxy.py::test_get_proxy_uses_proxy_pool_without_qingguo_credentials test/utility/test_proxy.py::test_proxy_pool_rejects_empty_or_malformed_payload -v`

Expected: FAIL because the current allocator requires Qingguo credentials and does not call `/get/`.

- [ ] **Step 3: Implement minimal provider adapters and selector**

```python
PROXY_POOL_URL = "http://proxy_pool:5010"
PROXY_POOL_GET_PATH = "/get/"


def _proxy_provider() -> str:
    provider = os.getenv("PROXY_PROVIDER", "auto").lower()
    if provider not in {"auto", "proxy_pool", "qingguo"}:
        raise ProxyError("PROXY_PROVIDER must be auto, proxy_pool, or qingguo")
    return provider


def _proxy_pool_url(path: str) -> str:
    return f"{os.getenv('PROXY_POOL_URL', PROXY_POOL_URL).rstrip('/')}{path}"


def _get_proxy_from_proxy_pool() -> tuple[str, dict[str, str]]:
    response = requests.get(
        _proxy_pool_url(PROXY_POOL_GET_PATH),
        params={"type": "https"},
        timeout=5,
    )
    payload = response.json()
    server = payload.get("proxy") if isinstance(payload, dict) else None
    if not isinstance(server, str) or not _is_proxy_server(server):
        raise ValueError(f"ProxyPool returned no usable proxy: {payload}")
    proxy_url = f"http://{server}"
    return server, {"http": proxy_url, "https": proxy_url}
```

Move the existing Qingguo parameter and response logic into `_get_proxy_from_qingguo()`. In `get_proxy`, select only the requested provider in explicit modes. In `auto`, try ProxyPool first and retain its exception as diagnostic context before trying the Qingguo helper. Keep all provider attempts bounded by `max_attempts`, remove lowercase proxy environment variables before each allocation, and set them only after a selected provider returns a mapping.

- [ ] **Step 4: Run provider contract tests**

Run: `uv run pytest test/utility/test_proxy.py -v`

Expected: PASS, including existing Qingguo credential escaping and decorator tests.

- [ ] **Step 5: Commit the provider adapter contract**

```bash
git add utility/proxy.py test/utility/test_proxy.py
git commit -m "feat: add ProxyPool allocation fallback"
```

### Task 2: Validate and Evict Only Failed ProxyPool Endpoints

**Files:**
- Modify: `test/utility/test_proxy.py`
- Modify: `utility/proxy.py`

**Interfaces:**
- Consumes: `_get_proxy_from_proxy_pool() -> tuple[str, dict[str, str]]` from Task 1.
- Produces: `_validate_proxy(proxies: dict[str, str]) -> None` and `_delete_proxy_from_pool(proxy_server: str) -> None`.
- Contract: a ProxyPool endpoint is installed in `http_proxy` and `https_proxy` only after the configured health request succeeds; invalid/transport-failed endpoints cause best-effort `/delete/?proxy=host:port`.

- [ ] **Step 1: Write failing validation and eviction tests**

```python
def test_auto_falls_back_to_qingguo_after_proxy_pool_validation_failure(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setenv("PROXY_PROVIDER", "auto")
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_proxy_pool",
        lambda: ("127.0.0.1:8080", {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}),
    )
    monkeypatch.setattr(
        proxy_module,
        "_validate_proxy",
        lambda proxies: (_ for _ in ()).throw(ProxyError("egress unavailable")),
    )
    deleted = []
    monkeypatch.setattr(proxy_module, "_delete_proxy_from_pool", deleted.append)
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_qingguo",
        lambda: {"http": "http://key:pwd@127.0.0.2:8080", "https": "http://key:pwd@127.0.0.2:8080"},
    )

    assert proxy_module.get_proxy(max_attempts=1)["https"] == "http://key:pwd@127.0.0.2:8080"
    assert deleted == ["127.0.0.1:8080"]


def test_pool_eviction_never_hides_original_allocation_failure(monkeypatch, caplog):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.setattr(proxy_module, "_delete_proxy_from_pool", lambda _: (_ for _ in ()).throw(RequestException("api down")))
    # Configure the pool response and validation to fail, then assert ProxyError and a warning.
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest test/utility/test_proxy.py -k "validation_failure or eviction_never_hides" -v`

Expected: FAIL because the current allocator has no health validation or ProxyPool eviction path.

- [ ] **Step 3: Implement health validation and best-effort eviction**

```python
PROXY_HEALTHCHECK_URL = "https://www.baidu.com"


def _validate_proxy(proxies: dict[str, str]) -> None:
    response = requests.get(PROXY_HEALTHCHECK_URL, proxies=proxies, timeout=10)
    response.raise_for_status()


def _delete_proxy_from_pool(proxy_server: str) -> None:
    try:
        requests.get(
            _proxy_pool_url("/delete/"),
            params={"proxy": proxy_server},
            timeout=5,
        ).raise_for_status()
    except RequestException as exc:
        logging.warning("Could not evict failed ProxyPool endpoint %s: %s", proxy_server, exc)
```

In the `auto` path, validate a ProxyPool result before using it. On `RequestException`, `ProxyError`, or invalid health response, call `_delete_proxy_from_pool(server)` and then try Qingguo. In `proxy_pool` mode, retry bounded allocation after eviction and do not call Qingguo. Validate Qingguo mappings through the same helper so environment variables are installed only after a usable egress path is confirmed. Keep failure logs redacted: log only `host:port`, never a full Qingguo proxy URL.

- [ ] **Step 4: Run proxy unit tests**

Run: `uv run pytest test/utility/test_proxy.py -v`

Expected: PASS, including fallback, failed eviction, credential redaction, and bounded retry tests.

- [ ] **Step 5: Commit validation and eviction behavior**

```bash
git add utility/proxy.py test/utility/test_proxy.py
git commit -m "feat: validate and evict ProxyPool proxies"
```

### Task 3: Add Private ProxyPool Compose Services

**Files:**
- Modify: `docker-compose.yml:51-53, 117-121, 169-175, 207-214, 226-253`

**Interfaces:**
- Consumes: `PROXY_POOL_URL` and `PROXY_PROVIDER` used by Task 1.
- Produces: Compose services `proxy_pool` and `proxy_redis`; DNS endpoint `http://proxy_pool:5010` for relevant application/Airflow services.

- [ ] **Step 1: Add a Compose configuration assertion before editing**

Run: `docker compose config --quiet`

Expected: PASS with the current Compose file, establishing a baseline before adding services.

- [ ] **Step 2: Add private services and common environment**

Add this environment mapping after `x-qg-proxy-env`:

```yaml
x-proxy-pool-env: &proxy-pool-env
  PROXY_POOL_URL: http://proxy_pool:5010
  PROXY_PROVIDER: ${PROXY_PROVIDER:-auto}
```

Merge it into `x-airflow-common.environment` and `x-app-common-env`. Add `proxy_pool` to `depends_on` only for `app`, `celery-worker`, and Airflow services that can run AkShare work. Keep `proxy_pool` absent from `paper-trading`.

Add services without `ports`:

```yaml
  proxy_redis:
    image: redis:7-alpine
    volumes:
      - proxy_redis_data:/data

  proxy_pool:
    image: jhao104/proxy_pool:latest
    depends_on: [proxy_redis]
    environment:
      DB_CONN: redis://proxy_redis:6379/0
    restart: unless-stopped
```

Add the named volume at the top-level of Compose:

```yaml
volumes:
  proxy_redis_data:
```

Use the image's foreground/container entrypoint if the upstream image does not start both scheduler and API by default; verify this from the image documentation before finalizing the `command` field.

- [ ] **Step 3: Validate rendered Compose configuration**

Run: `docker compose config`

Expected: exit code `0`; `proxy_pool` and `proxy_redis` have no `ports` entries; application and Airflow services receive the two proxy-pool variables; existing `redis` remains unchanged.

- [ ] **Step 4: Start only the new services and verify private API reachability**

Run: `docker compose up -d proxy_redis proxy_pool && docker compose ps proxy_redis proxy_pool && docker compose exec proxy_pool sh -c 'wget -qO- http://127.0.0.1:5010/count/'`

Expected: both services are running and the final command returns ProxyPool count JSON. If the image lacks `wget`, use its available HTTP client or execute `uv run` from an already-running project container; do not publish port `5010` to work around it.

- [ ] **Step 5: Commit the Compose deployment**

```bash
git add docker-compose.yml
git commit -m "feat: deploy private ProxyPool services"
```

### Task 4: Keep AkShare Retry and the Diagnostic Tool Provider-Agnostic

**Files:**
- Modify: `test/download/dl/test_downloader_akshare.py:177-249`
- Modify: `test/tools/test_test_proxy.py`
- Modify: `tools/test_proxy.py:40-54`

**Interfaces:**
- Consumes: `utility.proxy.get_proxy() -> dict[str, str]` from Tasks 1-2.
- Produces: an opt-in `uv run tools/test_proxy.py` diagnostic that succeeds in ProxyPool mode without Qingguo credentials and continues to print only sanitized `host:port` output.

- [ ] **Step 1: Write failing diagnostic tests for configured provider modes**

```python
def test_main_allows_proxy_pool_mode_without_qingguo_credentials(monkeypatch, capsys):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(proxy_tool, "_load_dotenv", lambda _: None)
    monkeypatch.setattr(
        proxy_tool.proxy_module,
        "get_proxy",
        lambda: {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
    )
    monkeypatch.setattr(proxy_tool.requests, "get", lambda *args, **kwargs: FakeSuccessResponse())

    assert proxy_tool.main() == 0
    assert "proxy server: 127.0.0.1:8080" in capsys.readouterr().out


def test_main_requires_qingguo_credentials_only_in_qingguo_mode(monkeypatch, capsys):
    monkeypatch.setenv("PROXY_PROVIDER", "qingguo")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(proxy_tool, "_load_dotenv", lambda _: None)

    assert proxy_tool.main() == 1
    assert "QG_PROXY_KEY and QG_PROXY_PWD" in capsys.readouterr().err
```

Add an AkShare test asserting that an initial successful request still makes zero allocation calls and that a transport failure delegates to `get_proxy` exactly once per bounded decorator retry. Keep it independent of provider implementation by monkeypatching `utility.proxy.get_proxy`.

- [ ] **Step 2: Run the added tests to verify they fail**

Run: `uv run pytest test/tools/test_test_proxy.py test/download/dl/test_downloader_akshare.py -k "proxy_pool_mode or qingguo_mode or proxy_refresh" -v`

Expected: the ProxyPool diagnostic test FAILS because the current tool unconditionally requires Qingguo credentials.

- [ ] **Step 3: Make the tool conditional on the selected provider**

```python
def _requires_qingguo_credentials() -> bool:
    return os.getenv("PROXY_PROVIDER", "auto").lower() == "qingguo"


def main() -> int:
    try:
        _load_dotenv(ROOT / ".env")
        if _requires_qingguo_credentials() and (
            not os.getenv("QG_PROXY_KEY") or not os.getenv("QG_PROXY_PWD")
        ):
            raise RuntimeError("QG_PROXY_KEY and QG_PROXY_PWD must be configured in .env")
        # Keep allocation and Baidu request behavior unchanged.
```

Do not add proxy environment variables to the tool or Compose. Preserve `_proxy_server()` as the sole output formatter so userinfo cannot be printed.

- [ ] **Step 4: Run focused runtime behavior tests**

Run: `uv run pytest test/tools/test_test_proxy.py test/download/dl/test_downloader_akshare.py -v`

Expected: PASS; direct-first and bounded AkShare retry behavior remain unchanged.

- [ ] **Step 5: Commit provider-neutral diagnostics**

```bash
git add tools/test_proxy.py test/tools/test_test_proxy.py test/download/dl/test_downloader_akshare.py
git commit -m "test: cover ProxyPool proxy recovery"
```

### Task 5: Document Deployment, Operation, and Rollback

**Files:**
- Modify: `README.md:38-52`

**Interfaces:**
- Consumes: Compose service names and `PROXY_PROVIDER`/`PROXY_POOL_URL` contract from Tasks 1 and 3.
- Produces: operator instructions for starting the pool, checking availability, validating a proxy, switching modes, and keeping ProxyPool private.

- [ ] **Step 1: Replace Qingguo-only configuration documentation**

Document this optional configuration table:

```markdown
| Variable | Default | Description |
|---|---|---|
| `PROXY_PROVIDER` | `auto` | `auto` tries local ProxyPool then Qingguo; `proxy_pool` disables fallback; `qingguo` bypasses the local pool. |
| `PROXY_POOL_URL` | `http://proxy_pool:5010` | Internal ProxyPool API address; do not expose it publicly. |
| `QG_PROXY_KEY` / `QG_PROXY_PWD` | (empty) | Qingguo fallback credentials required for `auto` fallback and `qingguo` mode. |
```

Add exact operational commands:

```bash
docker compose up -d proxy_redis proxy_pool
docker compose ps proxy_redis proxy_pool
docker compose exec proxy_pool sh -c 'wget -qO- http://127.0.0.1:5010/count/'
uv run tools/test_proxy.py
```

State that neither ProxyPool port is host-published, public proxies are untrusted, only AkShare retry recovery uses them, and rollback is `PROXY_PROVIDER=qingguo` followed by restarting the downloading worker/scheduler.

- [ ] **Step 2: Check documentation references and formatting**

Run: `git diff --check -- README.md && rg -n "QG_PROXY|PROXY_POOL|PROXY_PROVIDER|test_proxy" README.md docker-compose.yml utility/proxy.py tools/test_proxy.py`

Expected: exit code `0`; documented variable names and commands match implementation exactly.

- [ ] **Step 3: Commit the operational documentation**

```bash
git add README.md
git commit -m "docs: describe ProxyPool fallback operation"
```

### Task 6: Verify the Integrated Deployment

**Files:**
- Verify only; do not change files unless a failing check identifies a defect.

**Interfaces:**
- Consumes: all implementation and deployment work from Tasks 1-5.
- Produces: evidence that the narrow proxy behavior and rendered Compose stack meet the approved design.

- [ ] **Step 1: Run focused Python checks**

Run: `uv run pytest test/utility/test_proxy.py test/download/dl/test_downloader_akshare.py test/tools/test_test_proxy.py`

Expected: all selected tests pass.

- [ ] **Step 2: Validate Compose and private service definition**

Run: `docker compose config --quiet && docker compose config | rg -n "proxy_pool|proxy_redis|5010:|6379:"`

Expected: exit code `0`; service definitions are present, while no `5010:` or ProxyPool `6379:` host mapping exists.

- [ ] **Step 3: Verify the service at runtime**

Run: `docker compose up -d proxy_redis proxy_pool && docker compose ps proxy_redis proxy_pool && docker compose logs --tail=100 proxy_pool`

Expected: both services are running; logs show scheduler and HTTP API startup without a Redis connection error. Query `/count/` from the container or an eligible internal project container and record the returned JSON.

- [ ] **Step 4: Inspect the final change set**

Run: `git status --short && git diff --check HEAD~6..HEAD && git log --oneline -6`

Expected: no whitespace errors; only intended ProxyPool implementation commits are included. Preserve unrelated pre-existing worktree changes.

- [ ] **Step 5: Report evidence and residual risk**

Report focused test results, Compose validation output, service/API availability, selected provider mode, and the remaining reliability/security limitation: public proxies are best-effort and untrusted, while Qingguo remains the operational rollback path.
