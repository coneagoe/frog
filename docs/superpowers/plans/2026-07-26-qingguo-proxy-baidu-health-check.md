# Qingguo Proxy Baidu Health Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate Qingguo proxy HTTPS connectivity through `https://www.baidu.com` in both runtime proxy rotation and the opt-in diagnostic command.

**Architecture:** Keep `utility.proxy.get_proxy()` as the common proxy acquisition and health-check implementation, replacing only its target URL. Update `tools/test_proxy.py` to request the same Baidu HTTPS URL, require a successful HTTP response, and emit only the sanitized proxy server plus elapsed time because Baidu does not provide an egress-IP JSON contract.

**Tech Stack:** Python 3.12, `requests`, `pytest`, Ruff, `uv`.

## Global Constraints

- Use `uv run` for Python commands.
- Use the exact HTTPS target `https://www.baidu.com` for the runtime health check and `tools/test_proxy.py` request.
- Preserve existing timeouts, retry count, authenticated proxy construction, Qingguo request parameters, and proxy environment semantics.
- Keep health-check failure diagnostics for safe `proxy_ip` and `server` fields; never log the authenticated proxy URL, key, password, or raw provider response.
- `tools/test_proxy.py` returns `0` after a successful HTTP response and `1` for allocation, transport, or non-success HTTP failures.
- Tests must mock all network calls.

---

## File Structure

- Modify `utility/proxy.py`: replace the runtime health-check URL constant value.
- Modify `test/utility/test_proxy.py`: expect the exact Baidu HTTPS URL in proxy helper tests.
- Modify `tools/test_proxy.py`: replace ipify JSON validation with an HTTP-only Baidu health check and sanitized server/time diagnostics.
- Modify `test/tools/test_test_proxy.py`: update mocked endpoint, output, and failure assertions.
- Modify `README.md`: remove the egress-IP promise from the diagnostic command description.

### Task 1: Align Runtime And Diagnostic Health Checks With Baidu HTTPS

**Files:**
- Modify: `utility/proxy.py:71-125`
- Modify: `test/utility/test_proxy.py:121-185`
- Modify: `tools/test_proxy.py:16-59`
- Modify: `test/tools/test_test_proxy.py:9-104`
- Modify: `README.md:47-52`

**Interfaces:**
- Consumes: `utility.proxy.get_proxy(max_attempts: int = 3) -> dict[str, str]` and `requests.get(url, proxies=..., timeout=...)`.
- Produces: unchanged `get_proxy()` return and retry behavior; `tools.test_proxy.main() -> int` prints `proxy server: IP:port` and `elapsed ms: <integer>` after a successful Baidu request.

- [ ] **Step 1: Change existing test expectations before implementation**

In `test/utility/test_proxy.py`, replace each expected health-check URL with:

```python
assert calls[1][0] == "https://www.baidu.com"
```

In `test/tools/test_test_proxy.py`, replace the response helper with an HTTP-only fake:

```python
class BaiduResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None
```

Rename the success test to `test_main_reports_sanitized_proxy_server`. Assert the request equals:

```python
assert calls == [
    (module.BAIDU_URL, {"proxies": proxy, "timeout": module.REQUEST_TIMEOUT})
]
```

Assert stdout contains `proxy server: 203.0.113.2:8080` and `elapsed ms:`, does not contain `egress ip:`, `secret-key`, `secret-password`, or `@`.

Replace the invalid-ipify test with a non-success HTTP response test:

```python
class FailedBaiduResponse:
    def raise_for_status(self) -> None:
        raise module.requests.HTTPError("503 Service Unavailable")

def test_main_handles_non_success_baidu_response(module, monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    proxy = {
        "http": "http://secret-key:secret-password@203.0.113.2:8080",
        "https": "http://secret-key:secret-password@203.0.113.2:8080",
    }
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: proxy)
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FailedBaiduResponse(),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "proxy test failed: 503 Service Unavailable" in captured.err
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err
    assert "@" not in captured.out + captured.err
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest test/utility/test_proxy.py test/tools/test_test_proxy.py -v`

Expected: FAIL because production code still uses `https://api.ipify.org?format=json` and still expects a JSON `ip` field.

- [ ] **Step 3: Replace the runtime target**

In `utility/proxy.py`, replace only the health-check assignment:

```python
test_url = "https://www.baidu.com"
```

Keep `requests.get(test_url, proxies=proxy, timeout=10)`, the HTTP-200 requirement, current safe address warnings, all retry behavior, and proxy environment updates unchanged.

- [ ] **Step 4: Simplify the live probe to HTTP-only validation**

In `tools/test_proxy.py`, replace the endpoint constant and remove JSON parsing:

```python
BAIDU_URL = "https://www.baidu.com"
REQUEST_TIMEOUT = 10

response = requests.get(BAIDU_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
response.raise_for_status()
print(f"proxy server: {_proxy_server(proxies['https'])}")
print(f"elapsed ms: {round((time.monotonic() - started) * 1000)}")
return 0
```

Remove `IPIFY_URL`, `payload = response.json()`, the `ip` validation, and the `egress ip` output. Keep the existing exception set and the safe `_proxy_server()` parser.

- [ ] **Step 5: Update the README command output description**

Replace the existing claim with:

```markdown
The command prints a sanitized proxy server address and elapsed time.
```

- [ ] **Step 6: Run focused validation**

Run: `uv run pytest test/utility/test_proxy.py test/tools/test_test_proxy.py -v && uv run ruff check utility/proxy.py tools/test_proxy.py test/utility/test_proxy.py test/tools/test_test_proxy.py && git diff --check`

Expected: all focused tests pass; Ruff and whitespace validation exit `0`.

- [ ] **Step 7: Inspect exact scope**

Run: `git diff -- utility/proxy.py test/utility/test_proxy.py tools/test_proxy.py test/tools/test_test_proxy.py README.md`

Expected: the diff changes the probe target, removes only ipify-specific JSON/egress behavior, updates mocks/output text, and preserves all unrelated proxy behavior.
