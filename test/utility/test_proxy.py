import logging
import sys
from pathlib import Path

import pytest
from requests.exceptions import ConnectionError, ProxyError, RequestException

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import proxy as proxy_module  # noqa: E402


def _set_proxy_credentials(monkeypatch):
    monkeypatch.setenv("QG_PROXY_KEY", "test-key")
    monkeypatch.setenv("QG_PROXY_PWD", "test-pwd")


def test_get_proxy_uses_proxy_pool_without_qingguo_credentials(monkeypatch):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.setenv("PROXY_POOL_URL", "http://pool:5010/")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    calls = []

    class PoolResponse:
        def json(self):
            return {"proxy": "127.0.0.1:8080", "https": True}

        def raise_for_status(self):
            return None

    class HealthResponse:
        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == proxy_module.PROXY_HEALTHCHECK_URL:
            return HealthResponse()
        return PoolResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    assert proxy_module.get_proxy() == {
        "http": "http://127.0.0.1:8080",
        "https": "http://127.0.0.1:8080",
    }
    assert calls == [
        ("http://pool:5010/get/", {"params": {"type": "http"}, "timeout": 5}),
        (
            proxy_module.PROXY_HEALTHCHECK_URL,
            {
                "proxies": {
                    "http": "http://127.0.0.1:8080",
                    "https": "http://127.0.0.1:8080",
                },
                "timeout": 10,
            },
        ),
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


def test_get_proxy_auto_falls_back_to_qingguo_after_proxy_pool_failure(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.delenv("PROXY_PROVIDER", raising=False)
    calls = []

    class QingguoResponse:
        def json(self):
            return {"code": "SUCCESS", "data": [{"server": "127.0.0.1:8080"}]}

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/get/"):
            raise RequestException("ProxyPool unavailable")
        if url == proxy_module.PROXY_HEALTHCHECK_URL:
            return QingguoResponse()
        return QingguoResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    expected_proxy = "http://test-key:test-pwd@127.0.0.1:8080"
    assert proxy_module.get_proxy(max_attempts=1) == {
        "http": expected_proxy,
        "https": expected_proxy,
    }
    assert calls == [
        "http://proxy_pool:5010/get/",
        proxy_module.proxy_api_url,
        proxy_module.PROXY_HEALTHCHECK_URL,
    ]


def test_get_proxy_auto_surfaces_sanitized_proxy_pool_failure(monkeypatch, caplog):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.delenv("PROXY_PROVIDER", raising=False)
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_proxy_pool",
        lambda: (_ for _ in ()).throw(ValueError("ProxyPool returned http://pool-user:pool-pass@pool:5010")),
    )
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_qingguo",
        lambda: (_ for _ in ()).throw(RequestException("Qingguo unavailable")),
    )
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(ProxyError, match="Failed to get working proxy after 1 attempts"),
    ):
        proxy_module.get_proxy(max_attempts=1)

    assert "after ProxyPool error: ProxyPool returned http://[REDACTED]@pool:5010" in caplog.text
    assert "pool-user" not in caplog.text
    assert "pool-pass" not in caplog.text


def test_change_proxy_does_not_refresh_proxy_before_first_attempt(monkeypatch):
    get_proxy_calls = 0

    def fake_get_proxy():
        nonlocal get_proxy_calls
        get_proxy_calls += 1
        return {"http": "http://new:8080", "https": "http://new:8080"}

    monkeypatch.setattr(proxy_module, "get_proxy", fake_get_proxy)

    @proxy_module.change_proxy
    def fetch_data():
        return "ok"

    assert fetch_data() == "ok"
    assert get_proxy_calls == 0


def test_change_proxy_refreshes_proxy_after_connection_error(monkeypatch):
    attempts = 0
    get_proxy_calls = 0

    def fake_get_proxy():
        nonlocal get_proxy_calls
        get_proxy_calls += 1
        return {"http": "http://new:8080", "https": "http://new:8080"}

    monkeypatch.setattr(proxy_module, "get_proxy", fake_get_proxy)
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    @proxy_module.change_proxy
    def fetch_data():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("proxy failed")
        return "ok"

    assert fetch_data() == "ok"
    assert attempts == 2
    assert get_proxy_calls == 1


def test_get_proxy_raises_after_bounded_malformed_provider_responses(monkeypatch, caplog):
    _set_proxy_credentials(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"msg": "illegal"}

    monkeypatch.setattr(proxy_module.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ProxyError, match="Failed to get working proxy after 2 attempts"):
            proxy_module.get_proxy(max_attempts=2)

    assert "Malformed proxy response" in caplog.text


def test_get_proxy_raises_after_bounded_non_success_provider_responses(monkeypatch):
    _set_proxy_credentials(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"code": "ERROR", "data": [{"server": "127.0.0.1:8080"}]}

    monkeypatch.setattr(proxy_module.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with pytest.raises(ProxyError, match="Failed to get working proxy after 2 attempts"):
        proxy_module.get_proxy(max_attempts=2)


def test_get_proxy_raises_after_bounded_request_failures(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setattr(
        proxy_module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RequestException("ssl eof")),
    )
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with pytest.raises(ProxyError, match="Failed to get working proxy after 2 attempts"):
        proxy_module.get_proxy(max_attempts=2)


@pytest.mark.parametrize("missing_variable", ["QG_PROXY_KEY", "QG_PROXY_PWD"])
def test_get_proxy_requires_qingguo_credentials_before_request(monkeypatch, missing_variable):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setenv("PROXY_PROVIDER", "qingguo")
    monkeypatch.delenv(missing_variable)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("proxy API should not be called without credentials")

    monkeypatch.setattr(proxy_module.requests, "get", fail_if_called)

    with pytest.raises(ProxyError, match="QG_PROXY_KEY and QG_PROXY_PWD must be configured"):
        proxy_module.get_proxy()


def test_get_proxy_sends_qingguo_key_and_password_from_env(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setenv("PROXY_PROVIDER", "qingguo")
    monkeypatch.setenv("QG_PROXY_KEY", "key:user")
    monkeypatch.setenv("QG_PROXY_PWD", "p@ss/word")
    calls = []

    class ProxyApiResponse:
        def json(self):
            return {"code": "SUCCESS", "data": [{"server": "127.0.0.1:8080"}]}

        def raise_for_status(self):
            return None

    class HealthResponse:
        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == proxy_module.PROXY_HEALTHCHECK_URL:
            return HealthResponse()
        assert url == proxy_module.proxy_api_url
        return ProxyApiResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    expected_proxy = "http://key%3Auser:p%40ss%2Fword@127.0.0.1:8080"
    assert proxy_module.get_proxy() == {"http": expected_proxy, "https": expected_proxy}
    assert calls == [
        (
            proxy_module.proxy_api_url,
            {"params": {"key": "key:user", "num": 1, "distinct": True}, "timeout": 5},
        ),
        (
            proxy_module.PROXY_HEALTHCHECK_URL,
            {"proxies": {"http": expected_proxy, "https": expected_proxy}, "timeout": 10},
        ),
    ]
    assert proxy_module.os.environ["http_proxy"] == expected_proxy
    assert proxy_module.os.environ["https_proxy"] == expected_proxy


def test_auto_falls_back_to_qingguo_after_proxy_pool_validation_failure(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setenv("PROXY_PROVIDER", "auto")
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_proxy_pool",
        lambda: (
            "127.0.0.1:8080",
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
        ),
    )
    validation_calls = 0

    def validate_proxy(proxies):
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            raise ProxyError("egress unavailable")

    monkeypatch.setattr(proxy_module, "_validate_proxy", validate_proxy)
    deleted: list[str] = []
    monkeypatch.setattr(proxy_module, "_delete_proxy_from_pool", deleted.append)
    qingguo_proxy = {
        "http": "http://key:pwd@127.0.0.2:8080",
        "https": "http://key:pwd@127.0.0.2:8080",
    }
    monkeypatch.setattr(proxy_module, "_get_proxy_from_qingguo", lambda: qingguo_proxy)

    assert proxy_module.get_proxy(max_attempts=1) == qingguo_proxy
    assert deleted == ["127.0.0.1:8080"]
    assert validation_calls == 2


def test_pool_eviction_never_hides_original_validation_failure(monkeypatch, caplog):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.setattr(
        proxy_module,
        "_get_proxy_from_proxy_pool",
        lambda: (
            "127.0.0.1:8080",
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
        ),
    )
    monkeypatch.setattr(
        proxy_module,
        "_validate_proxy",
        lambda proxies: (_ for _ in ()).throw(ProxyError("egress unavailable")),
    )
    monkeypatch.setattr(
        proxy_module,
        "_delete_proxy_from_pool",
        lambda _: (_ for _ in ()).throw(RequestException("api down")),
    )

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(ProxyError, match="Failed to get working proxy after 1 attempts"),
    ):
        proxy_module.get_proxy(max_attempts=1)

    assert "api down" in caplog.text
    assert "egress unavailable" in caplog.text
