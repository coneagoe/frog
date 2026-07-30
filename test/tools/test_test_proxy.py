import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "tools" / "test_proxy.py"


class BaiduResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("test_proxy_script", SCRIPT_PATH)
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_main_reports_sanitized_proxy_server(module, monkeypatch, tmp_path, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    proxy = {
        "http": "http://secret-key:secret-password@203.0.113.2:8080",
        "https": "http://secret-key:secret-password@203.0.113.2:8080",
    }
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: proxy)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs: object) -> BaiduResponse:
        calls.append((url, kwargs))
        return BaiduResponse()

    monkeypatch.setattr(
        module.requests,
        "get",
        fake_get,
    )

    assert module.main() == 0
    captured = capsys.readouterr()
    assert calls == [(module.BAIDU_URL, {"proxies": proxy, "timeout": module.REQUEST_TIMEOUT})]
    assert "proxy server: 203.0.113.2:8080" in captured.out
    assert "elapsed ms:" in captured.out
    assert "egress ip:" not in captured.out
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err
    assert "@" not in captured.out + captured.err


def test_main_allows_proxy_pool_mode_without_qingguo_credentials(module, monkeypatch, capsys):
    monkeypatch.setenv("PROXY_PROVIDER", "proxy_pool")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(module, "_load_dotenv", lambda _: None)
    monkeypatch.setattr(
        module.proxy_module,
        "get_proxy",
        lambda: {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
    )
    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: BaiduResponse())

    assert module.main() == 0
    assert "proxy server: 127.0.0.1:8080" in capsys.readouterr().out


def test_main_requires_qingguo_credentials_only_in_qingguo_mode(module, monkeypatch, capsys):
    monkeypatch.setenv("PROXY_PROVIDER", "qingguo")
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(module, "_load_dotenv", lambda _: None)

    assert module.main() == 1
    assert "QG_PROXY_KEY and QG_PROXY_PWD" in capsys.readouterr().err


def test_main_rejects_missing_proxy_password(module, monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setenv("PROXY_PROVIDER", "qingguo")
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    monkeypatch.setattr(module.proxy_module, "get_proxy", lambda: pytest.fail("must not allocate"))

    assert module.main() == 1
    assert "QG_PROXY_KEY and QG_PROXY_PWD must be configured" in capsys.readouterr().err


def test_main_handles_non_success_baidu_response(module, monkeypatch, tmp_path, capsys):
    class FailedBaiduResponse:
        def raise_for_status(self) -> None:
            raise module.requests.HTTPError("503 Service Unavailable")

    (tmp_path / ".env").write_text("QG_PROXY_KEY=secret-key\nQG_PROXY_PWD=secret-password\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    proxy = {
        "http": "http://secret-key:secret-password@203.0.113.2:8080",
        "https": "http://secret-key:secret-password@203.0.113.2:8080",
    }
    get_proxy_calls = 0

    def fake_get_proxy():
        nonlocal get_proxy_calls
        get_proxy_calls += 1
        return proxy

    monkeypatch.setattr(module.proxy_module, "get_proxy", fake_get_proxy)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_requests_get(url: str, **kwargs: object) -> FailedBaiduResponse:
        calls.append((url, kwargs))
        return FailedBaiduResponse()

    monkeypatch.setattr(
        module.requests,
        "get",
        fake_requests_get,
    )

    assert module.main() == 1
    assert get_proxy_calls == 1
    assert calls == [(module.BAIDU_URL, {"proxies": proxy, "timeout": module.REQUEST_TIMEOUT})]
    captured = capsys.readouterr()
    assert "proxy test failed: 503 Service Unavailable" in captured.err
    assert "secret-key" not in captured.out + captured.err
    assert "secret-password" not in captured.out + captured.err
    assert "@" not in captured.out + captured.err


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
