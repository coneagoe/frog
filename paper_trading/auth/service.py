"""Pure authentication primitives for browser sessions."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Response

from paper_trading.auth import AuthSettings
from storage.model.auth import User

_JWT_ALGORITHM = "HS256"
_USER_ID_RE = re.compile(r"^[0-9]+$")
_PASSWORD_LETTER_RE = re.compile(r"[A-Za-z]")
_password_hasher = PasswordHasher()


@dataclass(frozen=True)
class SessionClaims:
    user_id: int
    session_version: int
    issued_at: datetime
    expires_at: datetime


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < 12 or not _PASSWORD_LETTER_RE.search(password):
        raise ValueError("Password must be at least 12 characters and contain a letter and a number")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must be at least 12 characters and contain a letter and a number")


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_session_token(
    user_id: int,
    session_version: int,
    settings: AuthSettings,
    now: datetime | None = None,
) -> str:
    issued_at = _as_utc(now or datetime.now(timezone.utc))
    expires_at = issued_at + timedelta(seconds=settings.jwt_ttl_seconds)
    claims = {
        "sub": str(user_id),
        "sv": session_version,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_session_token(
    token: str,
    settings: AuthSettings,
    now: datetime | None = None,
) -> SessionClaims:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_JWT_ALGORITHM],
            options={
                "require": ["sub", "sv", "iat", "exp"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
        subject = payload["sub"]
        session_version = payload["sv"]
        issued_timestamp = payload["iat"]
        expires_timestamp = payload["exp"]
        if (
            not isinstance(subject, str)
            or not _USER_ID_RE.fullmatch(subject)
            or not _is_integer(session_version)
            or not _is_integer(issued_timestamp)
            or not _is_integer(expires_timestamp)
        ):
            raise ValueError("Invalid session token")
        user_id = int(subject)
        issued_at = datetime.fromtimestamp(issued_timestamp, tz=timezone.utc)
        expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError, KeyError, jwt.InvalidTokenError) as exc:
        raise ValueError("Invalid session token") from exc

    current_time = _as_utc(now or datetime.now(timezone.utc))
    if expires_at <= current_time or session_version < 0 or user_id <= 0:
        raise ValueError("Invalid session token")
    return SessionClaims(user_id, session_version, issued_at, expires_at)


def new_auth_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_auth_token(raw_token)


def hash_auth_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def bump_session_version(user: User) -> int:
    user.session_version += 1
    return user.session_version


def build_session_cookie(response: Response, token: str, settings: AuthSettings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.jwt_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def build_csrf_cookie(response: Response, csrf_token: str, settings: AuthSettings) -> None:
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=settings.jwt_ttl_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
