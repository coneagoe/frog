import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_trading.api.auth_evidence import (
    AuthEvidenceCode,
    error_detail,
    render_evidence,
    request_id_from_request,
)
from paper_trading.api.deps import get_session, require_browser_user, require_csrf
from paper_trading.auth import (
    AuthSettings,
    build_csrf_cookie,
    build_password_reset_url,
    build_session_cookie,
    build_verification_url,
    clear_auth_cookies,
    create_session_token,
    hash_auth_token,
    hash_password,
    new_auth_token,
    normalize_email,
    validate_email,
    validate_password,
    verify_password,
)
from storage.model.auth import AuthToken, User

_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$NGJ2+MUUColXDcqLKM6NHw$VmCfSMah6ivG0JZGbbYZXPdKVCu4ZbZI+Ye9FoFzh+M"
)
_PASSWORD_RESET_PURPOSE = "password_reset"
_PASSWORD_RESET_TTL_SECONDS = 900
_PASSWORD_RESET_EMAIL_RATE_LIMIT = 3
_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600
_PASSWORD_RESET_RESPONSE = {"message": "If the email exists, password reset instructions have been sent."}
_EMAIL_VERIFICATION_PURPOSE = "email_verification"
_EMAIL_VERIFICATION_TTL_SECONDS = 900
_EMAIL_VERIFICATION_EMAIL_RATE_LIMIT = 3
_EMAIL_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS = 3600
_REGISTRATION_RATE_LIMIT_KEY_PREFIX = "paper_trading:auth:registration"
_VERIFICATION_EMAIL_RATE_LIMIT_KEY_PREFIX = "paper_trading:auth:verification_email"
_LOGIN_RATE_LIMIT_KEY_PREFIX = "paper_trading:auth:login"
_LOGIN_RATE_LIMIT = 3
_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 3600
_EMAIL_VERIFICATION_RESPONSE = {"message": "If the email exists, verification instructions have been sent."}

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        try:
            return validate_email(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class RegistrationCredentials(Credentials):
    password: str = Field(min_length=1)


class Identity(BaseModel):
    id: int
    email: str
    email_verified_at: datetime | None


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        try:
            return validate_email(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ResendVerificationRequest(ForgotPasswordRequest):
    pass


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=1)


def _identity(user: User) -> Identity:
    return Identity(id=user.id, email=user.email, email_verified_at=user.email_verified_at)


def _generic_unauthorized(code: AuthEvidenceCode = AuthEvidenceCode.AUTH_INVALID_CREDENTIALS) -> HTTPException:
    print(render_evidence(code, "/auth/login"))
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=error_detail(AuthEvidenceCode.AUTHENTICATION_FAILED, "邮箱或密码不正确。"),
    )


def _get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


def _password_reset_rate_limit(redis_client: redis.Redis, ip_address: str, email: str) -> bool:
    return _rate_limit(
        redis_client,
        ip_address,
        email,
        key_prefix="paper_trading:auth:password_reset",
        window_seconds=_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS,
        limit=_PASSWORD_RESET_EMAIL_RATE_LIMIT,
    )


def _rate_limit(
    redis_client: redis.Redis,
    ip_address: str,
    email: str,
    *,
    key_prefix: str,
    window_seconds: int,
    limit: int,
) -> bool:
    keys = (
        f"{key_prefix}:ip:{ip_address}",
        f"{key_prefix}:email:{email}",
    )
    pipeline = redis_client.pipeline(transaction=True)
    for key in keys:
        pipeline.incr(key)
        pipeline.expire(key, window_seconds, nx=True)
    results = pipeline.execute()
    counts = [int(results[index]) for index in range(0, len(results), 2)]
    return max(counts) <= limit


def _registration_rate_limit(redis_client: redis.Redis, ip_address: str, email: str) -> bool:
    return _rate_limit(
        redis_client,
        ip_address,
        email,
        key_prefix=_REGISTRATION_RATE_LIMIT_KEY_PREFIX,
        window_seconds=_EMAIL_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS,
        limit=_EMAIL_VERIFICATION_EMAIL_RATE_LIMIT,
    )


def _verification_email_rate_limit(redis_client: redis.Redis, ip_address: str, email: str) -> bool:
    return _rate_limit(
        redis_client,
        ip_address,
        email,
        key_prefix=_VERIFICATION_EMAIL_RATE_LIMIT_KEY_PREFIX,
        window_seconds=_EMAIL_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS,
        limit=_EMAIL_VERIFICATION_EMAIL_RATE_LIMIT,
    )


def _login_rate_limit(redis_client: redis.Redis, ip_address: str, email: str) -> bool:
    return _rate_limit(
        redis_client,
        ip_address,
        email,
        key_prefix=_LOGIN_RATE_LIMIT_KEY_PREFIX,
        window_seconds=_LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        limit=_LOGIN_RATE_LIMIT,
    )


def _send_password_reset_email(raw_token: str, email: str) -> None:
    reset_url = build_password_reset_url(raw_token)
    message = EmailMessage()
    message["Subject"] = "Password reset"
    message["From"] = os.environ["MAIL_SENDER"]
    message["To"] = email
    message.set_content(f"Use this link to reset your password:\n{reset_url}\n")
    with smtplib.SMTP_SSL(os.environ["MAIL_SERVER"], int(os.environ["MAIL_PORT"])) as smtp:
        smtp.login(os.environ["MAIL_SENDER"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)


def _send_verification_email(raw_token: str, email: str) -> None:
    verification_url = build_verification_url(raw_token)
    message = EmailMessage()
    message["Subject"] = "Verify your email"
    message["From"] = os.environ["MAIL_SENDER"]
    message["To"] = email
    message.set_content(f"Use this link to verify your email:\n{verification_url}\n")
    with smtplib.SMTP_SSL(os.environ["MAIL_SERVER"], int(os.environ["MAIL_PORT"])) as smtp:
        smtp.login(os.environ["MAIL_SENDER"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)


@router.post("/register", response_model=Identity, status_code=status.HTTP_201_CREATED)
def register(
    credentials: RegistrationCredentials, request: Request, session: Session = Depends(get_session)
) -> Identity:
    if os.getenv("AUTH_REGISTRATION_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")
    email = credentials.email
    try:
        redis_client = _get_redis_client()
        if not _registration_rate_limit(redis_client, request.client.host if request.client else "unknown", email):
            raise HTTPException(
                status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many requests", "details": {}}
            )
        validate_password(credentials.password)
        user = User(email=email, password_hash=hash_password(credentials.password))
        session.add(user)
        session.flush()
        raw_token, token_hash = new_auth_token()
        token = AuthToken(
            user_id=user.id,
            purpose=_EMAIL_VERIFICATION_PURPOSE,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=_EMAIL_VERIFICATION_TTL_SECONDS),
        )
        session.add(token)
        session.flush()
        _send_verification_email(raw_token, user.email)
        session.commit()
        session.refresh(user)
    except HTTPException:
        session.rollback()
        raise
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        if not _is_email_unique_violation(exc):
            raise
        raise HTTPException(status_code=409, detail="Registration failed") from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="Registration is temporarily unavailable") from exc
    return _identity(user)


@router.get("/verify-email")
def verify_email(token: str, session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        now = datetime.now(timezone.utc)
        token_row = session.scalar(
            select(AuthToken).where(
                AuthToken.token_hash == hash_auth_token(token),
                AuthToken.purpose == _EMAIL_VERIFICATION_PURPOSE,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
        )
        if token_row is None:
            raise ValueError
        claim_result = session.execute(
            update(AuthToken)
            .where(
                AuthToken.id == token_row.id,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim_result, "rowcount", 0) != 1:
            raise ValueError
        user = session.get(User, token_row.user_id)
        if user is None:
            raise ValueError
        user.email_verified_at = now
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_REQUEST", "message": "Invalid verification token", "details": {}},
        ) from exc
    return {"message": "Email has been verified."}


@router.post("/resend-verification-email", status_code=status.HTTP_202_ACCEPTED)
def resend_verification_email(
    payload: ResendVerificationRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    normalized_email = normalize_email(payload.email)
    try:
        redis_client = _get_redis_client()
        if not _verification_email_rate_limit(
            redis_client, request.client.host if request.client else "unknown", normalized_email
        ):
            raise HTTPException(
                status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many requests", "details": {}}
            )
        user = session.scalar(select(User).where(User.email == normalized_email, User.email_verified_at.is_(None)))
        if user is None:
            return _EMAIL_VERIFICATION_RESPONSE
        raw_token, token_hash = new_auth_token()
        session.add(
            AuthToken(
                user_id=user.id,
                purpose=_EMAIL_VERIFICATION_PURPOSE,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=_EMAIL_VERIFICATION_TTL_SECONDS),
            )
        )
        session.flush()
        _send_verification_email(raw_token, user.email)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
    return _EMAIL_VERIFICATION_RESPONSE


@router.post("/login", response_model=Identity)
def login(
    credentials: Credentials,
    response: Response,
    request: Request,
    session: Session = Depends(get_session),
) -> Identity:
    email = normalize_email(credentials.email)
    try:
        redis_client = _get_redis_client()
        if not _login_rate_limit(redis_client, request.client.host if request.client else "unknown", email):
            raise _generic_unauthorized(AuthEvidenceCode.AUTH_RATE_LIMITED)
    except HTTPException:
        raise
    except Exception as exc:
        request_id = request_id_from_request(request)
        print(render_evidence(AuthEvidenceCode.AUTH_UNAVAILABLE, "/auth/login", request_id))
        raise HTTPException(
            status_code=503,
            headers={"X-Request-ID": request_id},
            detail=error_detail(
                AuthEvidenceCode.AUTH_UNAVAILABLE,
                "登录服务暂时不可用，请稍后重试。",
                request_id,
            ),
        ) from exc

    try:
        user = session.scalar(select(User).where(User.email == email))
    except Exception as exc:
        request_id = request_id_from_request(request)
        print(render_evidence(AuthEvidenceCode.AUTH_UNAVAILABLE, "/auth/login", request_id))
        raise HTTPException(
            status_code=503,
            headers={"X-Request-ID": request_id},
            detail=error_detail(
                AuthEvidenceCode.AUTH_UNAVAILABLE,
                "登录服务暂时不可用，请稍后重试。",
                request_id,
            ),
        ) from exc
    password_hash = user.password_hash if user is not None and credentials.password else _DUMMY_PASSWORD_HASH
    try:
        password_valid = verify_password(credentials.password, password_hash)
    except Exception as exc:
        request_id = request_id_from_request(request)
        print(render_evidence(AuthEvidenceCode.AUTH_UNAVAILABLE, "/auth/login", request_id))
        raise HTTPException(
            status_code=503,
            headers={"X-Request-ID": request_id},
            detail=error_detail(
                AuthEvidenceCode.AUTH_UNAVAILABLE,
                "登录服务暂时不可用，请稍后重试。",
                request_id,
            ),
        ) from exc
    if user is None or not password_valid or user.email_verified_at is None:
        raise _generic_unauthorized()
    try:
        settings = AuthSettings.from_environment()
        build_session_cookie(response, create_session_token(user.id, user.session_version, settings), settings)
        build_csrf_cookie(response, secrets.token_urlsafe(32), settings)
    except Exception as exc:
        request_id = request_id_from_request(request)
        print(render_evidence(AuthEvidenceCode.AUTH_UNAVAILABLE, "/auth/login", request_id))
        raise HTTPException(
            status_code=503,
            headers={"X-Request-ID": request_id},
            detail=error_detail(
                AuthEvidenceCode.AUTH_UNAVAILABLE,
                "登录服务暂时不可用，请稍后重试。",
                request_id,
            ),
        ) from exc
    return _identity(user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    normalized_email = normalize_email(payload.email)
    try:
        redis_client = _get_redis_client()
        if not _password_reset_rate_limit(
            redis_client, request.client.host if request.client else "unknown", normalized_email
        ):
            raise HTTPException(
                status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many requests", "details": {}}
            )
        user = session.scalar(select(User).where(User.email == normalized_email, User.email_verified_at.is_not(None)))
        if user is None:
            return _PASSWORD_RESET_RESPONSE
        raw_token, token_hash = new_auth_token()
        session.add(
            AuthToken(
                user_id=user.id,
                purpose=_PASSWORD_RESET_PURPOSE,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=_PASSWORD_RESET_TTL_SECONDS),
            )
        )
        session.flush()
        _send_password_reset_email(raw_token, user.email)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
    return _PASSWORD_RESET_RESPONSE


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        validate_password(payload.password)
        now = datetime.now(timezone.utc)
        token_row = session.scalar(
            select(AuthToken).where(
                AuthToken.token_hash == hash_auth_token(payload.token),
                AuthToken.purpose == _PASSWORD_RESET_PURPOSE,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
        )
        if token_row is None:
            raise ValueError
        claim_result = session.execute(
            update(AuthToken)
            .where(
                AuthToken.id == token_row.id,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim_result, "rowcount", 0) != 1:
            raise ValueError
        user = session.get(User, token_row.user_id)
        if user is None:
            raise ValueError
        user.password_hash = hash_password(payload.password)
        user.session_version += 1
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_REQUEST", "message": "Invalid password reset token", "details": {}},
        )
    return {"message": "Password has been reset."}


@router.get("/me", response_model=Identity)
def me(user: User | None = Depends(require_browser_user)) -> Identity:
    if user is None:
        raise _generic_unauthorized()
    return _identity(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    user: User | None = Depends(require_browser_user),
    _: None = Depends(require_csrf),
    session: Session = Depends(get_session),
) -> Response:
    if user is None:
        raise _generic_unauthorized()
    result = session.execute(
        update(User)
        .where(User.id == user.id, User.session_version == user.session_version)
        .values(session_version=User.session_version + 1)
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        raise _generic_unauthorized()
    session.commit()
    clear_auth_cookies(response, AuthSettings.from_environment())
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _is_email_unique_violation(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return "users.email" in message or "users_email_key" in message
