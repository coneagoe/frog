import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_browser_user, require_csrf
from paper_trading.auth import (
    AuthSettings,
    build_csrf_cookie,
    build_session_cookie,
    clear_auth_cookies,
    create_session_token,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)
from storage.model.auth import User

_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$NGJ2+MUUColXDcqLKM6NHw$"
    "VmCfSMah6ivG0JZGbbYZXPdKVCu4ZbZI+Ye9FoFzh+M"
)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


class RegistrationCredentials(Credentials):
    password: str = Field(min_length=1)


class Identity(BaseModel):
    id: int
    email: str
    email_verified_at: datetime | None


def _identity(user: User) -> Identity:
    return Identity(id=user.id, email=user.email, email_verified_at=user.email_verified_at)


def _generic_unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": "Unauthorized", "details": {}},
    )


@router.post("/register", response_model=Identity, status_code=status.HTTP_201_CREATED)
def register(credentials: RegistrationCredentials, session: Session = Depends(get_session)) -> Identity:
    email = normalize_email(credentials.email)
    try:
        validate_password(credentials.password)
        user = User(email=email, password_hash=hash_password(credentials.password))
        session.add(user)
        session.commit()
        session.refresh(user)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        if not _is_email_unique_violation(exc):
            raise
        raise HTTPException(status_code=409, detail="email is already registered") from exc
    return _identity(user)


@router.post("/login", response_model=Identity)
def login(
    credentials: Credentials,
    response: Response,
    session: Session = Depends(get_session),
) -> Identity:
    user = session.scalar(select(User).where(User.email == normalize_email(credentials.email)))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(credentials.password, password_hash)
    if user is None or not password_valid or user.email_verified_at is None:
        raise _generic_unauthorized()
    settings = AuthSettings.from_environment()
    build_session_cookie(response, create_session_token(user.id, user.session_version, settings), settings)
    build_csrf_cookie(response, secrets.token_urlsafe(32), settings)
    return _identity(user)


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
