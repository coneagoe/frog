"""
黑名单（blackroom）持久化存储的 TDD 测试套件。

覆盖范围：
  - storage 包导出合约（BlackroomRecord, tb_name_blackroom_record）
  - create_blackroom_record（所有字段、默认值、ban_days 自动计算 expire_at）
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
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from storage.config import StorageConfig  # noqa: E402
from storage.storage_db import get_storage, reset_storage  # noqa: E402

# ---------------------------------------------------------------------------
# Export contract
# ---------------------------------------------------------------------------


class TestExportContract:
    def test_blackroom_record_exported_from_storage(self):
        import storage

        assert hasattr(
            storage, "BlackroomRecord"
        ), "storage must export BlackroomRecord"
        assert "BlackroomRecord" in storage.__all__

    def test_tb_name_blackroom_record_exported_from_storage(self):
        import storage

        assert hasattr(storage, "tb_name_blackroom_record")
        assert "tb_name_blackroom_record" in storage.__all__
        assert storage.tb_name_blackroom_record == "blackroom_records"

    def test_blackroom_record_exported_from_storage_model(self):
        from storage.model import BlackroomRecord, tb_name_blackroom_record

        assert BlackroomRecord.__tablename__ == "blackroom_records"
        assert tb_name_blackroom_record == "blackroom_records"

    def test_blackroom_record_has_approved_schema_fields(self):
        from storage.model import BlackroomRecord

        columns = {c.name for c in BlackroomRecord.__table__.columns}
        expected = {
            "id",
            "stock_code",
            "market",
            "ban_days",
            "start_at",
            "expire_at",
            "source",
            "note",
            "enabled",
            "created_at",
            "updated_at",
        }
        assert expected <= columns, f"Missing columns: {expected - columns}"


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
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        record = db.create_blackroom_record(
            stock_code="600519",
            market="A",
            ban_days=30,
            start_at=start,
            expire_at=expire,
            source="manual",
            note="基本面恶化",
            enabled=True,
        )

        assert record.id is not None
        assert record.stock_code == "600519"
        assert record.market == "A"
        assert record.ban_days == 30
        # SQLite strips tz info; compare naive equivalents
        assert record.start_at.replace(tzinfo=None) == start.replace(tzinfo=None)
        assert record.expire_at.replace(tzinfo=None) == expire.replace(tzinfo=None)
        assert record.source == "manual"
        assert record.note == "基本面恶化"
        assert record.enabled is True

    def test_defaults_market_source_enabled(self, sqlite_storage):
        db = sqlite_storage

        record = db.create_blackroom_record(stock_code="000001")

        assert record.market == "A"
        assert record.source == "manual"
        assert record.enabled is True
        assert record.expire_at is None
        assert record.note is None
        assert record.ban_days is None
        assert record.start_at is not None  # defaults to current time

    def test_auto_computes_expire_at_from_ban_days(self, sqlite_storage):
        db = sqlite_storage
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)

        record = db.create_blackroom_record(
            stock_code="000001",
            ban_days=10,
            start_at=start,
        )

        expected_expire = (start + timedelta(days=10)).replace(tzinfo=None)
        # SQLite strips tz info; compare naive equivalents
        assert record.expire_at.replace(tzinfo=None) == expected_expire

    def test_explicit_expire_at_overrides_ban_days(self, sqlite_storage):
        db = sqlite_storage
        explicit_expire = datetime(2099, 1, 1, tzinfo=timezone.utc)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        record = db.create_blackroom_record(
            stock_code="000001",
            ban_days=5,
            start_at=start,
            expire_at=explicit_expire,
        )

        # SQLite strips tz info; compare naive equivalents
        assert record.expire_at.replace(tzinfo=None) == explicit_expire.replace(
            tzinfo=None
        )

    def test_start_at_defaults_to_now_when_omitted(self, sqlite_storage):
        db = sqlite_storage
        before = datetime.now(timezone.utc)

        record = db.create_blackroom_record(stock_code="000001", ban_days=7)

        after = datetime.now(timezone.utc)
        assert record.start_at is not None
        # start_at is within [before, after] (SQLite strips tz, compare naive)
        start_naive = record.start_at.replace(tzinfo=None)
        assert before.replace(tzinfo=None) <= start_naive <= after.replace(tzinfo=None)
        # expire_at is auto-computed from default start_at + ban_days
        assert record.expire_at is not None

    def test_each_record_gets_unique_id(self, sqlite_storage):
        db = sqlite_storage

        r1 = db.create_blackroom_record(stock_code="000001")
        r2 = db.create_blackroom_record(stock_code="000002")

        assert r1.id != r2.id

    def test_hk_market_record(self, sqlite_storage):
        db = sqlite_storage

        record = db.create_blackroom_record(
            stock_code="00700", market="HK", source="manual"
        )

        assert record.market == "HK"


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
        future = datetime.now(timezone.utc) + timedelta(days=30)
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=future)
        db.create_blackroom_record(stock_code="000002", enabled=False, expire_at=future)

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

    def test_excludes_records_with_null_expire_at(self, sqlite_storage):
        db = sqlite_storage
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=None)

        active = db.list_active_blackroom_records()

        assert active == []

    def test_includes_records_expiring_in_future(self, sqlite_storage):
        db = sqlite_storage
        future = datetime.now(timezone.utc) + timedelta(days=365)
        db.create_blackroom_record(stock_code="000001", enabled=True, expire_at=future)

        active = db.list_active_blackroom_records()

        assert len(active) == 1

    def test_filters_by_market(self, sqlite_storage):
        db = sqlite_storage
        future = datetime.now(timezone.utc) + timedelta(days=30)
        db.create_blackroom_record(
            stock_code="000001", market="A", enabled=True, expire_at=future
        )
        db.create_blackroom_record(
            stock_code="00700", market="HK", enabled=True, expire_at=future
        )

        active_a = db.list_active_blackroom_records(market="A")

        assert len(active_a) == 1
        assert active_a[0].stock_code == "000001"

    def test_combined_disabled_and_expired(self, sqlite_storage):
        db = sqlite_storage
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        future2 = datetime.now(timezone.utc) + timedelta(days=2)
        # disabled but not expired -> excluded
        db.create_blackroom_record(stock_code="000001", enabled=False, expire_at=future)
        # enabled but expired -> excluded
        db.create_blackroom_record(stock_code="000002", enabled=True, expire_at=past)
        # enabled, future expiry -> included
        db.create_blackroom_record(stock_code="000003", enabled=True, expire_at=future2)
        # enabled, no expiry -> excluded (NULL expire_at is not active)
        db.create_blackroom_record(stock_code="000004", enabled=True, expire_at=None)

        active = db.list_active_blackroom_records()

        codes = [r.stock_code for r in active]
        assert codes == ["000003"]


# ---------------------------------------------------------------------------
# update_blackroom_record
# ---------------------------------------------------------------------------


class TestUpdateBlackroomRecord:
    def test_updates_allowed_fields(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(
            stock_code="000001", note="旧备注", enabled=True
        )

        updated = db.update_blackroom_record(record.id, note="新备注", enabled=False)

        assert updated is not None
        assert updated.note == "新备注"
        assert updated.enabled is False

    def test_updates_source_and_ban_days(self, sqlite_storage):
        db = sqlite_storage
        record = db.create_blackroom_record(stock_code="000001")

        updated = db.update_blackroom_record(
            record.id, source="shareholder_reduction", ban_days=60
        )

        assert updated.source == "shareholder_reduction"
        assert updated.ban_days == 60

    def test_returns_none_for_missing_id(self, sqlite_storage):
        db = sqlite_storage

        result = db.update_blackroom_record(99999, note="whatever")

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

    def test_recomputes_expire_at_when_ban_days_updated(self, sqlite_storage):
        db = sqlite_storage
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = db.create_blackroom_record(
            stock_code="000001", ban_days=10, start_at=start
        )

        updated = db.update_blackroom_record(record.id, ban_days=20)

        expected_expire = (start + timedelta(days=20)).replace(tzinfo=None)
        assert updated.expire_at.replace(tzinfo=None) == expected_expire

    def test_recomputes_expire_at_when_start_at_updated(self, sqlite_storage):
        db = sqlite_storage
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = db.create_blackroom_record(
            stock_code="000001", ban_days=10, start_at=start
        )

        new_start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        updated = db.update_blackroom_record(record.id, start_at=new_start)

        expected_expire = (new_start + timedelta(days=10)).replace(tzinfo=None)
        assert updated.expire_at.replace(tzinfo=None) == expected_expire

    def test_explicit_expire_at_in_update_is_not_overridden(self, sqlite_storage):
        db = sqlite_storage
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = db.create_blackroom_record(
            stock_code="000001", ban_days=10, start_at=start
        )

        explicit_expire = datetime(2099, 12, 31, tzinfo=timezone.utc)
        updated = db.update_blackroom_record(
            record.id, ban_days=99, expire_at=explicit_expire
        )

        assert updated.expire_at.replace(tzinfo=None) == explicit_expire.replace(
            tzinfo=None
        )

    def test_clears_expire_at_when_ban_days_set_to_none(self, sqlite_storage):
        """Nulling ban_days must clear expire_at, not leave stale value."""
        db = sqlite_storage
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = db.create_blackroom_record(
            stock_code="000001", ban_days=10, start_at=start
        )
        assert record.expire_at is not None

        updated = db.update_blackroom_record(record.id, ban_days=None)

        assert updated.ban_days is None
        assert updated.expire_at is None

    def test_clears_expire_at_when_start_at_set_to_none(self, sqlite_storage):
        """Nulling start_at must clear expire_at, not leave stale value."""
        db = sqlite_storage
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record = db.create_blackroom_record(
            stock_code="000001", ban_days=10, start_at=start
        )
        assert record.expire_at is not None

        updated = db.update_blackroom_record(record.id, start_at=None)

        assert updated.start_at is None
        assert updated.expire_at is None


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
