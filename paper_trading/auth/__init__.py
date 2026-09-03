"""Authentication configuration contracts."""

import os
from dataclasses import dataclass

_DEFAULT_JWT_SECRET = "local-development-secret"
_DEFAULT_JWT_TTL_SECONDS = 3600
_DEFAULT_SESSION_COOKIE_NAME = "paper_trading_session"
_DEFAULT_CSRF_COOKIE_NAME = "paper_trading_csrf"


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
            session_cookie_name=os.getenv(
                "PAPER_TRADING_SESSION_COOKIE_NAME", _DEFAULT_SESSION_COOKIE_NAME
            ),
            csrf_cookie_name=os.getenv("PAPER_TRADING_CSRF_COOKIE_NAME", _DEFAULT_CSRF_COOKIE_NAME),
        )
        validate_auth_settings(settings)
        return settings


def validate_auth_settings(settings: AuthSettings, environment: str | None = None) -> None:
    current_environment = environment or os.getenv("FROG_ENV", "local")
    if settings.jwt_ttl_seconds <= 0:
        raise ValueError("JWT TTL must be positive")
    if not settings.session_cookie_name:
        raise ValueError("Session cookie name must not be empty")
    if not settings.csrf_cookie_name:
        raise ValueError("CSRF cookie name must not be empty")
    if current_environment.lower() == "production":
        if not settings.jwt_secret or settings.jwt_secret == _DEFAULT_JWT_SECRET:
            raise ValueError("JWT secret is required in production")
        if not settings.cookie_secure:
            raise ValueError("secure cookies are required in production")
