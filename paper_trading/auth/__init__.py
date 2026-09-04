"""Authentication configuration contracts."""

import os
import re
from dataclasses import dataclass

_DEFAULT_JWT_SECRET = "local-development-secret"
_DEFAULT_JWT_TTL_SECONDS = 3600
_DEFAULT_SESSION_COOKIE_NAME = "paper_trading_session"
_DEFAULT_CSRF_COOKIE_NAME = "paper_trading_csrf"
_COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$")

__all__ = [
    "AuthSettings",
    "SessionClaims",
    "build_csrf_cookie",
    "build_session_cookie",
    "build_password_reset_url",
    "bump_session_version",
    "clear_auth_cookies",
    "create_session_token",
    "decode_session_token",
    "hash_auth_token",
    "hash_password",
    "new_auth_token",
    "normalize_email",
    "validate_email",
    "validate_auth_settings",
    "validate_password",
    "verify_password",
]


def _parse_bool(value: str, variable_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{variable_name} must be a boolean")


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    jwt_ttl_seconds: int
    cookie_secure: bool
    session_cookie_name: str
    csrf_cookie_name: str

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        ttl_value = os.getenv("PAPER_TRADING_JWT_TTL_SECONDS", str(_DEFAULT_JWT_TTL_SECONDS))
        try:
            jwt_ttl_seconds = int(ttl_value)
        except ValueError as exc:
            raise ValueError("PAPER_TRADING_JWT_TTL_SECONDS must be an integer") from exc

        secure_value = os.getenv("PAPER_TRADING_COOKIE_SECURE", "false")
        settings = cls(
            jwt_secret=os.getenv("PAPER_TRADING_JWT_SECRET", _DEFAULT_JWT_SECRET),
            jwt_ttl_seconds=jwt_ttl_seconds,
            cookie_secure=_parse_bool(secure_value, "PAPER_TRADING_COOKIE_SECURE"),
            session_cookie_name=os.getenv("PAPER_TRADING_SESSION_COOKIE_NAME", _DEFAULT_SESSION_COOKIE_NAME),
            csrf_cookie_name=os.getenv("PAPER_TRADING_CSRF_COOKIE_NAME", _DEFAULT_CSRF_COOKIE_NAME),
        )
        validate_auth_settings(settings)
        return settings


from .service import (  # noqa: E402
    SessionClaims,
    build_csrf_cookie,
    build_password_reset_url,
    build_session_cookie,
    bump_session_version,
    clear_auth_cookies,
    create_session_token,
    decode_session_token,
    hash_auth_token,
    hash_password,
    new_auth_token,
    normalize_email,
    validate_email,
    validate_password,
    verify_password,
)


def validate_auth_settings(settings: AuthSettings, environment: str | None = None) -> None:
    configured_environment = environment if environment is not None else os.getenv("FROG_ENV")
    if configured_environment is None:
        current_environment = "local"
    else:
        current_environment = configured_environment.strip().lower()
        if current_environment not in {"local", "test", "production"}:
            raise ValueError("FROG_ENV environment must be local, test, or production")
    if settings.jwt_ttl_seconds <= 0:
        raise ValueError("JWT TTL must be positive")
    for cookie_name, label in (
        (settings.session_cookie_name, "Session"),
        (settings.csrf_cookie_name, "CSRF"),
    ):
        if not cookie_name or not _COOKIE_NAME_RE.fullmatch(cookie_name):
            raise ValueError(f"{label} cookie name is invalid")
    if current_environment == "production":
        if not settings.jwt_secret.strip() or settings.jwt_secret.strip() == _DEFAULT_JWT_SECRET:
            raise ValueError("JWT secret is required in production")
        if not settings.cookie_secure:
            raise ValueError("secure cookies are required in production")
