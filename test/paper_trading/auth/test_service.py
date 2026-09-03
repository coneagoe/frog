import pytest

from paper_trading.auth import AuthSettings


def test_production_settings_require_jwt_secret(monkeypatch):
    monkeypatch.delenv("PAPER_TRADING_JWT_SECRET", raising=False)
    monkeypatch.setenv("FROG_ENV", "production")
    with pytest.raises(ValueError, match="JWT secret"):
        AuthSettings.from_environment()


def test_production_settings_reject_insecure_cookie(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-secret")
    monkeypatch.setenv("FROG_ENV", "production")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="secure"):
        AuthSettings.from_environment()
