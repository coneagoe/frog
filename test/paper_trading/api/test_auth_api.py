from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import cast
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.auth import AuthSettings, create_session_token, hash_auth_token, hash_password
from storage.model.auth import AuthToken, User
from storage.model.base import Base


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl


class _RecordingSMTP:
    instances: list["_RecordingSMTP"] = []

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.login_calls: list[tuple[str, str]] = []
        self.messages: list[EmailMessage] = []
        self.closed = False
        self.raise_on_send = False
        _RecordingSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def login(self, username: str, password: str) -> None:
        self.login_calls.append((username, password))

    def send_message(self, message) -> None:
        if self.raise_on_send:
            raise RuntimeError("smtp failed")
        self.messages.append(message)

    def quit(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def clear_password_reset_environment(monkeypatch):
    for variable_name in (
        "AUTH_PUBLIC_BASE_URL",
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_SENDER",
        "MAIL_PASSWORD",
        "MAIL_RECEIVERS",
    ):
        monkeypatch.delenv(variable_name, raising=False)


@pytest.fixture
def auth_client(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "api-secret")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def _register(client: TestClient, email="User@Example.com", password="StrongPassword1"):
    return client.post("/auth/register", json={"email": email, "password": password})


def _verified_user(factory, email="user@example.com", password="StrongPassword1") -> User:
    with factory() as session:
        user = User(email=email, password_hash=hash_password(password), email_verified_at=datetime.now(timezone.utc))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _login(client: TestClient, email="user@example.com", password="StrongPassword1"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _set_password_reset_env(monkeypatch):
    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://public.example.com/app")
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_PORT", "465")
    monkeypatch.setenv("MAIL_SENDER", "sender@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "smtp-password")
    monkeypatch.setenv("MAIL_RECEIVERS", "ops@example.com")


def _extract_reset_link(message: EmailMessage) -> str:
    content = cast(str, message.get_content())
    for line in content.splitlines():
        if line.startswith("https://"):
            return line
    raise AssertionError("reset link not found")


def test_register_normalizes_email_and_stores_only_argon2_hash(auth_client):
    client, factory = auth_client
    response = _register(client, " User@Example.COM ")
    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"
    assert response.json()["email_verified_at"] is None
    with factory() as session:
        user = session.scalar(select(User))
        assert user is not None
        assert user.password_hash.startswith("$argon2")
        assert "StrongPassword1" not in user.password_hash


def test_register_rejects_weak_password(auth_client):
    response = _register(auth_client[0], password="weak")
    assert response.status_code == 422


@pytest.mark.parametrize("email", ["", "@example.com", "user@", "user@example", "a@b@c.com"])
def test_register_rejects_invalid_email_without_creating_user(auth_client, email):
    client, factory = auth_client
    response = _register(client, email=email)
    assert response.status_code == 422
    with factory() as session:
        assert session.scalar(select(User)) is None


def test_login_rejects_invalid_email_with_client_validation_response(auth_client, monkeypatch):
    client, _ = auth_client
    calls = []

    def verify(password, password_hash):
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr("paper_trading.api.routers.auth.verify_password", verify)
    response = _login(client, email="missing@example")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "email"
    assert calls == []


def test_register_rejects_duplicate_normalized_email_with_409(auth_client):
    client, _ = auth_client
    assert _register(client).status_code == 201
    assert _register(client, " USER@example.COM ").status_code == 409


def test_register_does_not_map_non_email_integrity_error_to_409(auth_client, monkeypatch):
    client, _ = auth_client
    monkeypatch.setattr("paper_trading.api.routers.auth.hash_password", lambda _: None)
    with pytest.raises(IntegrityError):
        client.post("/auth/register", json={"email": "integrity@example.com", "password": "StrongPassword1"})


def test_login_requires_verified_user_but_uses_generic_401(auth_client):
    client, factory = auth_client
    assert _register(client).status_code == 201
    assert _login(client).status_code == 401
    _verified_user(factory, "verified@example.com")
    unknown = _login(client, "missing@example.com")
    incorrect = _login(client, password="WrongPass1")
    assert unknown.status_code == incorrect.status_code == 401
    assert unknown.json() == incorrect.json()


def test_login_unknown_user_runs_password_verification_path(auth_client, monkeypatch):
    client, _ = auth_client
    calls = []

    def verify(password, password_hash):
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr("paper_trading.api.routers.auth.verify_password", verify)
    response = _login(client, "missing@example.com")
    assert response.status_code == 401
    assert calls and calls[0][1].startswith("$argon2id$")


def test_login_empty_password_uses_dummy_verification_and_returns_generic_401(auth_client, monkeypatch):
    client, _ = auth_client
    calls = []

    def verify(password, password_hash):
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr("paper_trading.api.routers.auth.verify_password", verify)
    response = client.post("/auth/login", json={"email": "missing@example.com", "password": ""})
    assert response.status_code == 401
    assert calls and calls[0][0] == "" and calls[0][1].startswith("$argon2id$")


def test_login_existing_user_empty_password_uses_dummy_hash(auth_client, monkeypatch):
    client, factory = auth_client
    user = _verified_user(factory)
    calls = []

    def verify(password, password_hash):
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr("paper_trading.api.routers.auth.verify_password", verify)
    response = client.post("/auth/login", json={"email": user.email, "password": ""})
    assert response.status_code == 401
    assert calls == [("", calls[0][1])]
    assert calls[0][1].startswith("$argon2id$")
    assert calls[0][1] != user.password_hash


def test_login_sets_http_only_lax_session_and_readable_csrf_cookie(auth_client):
    client, factory = auth_client
    _verified_user(factory)
    response = _login(client)
    assert response.status_code == 200
    session_cookie = response.cookies.get("paper_trading_session")
    csrf_cookie = response.cookies.get("paper_trading_csrf")
    assert session_cookie and csrf_cookie
    set_cookie = response.headers.get_list("set-cookie")
    assert any(
        "paper_trading_session=" in value and "HttpOnly" in value and "SameSite=lax" in value for value in set_cookie
    )
    assert any(
        "paper_trading_csrf=" in value and "HttpOnly" not in value and "SameSite=lax" in value for value in set_cookie
    )
    assert all("Path=/" in value and "Max-Age=3600" in value and "Secure" not in value for value in set_cookie)


def test_me_returns_safe_identity_for_valid_session(auth_client):
    client, factory = auth_client
    _verified_user(factory)
    _login(client)
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert set(response.json()) == {"id", "email", "email_verified_at"}


def test_me_returns_401_for_missing_malformed_expired_and_stale_version_sessions(auth_client):
    client, factory = auth_client
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("paper_trading_session", "malformed")
    assert client.get("/auth/me").status_code == 401
    user = _verified_user(factory)
    settings = AuthSettings.from_environment()
    expired = jwt.encode({"sub": str(user.id), "sv": 1, "iat": 1, "exp": 2}, settings.jwt_secret, algorithm="HS256")
    client.cookies.set("paper_trading_session", expired)
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("paper_trading_session", create_session_token(user.id, 2, settings))
    assert client.get("/auth/me").status_code == 401


def test_logout_bumps_session_version_and_clears_cookies(auth_client):
    client, factory = auth_client
    user = _verified_user(factory)
    _login(client)
    csrf = client.cookies.get("paper_trading_csrf")
    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    with factory() as session:
        assert session.get(User, user.id).session_version == 2
    assert client.get("/auth/me").status_code == 401
    assert any(
        "paper_trading_session=" in value and "Max-Age=0" in value for value in response.headers.get_list("set-cookie")
    )
    assert any(
        "paper_trading_csrf=" in value and "Max-Age=0" in value for value in response.headers.get_list("set-cookie")
    )
    assert all("Path=/" in value and "Secure" not in value for value in response.headers.get_list("set-cookie"))


def test_cookie_authenticated_mutation_requires_matching_csrf(auth_client):
    client, factory = auth_client
    _verified_user(factory)
    _login(client)
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_static_bearer_token_remains_compatible_and_csrf_exempt(auth_client):
    client, _ = auth_client
    headers = {"Authorization": "Bearer api-secret"}
    response = client.post(
        "/paper/accounts",
        json={"name": "bearer-account", "initial_cash": "1000"},
        headers=headers,
    )
    assert response.status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 401


def test_forgot_password_returns_same_response_for_known_and_unknown_emails(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    _verified_user(factory, email="known@example.com")
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)
    smtp = _RecordingSMTP
    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", smtp)

    known = client.post("/auth/forgot-password", json={"email": "known@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert known.json()["message"] == "If the email exists, password reset instructions have been sent."
    assert redis_client.counts
    assert any(key.endswith(":ip:testclient") for key in redis_client.counts)
    assert any(key.endswith(":email:known@example.com") for key in redis_client.counts)
    assert any(key.endswith(":email:missing@example.com") for key in redis_client.counts)
    assert _RecordingSMTP.instances and _RecordingSMTP.instances[-1].messages


def test_forgot_password_normalizes_email_for_rate_limiting(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    _verified_user(factory, email="rate@example.com")
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)
    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", _RecordingSMTP)

    first = client.post("/auth/forgot-password", json={"email": "Rate@Example.com"})
    second = client.post("/auth/forgot-password", json={"email": " rate@example.com "})
    third = client.post("/auth/forgot-password", json={"email": "RATE@example.com"})
    fourth = client.post("/auth/forgot-password", json={"email": "rate@example.com"})

    assert first.status_code == second.status_code == third.status_code == 202
    assert fourth.status_code == 429
    assert redis_client.counts["paper_trading:auth:password_reset:email:rate@example.com"] == 4


def test_forgot_password_rate_limits_by_ip_across_email_addresses(auth_client, monkeypatch):
    client, _ = auth_client
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)

    responses = [
        client.post("/auth/forgot-password", json={"email": f"person{index}@example.com"}) for index in range(4)
    ]

    assert [response.status_code for response in responses] == [202, 202, 202, 429]
    assert redis_client.counts["paper_trading:auth:password_reset:ip:testclient"] == 4


def test_forgot_password_fails_closed_when_redis_is_unavailable(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    user = _verified_user(factory, email="redis@example.com")
    monkeypatch.setattr(
        "paper_trading.api.routers.auth._get_redis_client", lambda: (_ for _ in ()).throw(RuntimeError("redis down"))
    )
    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", pytest.fail)

    response = client.post("/auth/forgot-password", json={"email": user.email})

    assert response.status_code == 202
    assert response.json()["message"] == "If the email exists, password reset instructions have been sent."
    with factory() as session:
        assert session.query(User).filter(User.email == user.email).count() == 1
        assert session.query(AuthToken).count() == 0


def test_forgot_password_fails_closed_when_smtp_send_fails(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    user = _verified_user(factory, email="smtp@example.com")
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)

    class FailingSMTP(_RecordingSMTP):
        def send_message(self, message) -> None:
            raise RuntimeError("smtp provider failed")

    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", FailingSMTP)

    response = client.post("/auth/forgot-password", json={"email": user.email})

    assert response.status_code == 202
    assert response.json()["message"] == "If the email exists, password reset instructions have been sent."
    with factory() as session:
        assert session.query(AuthToken).count() == 0


def test_reset_password_consumes_single_use_token_and_increments_session_version(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    user = _verified_user(factory, email="reset@example.com")
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)
    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", _RecordingSMTP)

    forgot_response = client.post("/auth/forgot-password", json={"email": user.email})
    assert forgot_response.status_code == 202
    reset_link = _extract_reset_link(_RecordingSMTP.instances[-1].messages[-1])
    raw_token = parse_qs(urlparse(reset_link).query)["token"][0]

    reset_response = client.post("/auth/reset-password", json={"token": raw_token, "password": "NewPassword123"})
    assert reset_response.status_code == 200
    assert reset_response.json()["message"] == "Password has been reset."

    with factory() as session:
        refreshed = session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.session_version == user.session_version + 1
        assert refreshed.password_hash != user.password_hash
        assert refreshed.password_hash.startswith("$argon2")
        token_row = session.query(AuthToken).one()
        assert token_row.used_at is not None
        assert token_row.token_hash == hash_auth_token(raw_token)
        assert token_row.token_hash != raw_token

    assert (
        client.post("/auth/reset-password", json={"token": raw_token, "password": "NewPassword123"}).status_code == 400
    )


def test_reset_password_rejects_invalid_token_without_changing_user(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    user = _verified_user(factory, email="invalid-token@example.com")

    response = client.post("/auth/reset-password", json={"token": "not-a-token", "password": "NewPassword123"})

    assert response.status_code == 400
    with factory() as session:
        refreshed = session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.session_version == user.session_version
        assert refreshed.password_hash == user.password_hash


def test_reset_password_rejects_expired_token_without_changing_user(auth_client, monkeypatch):
    client, factory = auth_client
    _set_password_reset_env(monkeypatch)
    user = _verified_user(factory, email="expired-token@example.com")
    redis_client = _FakeRedis()
    monkeypatch.setattr("paper_trading.api.routers.auth._get_redis_client", lambda: redis_client)
    monkeypatch.setattr("paper_trading.api.routers.auth.smtplib.SMTP_SSL", _RecordingSMTP)
    assert client.post("/auth/forgot-password", json={"email": user.email}).status_code == 202
    raw_token = parse_qs(urlparse(_extract_reset_link(_RecordingSMTP.instances[-1].messages[-1])).query)["token"][0]
    with factory() as session:
        token_row = session.query(AuthToken).one()
        token_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    response = client.post("/auth/reset-password", json={"token": raw_token, "password": "NewPassword123"})

    assert response.status_code == 400
    with factory() as session:
        refreshed = session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.session_version == user.session_version
        assert refreshed.password_hash == user.password_hash
