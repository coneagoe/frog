import json
import uuid

from paper_trading.api.auth_evidence import (
    AuthEvidenceCode,
    allowed_evidence_path,
    new_request_id,
    render_evidence,
    validate_request_id,
)

pytest_plugins = ("test.paper_trading.api.test_auth_api",)


def test_auth_evidence_helpers_validate_ids_allowlisted_paths_and_emit_one_line_json():
    request_id = new_request_id()
    assert validate_request_id(request_id) == request_id
    assert uuid.UUID(request_id).version == 4
    assert validate_request_id("not-a-uuid") is None
    assert allowed_evidence_path("/auth/login")
    assert allowed_evidence_path("/paper/accounts")
    assert not allowed_evidence_path("/admin/secret")
    try:
        render_evidence(AuthEvidenceCode.AUTH_RATE_LIMITED, "/admin/secret")
    except ValueError:
        pass
    else:
        raise AssertionError("non-auth evidence path must be rejected")

    output = render_evidence(AuthEvidenceCode.AUTH_RATE_LIMITED, "/auth/login", request_id)
    assert "\n" not in output
    assert json.loads(output) == {
        "code": "AUTH_RATE_LIMITED",
        "path": "/auth/login",
        "request_id": request_id,
    }


def test_login_authentication_failures_are_identical_and_have_no_diagnostic_headers(auth_client, monkeypatch):
    client, factory = auth_client
    from test.paper_trading.api.test_auth_api import _FakeRedis, _verified_user

    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", _FakeRedis)
    _verified_user(factory)
    responses = [
        client.post("/auth/login", json={"email": "missing@example.com", "password": "WrongPassword1"}),
        client.post("/auth/login", json={"email": "user@example.com", "password": "WrongPassword1"}),
    ]
    for _ in range(2):
        responses.append(
            client.post("/auth/login", json={"email": "limited@example.com", "password": "WrongPassword1"})
        )
    responses.append(client.post("/auth/login", json={"email": "limited@example.com", "password": "WrongPassword1"}))

    assert all(response.status_code == 401 for response in responses)
    assert len({response.text for response in responses}) == 1
    assert responses[0].json()["detail"] == {
        "code": "AUTHENTICATION_FAILED",
        "message": "邮箱或密码不正确。",
        "details": {},
    }
    assert "x-request-id" not in responses[-1].headers
    assert "retry-after" not in responses[-1].headers


def test_login_rate_limit_emits_only_rate_limited_evidence(auth_client, monkeypatch, capsys):
    client, _ = auth_client
    from test.paper_trading.api.test_auth_api import _FakeRedis

    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)
    capsys.readouterr()
    for _ in range(3):
        client.post("/auth/login", json={"email": "limited@example.com", "password": "WrongPassword1"})
    capsys.readouterr()
    client.post("/auth/login", json={"email": "limited@example.com", "password": "WrongPassword1"})

    evidence = [line for line in capsys.readouterr().out.splitlines() if '"path":"/auth/login"' in line]
    assert len(evidence) == 1
    assert '"code":"AUTH_RATE_LIMITED"' in evidence[0]


def test_invalid_session_returns_evidence_and_clears_cookies(auth_client):
    client, _ = auth_client
    client.cookies.set("paper_trading_session", "invalid")
    client.cookies.set("paper_trading_csrf", "csrf")

    response = client.get("/paper/accounts")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "SESSION_INVALID"
    assert uuid.UUID(response.headers["x-request-id"]).version == 4
    assert response.json()["detail"]["request_id"] == response.headers["x-request-id"]
    cookie_headers = response.headers.get_list("set-cookie")
    assert len(cookie_headers) == 2
    assert any("paper_trading_session=" in value for value in cookie_headers)
    assert any("paper_trading_csrf=" in value for value in cookie_headers)


def test_login_503_sources_have_matching_request_ids_and_preserve_cookies(auth_client, monkeypatch):
    client, factory = auth_client
    from test.paper_trading.api.test_auth_api import _verified_user

    _verified_user(factory)
    for patch_target in (
        "paper_trading.api.routers.auth._get_redis_client",
        "sqlalchemy.orm.session.Session.scalar",
        "paper_trading.api.routers.auth.verify_password",
    ):
        if patch_target.endswith("_get_redis_client"):
            monkeypatch.setattr(patch_target, lambda: (_ for _ in ()).throw(RuntimeError("down")))
        else:
            monkeypatch.setattr(patch_target, lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
        response = client.post("/auth/login", json={"email": "user@example.com", "password": "WrongPassword1"})
        assert response.status_code == 503
        assert response.headers["x-request-id"] == response.json()["detail"]["request_id"]
        assert uuid.UUID(response.headers["x-request-id"]).version == 4
        assert "set-cookie" not in response.headers
        monkeypatch.undo()
