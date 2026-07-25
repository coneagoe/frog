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
    monkeypatch.delenv(missing_variable)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("proxy API should not be called without credentials")

    monkeypatch.setattr(proxy_module.requests, "get", fail_if_called)

    with pytest.raises(ProxyError, match="QG_PROXY_KEY and QG_PROXY_PWD must be configured"):
        proxy_module.get_proxy()


def test_get_proxy_sends_qingguo_key_and_password_from_env(monkeypatch):
    _set_proxy_credentials(monkeypatch)
    monkeypatch.setenv("QG_PROXY_KEY", "key:user")
    monkeypatch.setenv("QG_PROXY_PWD", "p@ss/word")
    calls = []

    class ProxyApiResponse:
        def json(self):
            return {"code": "SUCCESS", "data": [{"server": "127.0.0.1:8080"}]}

    class ProxyTestResponse:
        status_code = proxy_module.requests.codes.ok

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == proxy_module.proxy_api_url:
            return ProxyApiResponse()
        return ProxyTestResponse()

    monkeypatch.setattr(proxy_module.requests, "get", fake_get)

    expected_proxy = "http://key%3Auser:p%40ss%2Fword@127.0.0.1:8080"
    assert proxy_module.get_proxy() == {"http": expected_proxy, "https": expected_proxy}
    assert calls[1][0] == "https://api.ipify.org?format=json"
    assert calls[1][1]["proxies"] == {"http": expected_proxy, "https": expected_proxy}
    assert calls[1][1]["timeout"] == 10
    assert proxy_module.os.environ["http_proxy"] == expected_proxy
    assert proxy_module.os.environ["https_proxy"] == expected_proxy

    proxy_api_call = calls[0]
    assert proxy_api_call[0] == proxy_module.proxy_api_url
    assert proxy_api_call[1]["params"] == {
        "key": "key:user",
        "num": 1,
        "distinct": True,
    }
