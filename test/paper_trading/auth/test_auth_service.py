from datetime import datetime, timezone
from http.cookies import SimpleCookie

import pytest
from fastapi import Response
from jwt import decode, encode

from paper_trading.auth import (
    AuthSettings,
    build_csrf_cookie,
    build_password_reset_url,
    build_session_cookie,
    build_verification_url,
    bump_session_version,
    clear_auth_cookies,
    create_session_token,
    decode_session_token,
    hash_auth_token,
    hash_password,
    new_auth_token,
    normalize_email,
    validate_auth_settings,
    validate_password,
    verify_password,
)
from storage.model.auth import User


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    for variable_name in (
        "FROG_ENV",
        "PAPER_TRADING_JWT_SECRET",
        "PAPER_TRADING_JWT_TTL_SECONDS",
        "PAPER_TRADING_COOKIE_SECURE",
        "PAPER_TRADING_SESSION_COOKIE_NAME",
        "PAPER_TRADING_CSRF_COOKIE_NAME",
        "AUTH_PUBLIC_BASE_URL",
    ):
        monkeypatch.delenv(variable_name, raising=False)


def test_production_settings_require_jwt_secret(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "production")
    with pytest.raises(ValueError, match="JWT secret"):
        AuthSettings.from_environment()


def test_production_settings_fail_closed_when_environment_is_explicitly_empty(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "")

    with pytest.raises(ValueError, match="environment"):
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
    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://public.example.com/app")
    settings = AuthSettings(
        jwt_secret="production-secret",
        jwt_ttl_seconds=3600,
        cookie_secure=True,
        session_cookie_name="session",
        csrf_cookie_name="csrf",
    )

    validate_auth_settings(settings, environment="  PRODUCTION  ")


def test_explicit_empty_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("FROG_ENV", "production")
    settings = AuthSettings(
        jwt_secret="production-secret",
        jwt_ttl_seconds=3600,
        cookie_secure=False,
        session_cookie_name="session",
        csrf_cookie_name="csrf",
    )

    with pytest.raises(ValueError, match="environment"):
        validate_auth_settings(settings, environment="")


def test_valid_production_settings(monkeypatch):
    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://public.example.com/app")
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


def _settings() -> AuthSettings:
    return AuthSettings("test-secret-with-at-least-32-bytes-long", 3600, True, "session", "csrf")


def test_normalize_email_trims_and_lowercases():
    assert normalize_email("  User@Example.COM ") == "user@example.com"


@pytest.mark.parametrize("password", ["short1", "shortpassword", "123456789012"])
def test_validate_password_rejects_short_missing_letter_and_missing_number(password):
    with pytest.raises(ValueError, match="letter and a number"):
        validate_password(password)


def test_validate_password_rejects_unicode_digit():
    with pytest.raises(ValueError, match="letter and a number"):
        validate_password("abcdefghijkl١")


def test_hash_password_never_equals_plaintext_and_verifies():
    password = "correct-horse2"
    password_hash = hash_password(password)
    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("wrong-password2", password_hash)
    assert not verify_password(password, "not-an-argon2-hash")


def test_session_token_contains_user_and_session_version():
    token = create_session_token(42, 7, _settings())
    claims = decode(token, _settings().jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "42"
    assert claims["sv"] == 7


def test_decode_session_token_rejects_expired_and_wrong_version_claims():
    issued_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    token = create_session_token(42, 0, _settings(), issued_at)
    with pytest.raises(ValueError):
        decode_session_token(token, _settings(), datetime(2026, 1, 1, 1, tzinfo=timezone.utc))

    wrong_version = create_session_token(42, -1, _settings())
    with pytest.raises(ValueError):
        decode_session_token(wrong_version, _settings())


def test_decode_session_token_uses_injected_now_for_expiry():
    issued_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    token = create_session_token(42, 0, _settings(), issued_at)

    claims = decode_session_token(token, _settings(), datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc))
    assert claims.user_id == 42
    with pytest.raises(ValueError):
        decode_session_token(token, _settings(), datetime(2026, 1, 1, 2, tzinfo=timezone.utc))


def test_decode_session_token_rejects_future_iat():
    issued_at = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    token = create_session_token(42, 0, _settings(), issued_at)

    with pytest.raises(ValueError, match="Invalid session token"):
        decode_session_token(token, _settings(), datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_decode_session_token_rejects_expiration_at_or_before_iat():
    issued_timestamp = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    for expires_timestamp in (issued_timestamp, issued_timestamp - 1):
        token = encode(
            {"sub": "42", "sv": 0, "iat": issued_timestamp, "exp": expires_timestamp},
            _settings().jwt_secret,
            algorithm="HS256",
        )

        with pytest.raises(ValueError, match="Invalid session token"):
            decode_session_token(token, _settings(), datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    "claim, value",
    [
        ("sub", ""),
        ("sub", "42.0"),
        ("sub", 42),
        ("sv", True),
        ("sv", "0"),
        ("iat", False),
        ("iat", 1.5),
        ("exp", "2"),
        ("exp", 2.5),
    ],
)
def test_decode_session_token_rejects_invalid_claim_types(claim, value):
    issued_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payload = {"sub": "42", "sv": 0, "iat": int(issued_at.timestamp()), "exp": int((issued_at.timestamp() + 3600))}
    payload[claim] = value
    token = encode(payload, _settings().jwt_secret, algorithm="HS256")

    with pytest.raises(ValueError, match="Invalid session token"):
        decode_session_token(token, _settings(), issued_at)


def test_session_version_bump_invalidates_old_token_at_calling_boundary():
    user = User(session_version=1)
    token = create_session_token(42, user.session_version, _settings())
    assert decode_session_token(token, _settings()).session_version == user.session_version

    assert bump_session_version(user) == 2
    claims = decode_session_token(token, _settings())
    assert claims.session_version != user.session_version


def test_new_auth_token_returns_only_hash_for_storage():
    raw_token, token_hash = new_auth_token()
    assert raw_token
    assert token_hash == hash_auth_token(raw_token)
    assert raw_token != token_hash


@pytest.mark.parametrize(
    "url_builder, route",
    [
        (build_password_reset_url, "/reset-password"),
        (build_verification_url, "/verify-email"),
    ],
)
def test_auth_urls_require_an_explicit_valid_https_public_base_url(url_builder, route):
    with pytest.raises(ValueError, match="AUTH_PUBLIC_BASE_URL"):
        url_builder("raw-token")

    assert (
        url_builder("raw-token", "https://public.example.com/app/")
        == f"https://public.example.com/app{route}?token=raw-token"
    )


@pytest.mark.parametrize("url_builder", [build_password_reset_url, build_verification_url])
@pytest.mark.parametrize(
    "base_url",
    ["http://public.example.com/app", "https:///app", "https://user@/app"],
)
def test_auth_urls_reject_invalid_public_base_urls_without_leaking_configuration(url_builder, base_url):
    with pytest.raises(ValueError, match="AUTH_PUBLIC_BASE_URL") as error:
        url_builder("raw-token", base_url)

    assert base_url not in str(error.value)


@pytest.mark.parametrize(
    "url_builder, route",
    [
        (build_password_reset_url, "/reset-password"),
        (build_verification_url, "/verify-email"),
    ],
)
def test_auth_urls_preserve_path_prefix_and_quote_tokens(monkeypatch, url_builder, route):
    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://public.example.com/app/")

    assert url_builder("raw token?+/") == f"https://public.example.com/app{route}?token=raw%20token%3F%2B%2F"


def test_session_and_csrf_cookies_have_expected_attributes():
    response = Response()
    build_session_cookie(response, "token", _settings())
    build_csrf_cookie(response, "csrf-token", _settings())
    cookies = [
        SimpleCookie(value.decode())[name]
        for header_name, value in response.raw_headers
        if header_name == b"set-cookie"
        for name in ("session", "csrf")
        if name in value.decode()
    ]
    session_cookie, csrf_cookie = cookies
    assert session_cookie.key == "session"
    assert session_cookie.value == "token"
    assert session_cookie["path"] == "/"
    assert session_cookie["max-age"] == "3600"
    assert session_cookie["httponly"]
    assert session_cookie["samesite"] == "lax"
    assert session_cookie["secure"]
    assert csrf_cookie.key == "csrf"
    assert csrf_cookie.value == "csrf-token"
    assert csrf_cookie["path"] == "/"
    assert csrf_cookie["max-age"] == "3600"
    assert csrf_cookie["httponly"] == ""
    assert csrf_cookie["samesite"] == "lax"
    assert csrf_cookie["secure"]


def test_clear_auth_cookies_expires_session_and_csrf_cookies():
    response = Response()
    build_session_cookie(response, "token", _settings())
    build_csrf_cookie(response, "csrf-token", _settings())
    clear_auth_cookies(response, _settings())
    cleared = [
        SimpleCookie(value.decode())[name]
        for header_name, value in response.raw_headers
        if header_name == b"set-cookie"
        for name in ("session", "csrf")
        if "Max-Age=0" in value.decode() and name in value.decode()
    ]
    assert {cookie.key for cookie in cleared} == {"session", "csrf"}
    assert all(cookie["path"] == "/" for cookie in cleared)
    assert all(cookie["max-age"] == "0" for cookie in cleared)
