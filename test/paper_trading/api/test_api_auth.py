import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.auth import AuthSettings
from storage.model.base import Base
from storage.storage_db import StorageDb


def test_api_requires_bearer_token(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    unauthorized = client.get("/paper/accounts")
    authorized = client.get("/paper/accounts", headers={"Authorization": "Bearer secret"})

    assert unauthorized.status_code == 401
    assert authorized.status_code != 401
    session.close()
    engine.dispose()


@pytest.mark.parametrize("environment", ["", "staging"])
def test_app_startup_rejects_invalid_auth_environment(monkeypatch, environment):
    monkeypatch.setenv("FROG_ENV", environment)

    with pytest.raises(ValueError, match="environment"):
        with TestClient(create_app()):
            pass


def test_app_startup_rejects_invalid_production_auth_configuration(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "production")
    monkeypatch.delenv("PAPER_TRADING_JWT_SECRET", raising=False)
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")

    with pytest.raises(ValueError, match="JWT secret"):
        with TestClient(create_app()):
            pass


@pytest.mark.parametrize("base_url", [None, "http://public.example.com/app", "https:///app"])
def test_app_startup_rejects_invalid_production_public_base_url(monkeypatch, base_url):
    monkeypatch.setenv("FROG_ENV", "production")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "production-secret")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")
    if base_url is None:
        monkeypatch.delenv("AUTH_PUBLIC_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", base_url)
    monkeypatch.setattr("paper_trading.api.app.get_storage", pytest.fail)

    with pytest.raises(ValueError, match="AUTH_PUBLIC_BASE_URL") as error:
        with TestClient(create_app()):
            pass

    if base_url is not None:
        assert base_url not in str(error.value)


def test_app_startup_accepts_normalized_production_environment(monkeypatch):
    monkeypatch.setenv("FROG_ENV", " PRODUCTION ")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "production-secret")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://public.example.com/app")
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)

    with TestClient(create_app()):
        pass


@pytest.mark.parametrize("environment", ["local", "test"])
def test_app_startup_accepts_local_and_test_auth_defaults(monkeypatch, environment):
    monkeypatch.setenv("FROG_ENV", environment)
    monkeypatch.delenv("PAPER_TRADING_JWT_SECRET", raising=False)
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)

    with TestClient(create_app()):
        assert AuthSettings.from_environment().jwt_secret == "local-development-secret"


def test_app_lifespan_backfills_legacy_owner_once_across_repeated_startups(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    storage = object.__new__(StorageDb)
    storage.engine = engine
    monkeypatch.setenv("AUTH_OWNER_EMAIL", "owner@example.com")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, email_verified_at TEXT)"))
        connection.execute(text("CREATE TABLE paper_accounts (id INTEGER PRIMARY KEY, owner_user_id INTEGER)"))
        connection.execute(
            text("INSERT INTO users (id, email, email_verified_at) VALUES (1, 'owner@example.com', '2026-01-01')")
        )
        connection.execute(text("INSERT INTO paper_accounts (id, owner_user_id) VALUES (1, NULL)"))

    storage_starts: list[None] = []

    def start_storage():
        storage_starts.append(None)
        storage._backfill_paper_account_ownership()
        return storage

    monkeypatch.setattr("paper_trading.api.app.get_storage", start_storage)
    try:
        with TestClient(create_app()):
            pass
        with TestClient(create_app()):
            pass

        with engine.connect() as connection:
            assert connection.execute(text("SELECT owner_user_id FROM paper_accounts")).scalar_one() == 1
        assert storage_starts == [None, None]
    finally:
        engine.dispose()
