import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from storage.model import AuthToken, Base, User


def test_auth_schema_is_fresh_and_idempotent_on_postgresql():
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")

    engine = create_engine(url)
    tables = [User.__table__, AuthToken.__table__]
    try:
        Base.metadata.drop_all(engine, tables=tables)
        Base.metadata.create_all(engine, tables=tables)
        Base.metadata.create_all(engine, tables=tables)

        database_inspector = inspect(engine)
        assert database_inspector.has_table("users")
        assert database_inspector.has_table("auth_tokens")
        assert {index["name"] for index in database_inspector.get_indexes("users")} >= {"ix_users_email"}
        assert {index["name"] for index in database_inspector.get_indexes("auth_tokens")} >= {
            "ix_auth_tokens_user_id",
            "ix_auth_tokens_purpose_expires_at",
        }
        foreign_keys = database_inspector.get_foreign_keys("auth_tokens")
        assert any(
            foreign_key["referred_table"] == "users"
            and foreign_key["constrained_columns"] == ["user_id"]
            for foreign_key in foreign_keys
        )

        with Session(engine) as session:
            user = User(email=" Operator@Example.com ", password_hash="argon2-hash")
            session.add(user)
            session.flush()
            session.add(
                AuthToken(
                    user_id=user.id,
                    purpose="session",
                    token_hash="hashed-token",
                    expires_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
            assert session.scalar(select(User).where(User.email == "operator@example.com")) is not None
    finally:
        Base.metadata.drop_all(engine, tables=[AuthToken.__table__, User.__table__])
        engine.dispose()
