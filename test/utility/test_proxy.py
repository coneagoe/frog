import logging
import sys
from pathlib import Path

import pytest
from requests.exceptions import ConnectionError, ProxyError, RequestException

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import proxy as proxy_module  # noqa: E402


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


def test_get_proxy_raises_after_bounded_malformed_provider_responses(
    monkeypatch, caplog
):
    class FakeResponse:
        def json(self):
            return {"msg": "illegal"}

    monkeypatch.setattr(
        proxy_module.requests, "get", lambda *args, **kwargs: FakeResponse()
    )
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(
            ProxyError, match="Failed to get working proxy after 2 attempts"
        ):
            proxy_module.get_proxy(max_attempts=2)

    assert "Malformed proxy response" in caplog.text


def test_get_proxy_raises_after_bounded_request_failures(monkeypatch):
    monkeypatch.setattr(
        proxy_module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RequestException("ssl eof")),
    )
    monkeypatch.setattr(proxy_module.time, "sleep", lambda _: None)

    with pytest.raises(
        ProxyError, match="Failed to get working proxy after 2 attempts"
    ):
        proxy_module.get_proxy(max_attempts=2)
