# Qingguo Proxy Live Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use ipify for runtime Qingguo proxy validation and add an opt-in command that reports whether a freshly acquired authenticated proxy can reach it.

**Architecture:** `utility.proxy.get_proxy()` remains the sole implementation for obtaining and authenticating a Qingguo proxy; only its health-check target changes. The new standalone `tools/test_proxy.py` loads root `.env` credentials, calls that helper, then makes a second bounded ipify request to validate response JSON and print sanitized diagnostics.

**Tech Stack:** Python 3.11+, `requests`, `pytest`, `monkeypatch`, `uv`, Ruff.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Use `https://api.ipify.org?format=json` for both the helper health check and live probe.
- Keep the helper's existing three-attempt bounded retry behavior and proxy environment variable semantics.
- The live probe is opt-in only; no test may make a real network request.
- Load `QG_PROXY_KEY` and `QG_PROXY_PWD` from repository-root `.env` without logging either credential or an authenticated proxy URL.
- Preserve unrelated uncommitted changes in `utility/proxy.py`, `test/utility/test_proxy.py`, and the rest of the worktree.

---

## File Structure

- Modify `utility/proxy.py`: replace the runtime validation URL while retaining current allocation, timeout, retry, and environment update behavior.
- Modify `test/utility/test_proxy.py`: assert the helper probes ipify through the authenticated proxy mapping.
- Create `tools/test_proxy.py`: provide a guarded operational command for live proxy validation and safe diagnostics.
- Create `test/tools/test_test_proxy.py`: mock the operational command's dependencies and verify its success and failure contracts.

### Task 1: Switch Runtime Proxy Health Check To Ipify

**Files:**
- Modify: `utility/proxy.py:54-98`
- Modify: `test/utility/test_proxy.py:121-155`

**Interfaces:**
- Consumes: `QG_PROXY_KEY` and `QG_PROXY_PWD` from the environment.
- Produces: `get_proxy(max_attempts: int = 3) -> dict[str, str]`, returning `{"http": proxy_url, "https": proxy_url}` only after an HTTP 200 health check.

- [ ] **Step 1: Write the failing helper assertion**

In `test_get_proxy_sends_qingguo_key_and_password_from_env`, change the expected second request URL to the exact runtime target:

```python
assert calls[1][0] == "https://api.ipify.org?format=json"
assert calls[1][1]["proxies"] == {"http": expected_proxy, "https": expected_proxy}
assert calls[1][1]["timeout"] == 10
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest test/utility/test_proxy.py::test_get_proxy_sends_qingguo_key_and_password_from_env -v`

Expected: FAIL because `get_proxy()` still calls `https://test.ipw.cn`.

- [ ] **Step 3: Change the helper's validation constant**

Replace the local target assignment in `get_proxy()` with:

```python
test_url = "https://api.ipify.org?format=json"
test = requests.get(test_url, proxies=proxy, timeout=10)
```

Do not alter request parameters for `proxy_api_url`, the retry loop, exception handling, or the lowercase environment variable updates.

- [ ] **Step 4: Run focused helper tests**

Run: `uv run pytest test/utility/test_proxy.py -v`

Expected: PASS. This confirms the new target, credential URL encoding, bounded failures, and proxy refresh behavior remain covered without live network access.

- [ ] **Step 5: Inspect the isolated helper diff**

Run: `git diff -- utility/proxy.py test/utility/test_proxy.py`

Expected: only the ipify assertion and runtime validation URL are added to the existing local proxy changes. Do not stage or commit because the worktree contains unrelated user changes and no commit was requested.

### Task 2: Add Sanitized Live Proxy Probe

**Files:**
- Create: `tools/test_proxy.py`
- Create: `test/tools/test_test_proxy.py`

**Interfaces:**
- Consumes: root `.env`, `utility.proxy.get_proxy() -> dict[str, str]`, and `requests.get(url, proxies=..., timeout=...)`.
- Produces: `main() -> int`; returns `0` on a valid proxied ipify response, otherwise `1`; `if __name__ == "__main__": raise SystemExit(main())` exposes `uv run tools/test_proxy.py`.

- [ ] **Step 1: Write failing tests for dotenv and successful probe**

Create `test/tools/test_test_proxy.py`. Import the script module from its file path using `importlib.util.spec_from_file_location` so the test does not require `tools` to be a package. Mock `proxy_module.get_proxy`, `requests.get`, and output capture. Cover a success path that writes a temporary root `.env` with both credentials, returns a safe proxy mapping, and supplies:

```python
class IpifyResponse:
    status_code = 200

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload
```

Use this concrete fixture and test shape:

```python
@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("test_proxy_script", SCRIPT_PATH)
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script

def test_main_reports_sanitized_egress_ip(module, monkeypatch, tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    proxy = {"http": "http://secret-key:secret-password@203.0.113.2:8080",
             "https": "http://secret-key:secret-password@203.0.113.2:8080"}
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: proxy)
    calls = []
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, **kwargs: calls.append((url, kwargs)) or IpifyResponse({"ip": "203.0.113.10"}),
    )

    assert module.main() == 0
    captured = capsys.readouterr()
    assert calls == [(module.IPIFY_URL, {"proxies": proxy, "timeout": module.REQUEST_TIMEOUT})]
    assert "proxy server: 203.0.113.2:8080" in captured.out
    assert "egress ip: 203.0.113.10" in captured.out
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err
    assert "@" not in captured.out + captured.err
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `uv run pytest test/tools/test_test_proxy.py -v`

Expected: FAIL because `tools/test_proxy.py` does not exist.

- [ ] **Step 3: Implement the smallest operational script**

Create `tools/test_proxy.py` with these explicit units:

```python
IPIFY_URL = "https://api.ipify.org?format=json"
REQUEST_TIMEOUT = 10

def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            os.environ.setdefault(name, value.strip().strip('"').strip("'"))

def _proxy_server(proxy_url: str) -> str:
    parsed = urlsplit(proxy_url)
    if not parsed.hostname or parsed.port is None:
        raise ValueError("Proxy URL does not contain a server address")
    return f"{parsed.hostname}:{parsed.port}"

def main() -> int:
    try:
        _load_dotenv(ROOT / ".env")
        if not os.getenv("QG_PROXY_KEY") or not os.getenv("QG_PROXY_PWD"):
            raise RuntimeError("QG_PROXY_KEY and QG_PROXY_PWD must be configured in .env")
        started = time.monotonic()
        proxies = proxy_module.get_proxy()
        response = requests.get(IPIFY_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        ip = payload.get("ip") if isinstance(payload, dict) else None
        if not isinstance(ip, str) or not ip:
            raise ValueError("ipify response does not contain a usable ip")
        print(f"proxy server: {_proxy_server(proxies['https'])}")
        print(f"egress ip: {ip}")
        print(f"elapsed ms: {round((time.monotonic() - started) * 1000)}")
        return 0
    except (FileNotFoundError, ProxyError, requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"proxy test failed: {exc}", file=sys.stderr)
        return 1
```

Set `ROOT = Path(__file__).resolve().parents[1]` and add it to `sys.path` before importing `utility.proxy`. Use `urllib.parse.urlsplit` in `_proxy_server` so output removes `username:password@`. Catch `FileNotFoundError`, `ProxyError`, `requests.RequestException`, `ValueError`, and `RuntimeError`; print `proxy test failed: <message>` to stderr and return `1`. Do not include exception representations that could contain proxy credentials.

- [ ] **Step 4: Add failure-path tests**

Add deterministic tests with these concrete assertions:

```python
def test_main_rejects_missing_proxy_password(module, monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: pytest.fail("must not allocate"))
    assert module.main() == 1
    assert "QG_PROXY_KEY and QG_PROXY_PWD must be configured" in capsys.readouterr().err

def test_main_rejects_ipify_response_without_ip(module, monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    proxy = {"http": "http://secret-key:secret-password@203.0.113.2:8080",
             "https": "http://secret-key:secret-password@203.0.113.2:8080"}
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: proxy)
    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: IpifyResponse({}))
    assert module.main() == 1
    captured = capsys.readouterr()
    assert "ipify response does not contain a usable ip" in captured.err
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err

def test_main_handles_proxy_allocation_failure(module, monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module.proxy_module,
        "get_proxy",
        lambda: (_ for _ in ()).throw(module.ProxyError("allocation failed")),
    )
    assert module.main() == 1
    captured = capsys.readouterr()
    assert "proxy test failed: allocation failed" in captured.err
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err
```

Define `IpifyResponse` in the test module so it accepts a payload and exposes `raise_for_status()` plus `json()`, then mock `requests.get` in every test that reaches the ipify request. Live network calls are prohibited.

- [ ] **Step 5: Run the new test module**

Run: `uv run pytest test/tools/test_test_proxy.py -v`

Expected: PASS for dotenv loading, missing credentials, successful sanitized diagnostics, invalid ipify JSON, and proxy acquisition failure.

- [ ] **Step 6: Run lint and combined proxy-focused tests**

Run: `uv run ruff check utility/proxy.py tools/test_proxy.py test/utility/test_proxy.py test/tools/test_test_proxy.py && uv run pytest test/utility/test_proxy.py test/tools/test_test_proxy.py -v`

Expected: Ruff exits `0`; all focused tests pass.

- [ ] **Step 7: Inspect the standalone probe diff**

Run: `git diff -- tools/test_proxy.py test/tools/test_test_proxy.py`

Expected: the script only loads local credentials, reports sanitized server and egress diagnostics, and uses no real network calls in tests. Do not stage or commit unless the user explicitly asks.

### Task 3: Perform An Opt-In Live Validation

**Files:**
- Verify: `tools/test_proxy.py`

**Interfaces:**
- Consumes: valid root `.env` values for `QG_PROXY_KEY` and `QG_PROXY_PWD` plus external Qingguo and ipify network availability.
- Produces: a process status and sanitized diagnostics for one allocated proxy.

- [ ] **Step 1: Confirm the local credential file is present without displaying it**

Run: `test -f .env`

Expected: exit `0`. If missing, do not create credentials; report that the optional live validation was skipped.

- [ ] **Step 2: Run the live probe once**

Run: `uv run tools/test_proxy.py`

Expected on success: exit `0` and output containing a proxy server, `egress ip:`, and elapsed time, with no key, password, or authenticated URL. On failure: exit `1` with a sanitized reason; preserve this output as evidence that the external allocation or tunnel is unavailable.

- [ ] **Step 3: Inspect the final intended diff**

Run: `git diff -- utility/proxy.py test/utility/test_proxy.py tools/test_proxy.py test/tools/test_test_proxy.py`

Expected: only the ipify endpoint change, standalone probe, and focused tests are present; no unrelated worktree changes are included.
