import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.auth import AuthSettings
from storage.model.base import Base


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


def test_app_startup_accepts_normalized_production_environment(monkeypatch):
    monkeypatch.setenv("FROG_ENV", " PRODUCTION ")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "production-secret")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")
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
