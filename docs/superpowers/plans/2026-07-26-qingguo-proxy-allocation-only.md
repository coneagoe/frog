# Qingguo Proxy Allocation-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `get_proxy()` return a validated Qingguo allocation immediately, without testing downstream connectivity, while retaining the standalone one-shot Baidu diagnostic.

**Architecture:** `get_proxy()` owns Qingguo provider request/retry, provider-response validation, authenticated proxy construction, and lowercase proxy environment installation. It no longer issues a Baidu request. Actual downstream failures remain the responsibility of `change_proxy` for production downloader calls, while `tools/test_proxy.py` remains a separate, one-shot manual Baidu HTTPS test.

**Tech Stack:** Python 3.12, `requests`, `pytest`, Ruff, `uv`.

## Global Constraints

- Use `uv run` for Python commands.
- `get_proxy()` must not make any downstream request to `https://www.baidu.com` or another connectivity target.
- Preserve the existing three-attempt Qingguo provider allocation retry, one-second inter-attempt wait, authenticated proxy URL construction, request parameters, and lowercase proxy environment semantics.
- Retry only Qingguo provider request failures, malformed responses, and non-success provider responses; missing credentials remain a non-retryable configuration error.
- `change_proxy` remains responsible for refreshing the proxy after downstream `ConnectionError` or `ProxyError`.
- `tools/test_proxy.py` remains an explicit one-shot Baidu HTTPS test; it does not retry or acquire another proxy after a downstream request failure.
- Never print or log the authenticated proxy URL, key, password, or raw Qingguo response.
- Tests must mock all network calls.

---

## File Structure

- Modify `utility/proxy.py`: remove downstream health-check and its safe-address log branches from `get_proxy()` while retaining allocation validation/retry and environment setup.
- Modify `test/utility/test_proxy.py`: replace health-check tests with allocation-only assertions and preserve existing allocation/refresh coverage.
- Modify `test/tools/test_test_proxy.py`: retain the manual one-shot Baidu tests and clarify the allocation succeeds before its separate request fails.
- Modify `docs/superpowers/specs/2026-07-25-qingguo-proxy-live-test-design.md`: already updated as the approved design source; do not make unrelated documentation changes.

### Task 1: Return Qingguo Allocations Without Downstream Validation

**Files:**
- Modify: `utility/proxy.py:54-128`
- Modify: `test/utility/test_proxy.py:63-213`
- Modify: `test/tools/test_test_proxy.py:62-108`

**Interfaces:**
- Consumes: `QG_PROXY_KEY`, `QG_PROXY_PWD`, and Qingguo provider response `{"code": "SUCCESS", "data": [{"server": "IP:port"}]}`.
- Produces: unchanged `get_proxy(max_attempts: int = 3) -> dict[str, str]`; on the first valid allocation, installs `http_proxy`/`https_proxy` and returns the authenticated mapping without requesting any downstream target.

- [ ] **Step 1: Replace health-check tests with allocation-only expectations**

Remove `test_get_proxy_logs_safe_address_when_health_check_fails` and `test_get_proxy_omits_missing_proxy_ip_when_health_check_fails`, because `get_proxy()` will not perform any health check.

Update `test_get_proxy_sends_qingguo_key_and_password_from_env` to use a provider-only fake and assert one request only:

```python
def fake_get(url, **kwargs):
    calls.append((url, kwargs))
    assert url == proxy_module.proxy_api_url
    return ProxyApiResponse()

assert proxy_module.get_proxy() == {"http": expected_proxy, "https": expected_proxy}
assert calls == [
    (
        proxy_module.proxy_api_url,
        {"params": {"key": "key:user", "num": 1, "distinct": True}, "timeout": 5},
    )
]
assert proxy_module.os.environ["http_proxy"] == expected_proxy
assert proxy_module.os.environ["https_proxy"] == expected_proxy
```

This replaces assertions for `https://www.baidu.com`, `proxies`, and the 10-second health-check timeout.

- [ ] **Step 2: Run the focused helper test to verify it fails**

Run: `uv run pytest test/utility/test_proxy.py::test_get_proxy_sends_qingguo_key_and_password_from_env -v`

Expected: FAIL because current `get_proxy()` still issues the downstream Baidu request and the fake no longer returns a health-check response.

- [ ] **Step 3: Remove downstream validation from `get_proxy()`**

In `utility/proxy.py`, retain this provider allocation flow:

```python
resp = requests.get(proxy_api_url, params=proxy_params, timeout=5)
proxy = _build_proxy_from_response(resp.json())
os.environ["http_proxy"] = proxy["http"]
os.environ["https_proxy"] = proxy["https"]
return proxy
```

Remove `_proxy_diagnostics()`, `proxy_response`, the `https://www.baidu.com` request, HTTP-status condition, and both downstream health-check warning branches. Keep the existing `except RequestException` and `except ValueError` allocation retry handling, `time.sleep(1)`, and terminal `ProxyError` unchanged.

- [ ] **Step 4: Make the manual failure test prove one-shot behavior**

In `test/tools/test_test_proxy.py::test_main_handles_non_success_baidu_response`, count `get_proxy` and `requests.get` calls:

```python
get_proxy_calls = 0

def fake_get_proxy():
    nonlocal get_proxy_calls
    get_proxy_calls += 1
    return proxy

monkeypatch.setattr(module.proxy_module, "get_proxy", fake_get_proxy)
calls = []
monkeypatch.setattr(
    module.requests,
    "get",
    lambda url, **kwargs: calls.append((url, kwargs)) or FailedBaiduResponse(),
)

assert module.main() == 1
assert get_proxy_calls == 1
assert calls == [(module.BAIDU_URL, {"proxies": proxy, "timeout": module.REQUEST_TIMEOUT})]
```

Keep the existing sanitized stderr assertions. This proves the script does not reallocate/retry after its single downstream failure.

- [ ] **Step 5: Run focused verification**

Run: `uv run pytest test/utility/test_proxy.py test/tools/test_test_proxy.py -v && uv run ruff check utility/proxy.py test/utility/test_proxy.py tools/test_proxy.py test/tools/test_test_proxy.py && git diff --check`

Expected: all tests pass; Ruff and whitespace checks exit `0`.

- [ ] **Step 6: Inspect exact scope**

Run: `git diff -- utility/proxy.py test/utility/test_proxy.py test/tools/test_test_proxy.py`

Expected: `get_proxy()` contains no Baidu/downstream request; its response validation and allocation retries remain; the tool still makes exactly one Baidu request; no credentials or raw response become output.
