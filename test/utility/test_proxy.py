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


def test_get_proxy_requires_qingguo_credentials_before_request(monkeypatch):
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("proxy API should not be called without credentials")

    monkeypatch.setattr(proxy_module.requests, "get", fail_if_called)

    with pytest.raises(ProxyError, match="QG_PROXY_KEY and QG_PROXY_PWD must be configured"):
        proxy_module.get_proxy()


def test_get_proxy_sends_qingguo_key_and_password_from_env(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    calls = []

    class ProxyApiResponse:
        def json(self):
            return {"data": [{"server": "127.0.0.1:8080"}]}

    class ProxyTestResponse:
        status_code = proxy_module.requests.codes.ok

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == proxy_module.proxy_api_url:
            return ProxyApiResponse()
        return ProxyTestResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    assert proxy_module.get_proxy() == {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}

    proxy_api_call = calls[0]
    assert proxy_api_call[0] == proxy_module.proxy_api_url
    assert proxy_api_call[1]["params"] == {
        "key": "test-key",
        "pwd": "test-pwd",
        "num": 1,
        "area": "",
        "isp": 0,
        "format": "json",
        "distinct": "true",
    }
