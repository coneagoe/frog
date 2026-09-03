from datetime import datetime, timezone

import pytest
from sqlalchemy import DateTime, Index, Integer, String, inspect
from sqlalchemy.exc import IntegrityError

from storage.model import AuthToken, Base, User, tb_name_auth_tokens, tb_name_users


def test_auth_models_create_with_constraints(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    user = User(email="operator@example.com", password_hash="argon2-hash")
    sqlite_session.add(user)
    sqlite_session.flush()
    token = AuthToken(
        user_id=user.id,
        purpose="session",
        token_hash="hashed-token",
        expires_at=datetime.now(timezone.utc),
    )
    sqlite_session.add(token)
    sqlite_session.flush()

    assert user.session_version == 1
    assert user.email_verified_at is None
    assert token.id is not None
    assert token.user_id == user.id
    assert inspect(sqlite_session.get_bind()).has_table(tb_name_users)
    assert inspect(sqlite_session.get_bind()).has_table(tb_name_auth_tokens)

    users = User.__table__
    auth_tokens = AuthToken.__table__
    assert users.c.email.type.length == 320
    assert isinstance(users.c.id.type, Integer)
    assert isinstance(users.c.password_hash.type, String)
    assert isinstance(users.c.email_verified_at.type, DateTime)
    assert isinstance(users.c.session_version.type, Integer)
    assert users.c.email.nullable is False
    assert users.c.password_hash.nullable is False
    assert users.c.email_verified_at.nullable is True
    assert users.c.session_version.nullable is False
    assert users.c.created_at.nullable is False
    assert users.c.updated_at.nullable is False
    assert isinstance(auth_tokens.c.user_id.type, Integer)
    assert isinstance(auth_tokens.c.purpose.type, String)
    assert isinstance(auth_tokens.c.token_hash.type, String)
    assert isinstance(auth_tokens.c.expires_at.type, DateTime)
    assert isinstance(auth_tokens.c.used_at.type, DateTime)
    assert auth_tokens.c.user_id.nullable is False
    assert auth_tokens.c.purpose.nullable is False
    assert auth_tokens.c.token_hash.nullable is False
    assert auth_tokens.c.expires_at.nullable is False
    assert auth_tokens.c.used_at.nullable is True
    assert "raw_token" not in users.c and "raw_token" not in auth_tokens.c

    foreign_keys = list(auth_tokens.c.user_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert isinstance(foreign_keys[0].column.type, Integer)
    assert foreign_keys[0].target_fullname == "users.id"
    indexes = {index.name: index for index in auth_tokens.indexes}
    purpose_expiry_index = indexes["ix_auth_tokens_purpose_expires_at"]
    assert isinstance(purpose_expiry_index, Index)
    assert [column.name for column in purpose_expiry_index.columns] == ["purpose", "expires_at"]


def test_user_email_is_unique(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    normalized_user = User(email=" Operator@Example.com ", password_hash="a")
    duplicate_user = User(email="operator@example.com", password_hash="b")
    assert normalized_user.email == "operator@example.com"
    assert duplicate_user.email == "operator@example.com"
    sqlite_session.add_all([normalized_user, duplicate_user])
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
