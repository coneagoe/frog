import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from storage.model import Base, User


def test_auth_models_create_with_constraints(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    user = User(email="operator@example.com", password_hash="argon2-hash")
    sqlite_session.add(user)
    sqlite_session.flush()

    assert user.session_version == 1
    assert user.email_verified_at is None
    assert inspect(sqlite_session.get_bind()).has_table("users")
    assert inspect(sqlite_session.get_bind()).has_table("auth_tokens")


def test_user_email_is_unique(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add_all(
        [User(email="same@example.com", password_hash="a"), User(email="same@example.com", password_hash="b")]
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
