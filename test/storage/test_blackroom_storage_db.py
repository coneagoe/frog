"""
黑名单（blackroom）持久化存储的 TDD 测试套件。

覆盖范围：
  - create_blackroom_record
  - get_blackroom_record
  - list_blackroom_records
  - list_active_blackroom_records (honors enabled=True AND expire_at > now)
  - update_blackroom_record
  - delete_blackroom_record
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from storage.config import StorageConfig  # noqa: E402
from storage.storage_db import get_storage, reset_storage  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture: SQLite in-memory database wired into StorageDb
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_storage(tmp_path, monkeypatch):
    from sqlalchemy import create_engine as real_create_engine

    from storage.model import Base

    sqlite_url = f"sqlite:///{tmp_path}/test_blackroom.db"
    engine = real_create_engine(sqlite_url)
    Base.metadata.create_all(engine)

    reset_storage()
    mock_config = Mock(spec=StorageConfig)
    mock_config.get_db_host.return_value = "localhost"
    mock_config.get_db_port.return_value = 5432
    mock_config.get_db_name.return_value = "test_db"
    mock_config.get_db_username.return_value = "test_user"
    mock_config.get_db_password.return_value = "test_pass"

    monkeypatch.setattr("storage.storage_db.create_engine", lambda *a, **kw: engine)
    monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
    monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

    db = get_storage(mock_config)
    db.engine = engine
    db.Session = sessionmaker(bind=engine)
    yield db
    reset_storage()


# ---------------------------------------------------------------------------
# create_blackroom_record
# ---------------------------------------------------------------------------


class TestCreateBlackroomRecord:
    def test_returns_persisted_record_with_all_fields(self, sqlite_storage):
        db = sqlite_storage
        expire = datetime(2030, 12, 31, tzinfo=timezone.utc)

        record = db.create_blackroom_record(
            stock_code="600519",
            market="A",
            reason="基本面恶化",
            enabled=True,
            expire_at=expire,
        )

        assert record.id is not None
        assert record.stock_code == "600519"
        assert record.market == "A"
        assert record.reason == "基本面恶化"
        assert record.enabled is True

    def test_defaults_market_to_A_and_enabled_to_true(self, sqlite_storage):
        db = sqlite_storage

        record = db.create_blackroom_record(stock_code="000001")

        assert record.market == "A"
        assert record.enabled is True
        assert record.expire_at is None
        assert record.reason is None

    def test_multiple_records_get_distinct_ids(self, sqlite_storage):
        db = sqlite_storage

        r1 = db.create_blackroom_record(stock_code="000001")
        r2 = db.create_blackroom_record(stock_code="000002")

        assert r1.id != r2.id


# ---------------------------------------------------------------------------
# get_blackroom_record
# ---------------------------------------------------------------------------


class TestGetBlackroomRecord:
    def test_returns_record_by_id(self, sqlite_storage):
        db = sqlite_storage
        created = db.create_blackroom_record(stock_code="600036", market="A")

        fetched = db.get_blackroom_record(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.stock_code == "600036"

    def test_returns_none_for_missing_id(self, sqlite_storage):
        db = sqlite_storage

        result = db.get_blackroom_record(99999)

        assert result is None


# ---------------------------------------------------------------------------
# list_blackroom_records
# ---------------------------------------------------------------------------


class TestListBlackroomRecords:
    def test_returns_all_records_when_no_filter(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", market="A")
        db.create_blackroom_record(stock_code="00700", market="HK")

        records = db.list_blackroom_records()

        assert len(records) == 2

    def test_filters_by_market(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", market="A")
        db.create_blackroom_record(stock_code="00700", market="HK")

        records = db.list_blackroom_records(market="A")

        assert len(records) == 1
        assert records[0].stock_code == "000001"

    def test_filters_by_enabled(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", enabled=True)
        db.create_blackroom_record(stock_code="000002", enabled=False)

        active = db.list_blackroom_records(enabled=True)
        inactive = db.list_blackroom_records(enabled=False)

        assert len(active) == 1
        assert active[0].stock_code == "000001"
        assert len(inactive) == 1
        assert inactive[0].stock_code == "000002"

    def test_returns_empty_list_when_no_records(self, sqlite_storage):
        db = sqlite_storage

        records = db.list_blackroom_records()

        assert records == []


# ---------------------------------------------------------------------------
# list_active_blackroom_records
# ---------------------------------------------------------------------------


class TestListActiveBlackroomRecords:
    def test_excludes_disabled_records(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", enabled=True)
        db.create_blackroom_record(stock_code="000002", enabled=False)

        active = db.list_active_blackroom_records()

        codes = [r.stock_code for r in active]
        assert "000001" in codes
        assert "000002" not in codes

    def test_excludes_expired_records(self, sqlite_storage):
        db = sqlite_storage
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=past)

        active = db.list_active_blackroom_records()

        assert active == []

    def test_includes_records_with_no_expiry(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=None)

        active = db.list_active_blackroom_records()

        assert len(active) == 1
        assert active[0].stock_code == "000001"

    def test_includes_records_expiring_in_future(self, sqlite_storage):
        db = sqlite_storage
        future = datetime.now(timezone.utc) + timedelta(days=365)
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=future)

        active = db.list_active_blackroom_records()

        assert len(active) == 1

    def test_filters_by_market(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", market="A", enabled=True)
        db.create_blackroom_record(stock_code="00700", market="HK", enabled=True)

        active_a = db.list_active_blackroom_records(market="A")

        assert len(active_a) == 1
        assert active_a[0].stock_code == "000001"

    def test_combined_disabled_and_expired(self, sqlite_storage):
        db = sqlite_storage
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        # disabled but not expired -> excluded
        db.create_blackroom_record(stock_code="000001", enabled=False, expire_at=future)
        # enabled but expired -> excluded
        db.create_blackroom_record(stock_code="000002", enabled=True, expire_at=past)
        # enabled, no expiry -> included
        db.create_blackroom_record(stock_code="000003", enabled=True, expire_at=None)

        active = db.list_active_blackroom_records()

        codes = [r.stock_code for r in active]
        assert codes == ["000003"]


# ---------------------------------------------------------------------------
# update_blackroom_record
# ---------------------------------------------------------------------------


class TestUpdateBlackroomRecord:
    def test_updates_allowed_fields(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(stock_code="000001", reason="旧理由", enabled=True)

        updated = db.update_blackroom_record(record.id, reason="新理由", enabled=False)

        assert updated is not None
        assert updated.reason == "新理由"
        assert updated.enabled is False

    def test_returns_none_for_missing_id(self, sqlite_storage):
        db = sqlite_storage

        result = db.update_blackroom_record(99999, reason="whatever")

        assert result is None

    def test_raises_for_invalid_field(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(stock_code="000001")

        with pytest.raises(ValueError, match="不支持更新字段"):
            db.update_blackroom_record(record.id, nonexistent_field="x")

    def test_persists_update_across_sessions(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(stock_code="000001", enabled=True)

        db.update_blackroom_record(record.id, enabled=False)
        fetched = db.get_blackroom_record(record.id)

        assert fetched.enabled is False


# ---------------------------------------------------------------------------
# delete_blackroom_record
# ---------------------------------------------------------------------------


class TestDeleteBlackroomRecord:
    def test_removes_record_and_returns_true(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(stock_code="000001")

        result = db.delete_blackroom_record(record.id)

        assert result is True
        assert db.get_blackroom_record(record.id) is None

    def test_returns_false_for_missing_id(self, sqlite_storage):
        db = sqlite_storage

        result = db.delete_blackroom_record(99999)

        assert result is False
