# Qingguo Proxy Failure Address Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log Qingguo's `proxy_ip` and `server` for each acquired proxy whose ipify health check fails, without exposing credentials.

**Architecture:** Keep the existing authenticated proxy mapping returned by `_build_proxy_from_response()`. Extend the parsed proxy result with the provider's safe diagnostic fields, carry them only within `get_proxy()` while a health check is attempted, and include them in failure warnings. A mocked log assertion prevents credential leakage.

**Tech Stack:** Python 3.12, `requests`, `pytest`, `caplog`, Ruff, `uv`.

## Global Constraints

- Use `uv run` for Python commands.
- Preserve the exact health-check URL `https://api.ipify.org?format=json`, current timeouts, retry count, authentication URL construction, and proxy environment semantics.
- Print Qingguo `proxy_ip` only if it is a string, and print the validated `server` as `IP:port`.
- Never log the authenticated proxy URL, `QG_PROXY_KEY`, or `QG_PROXY_PWD`.
- Provider-response and transport failures without a usable proxy address retain their existing diagnostics.

---

## File Structure

- Modify `utility/proxy.py`: preserve safe response diagnostics while retaining the existing `dict[str, str]` public return from `get_proxy()`.
- Modify `test/utility/test_proxy.py`: add a fully mocked health-check failure log test.

### Task 1: Log Safe Addresses On Proxy Health-Check Failure

**Files:**
- Modify: `utility/proxy.py:26-98`
- Modify: `test/utility/test_proxy.py:63-104`

**Interfaces:**
- Consumes: successful Qingguo item `{"proxy_ip": str, "server": "IP:port"}` and health-check response status.
- Produces: unchanged `get_proxy(max_attempts: int = 3) -> dict[str, str]`; its non-200 health-check warning includes `proxy_ip=<value>` and `server=<value>`.

- [ ] **Step 1: Write the failing log test**

Add a test that mocks the provider response and a non-200 ipify result:

```python
def test_get_proxy_logs_safe_address_when_health_check_fails(monkeypatch, caplog):
    _set_proxy_credentials(monkeypatch)

    class ProviderResponse:
        def json(self):
            return {
                "code": "SUCCESS",
                "data": [{"proxy_ip": "203.0.113.9", "server": "203.0.113.9:8080"}],
            }

    class HealthCheckResponse:
        status_code = 408

    def fake_get(url, **kwargs):
        return ProviderResponse() if url == proxy_module.proxy_api_url else HealthCheckResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProxyError, match="Failed to get working proxy after 1 attempts"):
            proxy_module.get_proxy(max_attempts=1)

    assert "proxy_ip=203.0.113.9" in caplog.text
    assert "server=203.0.113.9:8080" in caplog.text
    assert "test-key" not in caplog.text
    assert "test-pwd" not in caplog.text
    assert "@" not in caplog.text
```

- [ ] **Step 2: Verify the test fails before implementation**

Run: `uv run pytest test/utility/test_proxy.py::test_get_proxy_logs_safe_address_when_health_check_fails -v`

Expected: FAIL because the existing warning has only HTTP status and attempt counters.

- [ ] **Step 3: Preserve safe response metadata internally**

Keep `_build_proxy_from_response()`'s public return type unchanged. In `get_proxy()`, after `proxy = _build_proxy_from_response(resp.json())`, derive the provider `server` and optional `proxy_ip` from the already parsed successful response through a focused helper that returns only safe fields:

```python
def _proxy_diagnostics(proxy_json: object) -> tuple[str | None, str]:
    if not isinstance(proxy_json, dict):
        raise ValueError("Expected proxy response object")
    proxy_data = proxy_json.get("data")
    if not isinstance(proxy_data, list) or not proxy_data or not isinstance(proxy_data[0], dict):
        raise ValueError("Missing usable proxy data")
    first_proxy = proxy_data[0]
    server = first_proxy.get("server")
    if not isinstance(server, str) or ":" not in server:
        raise ValueError("Missing usable proxy server")
    proxy_ip = first_proxy.get("proxy_ip")
    return (proxy_ip if isinstance(proxy_ip, str) else None, server)
```

Store `proxy_response = resp.json()` once, then call `_build_proxy_from_response(proxy_response)` and `_proxy_diagnostics(proxy_response)`. Call the helper only after `_build_proxy_from_response()` has validated the response. Update the non-200 warning to use safe field formatting:

```python
logging.warning(
    "Proxy test failed for proxy_ip=%s, server=%s with status %s on attempt %d/%d",
    proxy_ip,
    server,
    test.status_code,
    attempt,
    max_attempts,
)
```

Do not log `proxy`, its `http`/`https` values, environment variables, or the raw response.

- [ ] **Step 4: Run focused proxy tests**

Run: `uv run pytest test/utility/test_proxy.py -v`

Expected: PASS, including existing credentials/URL-encoding checks and the new safe diagnostic assertion.

- [ ] **Step 5: Run formatting and inspect the diff**

Run: `uv run ruff check utility/proxy.py test/utility/test_proxy.py && git diff --check && git diff -- utility/proxy.py test/utility/test_proxy.py`

Expected: all checks exit `0`; the diff only adds safe diagnostics and its test.
