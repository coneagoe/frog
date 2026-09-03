import pytest

from paper_trading.auth import AuthSettings, validate_auth_settings


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    for variable_name in (
        "FROG_ENV",
        "PAPER_TRADING_JWT_SECRET",
        "PAPER_TRADING_JWT_TTL_SECONDS",
        "PAPER_TRADING_COOKIE_SECURE",
        "PAPER_TRADING_SESSION_COOKIE_NAME",
        "PAPER_TRADING_CSRF_COOKIE_NAME",
    ):
        monkeypatch.delenv(variable_name, raising=False)


def test_production_settings_require_jwt_secret(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "production")
    with pytest.raises(ValueError, match="JWT secret"):
        AuthSettings.from_environment()


def test_production_settings_reject_insecure_cookie(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-secret")
    monkeypatch.setenv("FROG_ENV", "production")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="secure"):
        AuthSettings.from_environment()


def test_defaults_are_loaded_from_environment():
    settings = AuthSettings.from_environment()

    assert settings.jwt_secret == "local-development-secret"
    assert settings.jwt_ttl_seconds == 3600
    assert settings.cookie_secure is False
    assert settings.session_cookie_name == "paper_trading_session"
    assert settings.csrf_cookie_name == "paper_trading_csrf"


def test_custom_settings_are_loaded(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "custom-secret")
    monkeypatch.setenv("PAPER_TRADING_JWT_TTL_SECONDS", "7200")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", " YES ")
    monkeypatch.setenv("PAPER_TRADING_SESSION_COOKIE_NAME", "custom_session")
    monkeypatch.setenv("PAPER_TRADING_CSRF_COOKIE_NAME", "custom_csrf")

    settings = AuthSettings.from_environment()

    assert settings.jwt_secret == "custom-secret"
    assert settings.jwt_ttl_seconds == 7200
    assert settings.cookie_secure is True
    assert settings.session_cookie_name == "custom_session"
    assert settings.csrf_cookie_name == "custom_csrf"


@pytest.mark.parametrize("ttl", ["not-an-integer", "0", "-1"])
def test_invalid_ttl_is_rejected(monkeypatch, ttl):
    monkeypatch.setenv("PAPER_TRADING_JWT_TTL_SECONDS", ttl)

    with pytest.raises(ValueError):
        AuthSettings.from_environment()


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "0", "false", "No", "off"])
def test_valid_boolean_values_are_parsed(monkeypatch, value):
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", value)

    settings = AuthSettings.from_environment()

    assert settings.cookie_secure is (value.strip().lower() in {"1", "true", "yes", "on"})


def test_invalid_boolean_is_rejected(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "maybe")

    with pytest.raises(ValueError, match="boolean"):
        AuthSettings.from_environment()


def test_cookie_names_can_be_overridden(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_SESSION_COOKIE_NAME", "session_override")
    monkeypatch.setenv("PAPER_TRADING_CSRF_COOKIE_NAME", "csrf_override")

    settings = AuthSettings.from_environment()

    assert settings.session_cookie_name == "session_override"
    assert settings.csrf_cookie_name == "csrf_override"


def test_explicit_environment_is_used_and_trimmed(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "local")
    settings = AuthSettings(
        jwt_secret="production-secret",
        jwt_ttl_seconds=3600,
        cookie_secure=True,
        session_cookie_name="session",
        csrf_cookie_name="csrf",
    )

    validate_auth_settings(settings, environment="  PRODUCTION  ")


def test_explicit_empty_environment_is_not_replaced(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "production")
    settings = AuthSettings(
        jwt_secret="production-secret",
        jwt_ttl_seconds=3600,
        cookie_secure=False,
        session_cookie_name="session",
        csrf_cookie_name="csrf",
    )

    validate_auth_settings(settings, environment="")


def test_valid_production_settings():
    settings = AuthSettings(
        jwt_secret="production-secret",
        jwt_ttl_seconds=900,
        cookie_secure=True,
        session_cookie_name="session",
        csrf_cookie_name="csrf",
    )

    validate_auth_settings(settings, environment="production")


def test_blank_production_secret_is_rejected_without_leaking_secret(monkeypatch):
    secret = "   "
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", secret)
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")
    monkeypatch.setenv("FROG_ENV", " production ")

    with pytest.raises(ValueError, match="JWT secret") as error:
        AuthSettings.from_environment()

    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "secret",
    [" local-development-secret", "local-development-secret ", "\tlocal-development-secret\n"],
)
def test_default_production_secret_variants_are_rejected(monkeypatch, secret):
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", secret)
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "true")
    monkeypatch.setenv("FROG_ENV", "production")

    with pytest.raises(ValueError, match="JWT secret"):
        AuthSettings.from_environment()


@pytest.mark.parametrize(
    "variable_name",
    ["PAPER_TRADING_SESSION_COOKIE_NAME", "PAPER_TRADING_CSRF_COOKIE_NAME"],
)
@pytest.mark.parametrize(
    "cookie_name",
    ["", "   ", "bad name", "bad;name", "bad\\name", "中文", "café", "bad:name", "bad/name"],
)
def test_invalid_cookie_names_are_rejected(monkeypatch, variable_name, cookie_name):
    monkeypatch.setenv(variable_name, cookie_name)

    with pytest.raises(ValueError, match="cookie name"):
        AuthSettings.from_environment()
