from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from monitor.domain_enums import NotificationDeliveryState
from storage.model import Base, MonitorNotification
from storage.storage_db import StorageDb


def _sqlite_storage(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/monitor_notifications.db")
    db.Session = sessionmaker(bind=db.engine)
    Base.metadata.create_all(db.engine)
    return db


def _target(db):
    return db.create_monitor_target("600001", "A", {"type": "price_threshold", "direction": "above", "value": 10})


def _notification(db, target_id, triggered_at):
    notification_id = db.create_monitor_notification_for_trigger(target_id, "Subject", "Body", triggered_at)
    assert notification_id is not None
    return notification_id


def _load(db, notification_id):
    session = db.Session()
    try:
        return session.get(MonitorNotification, UUID(notification_id))
    finally:
        session.close()


def test_create_notification_is_atomic_edge_and_noops_after_trigger(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = _target(db)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    notification_id = _notification(db, target.id, now)

    assert db.create_monitor_notification_for_trigger(target.id, "Again", "Again", now) is None
    assert _load(db, notification_id).state == NotificationDeliveryState.PENDING.value
    saved_target = db.get_monitor_target(target.id)
    assert (saved_target.last_state, saved_target.triggered_at) == (True, now.replace(tzinfo=None))


def test_create_notification_noops_for_disabled_target(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = _target(db)
    target.enabled = False
    session = db.Session()
    try:
        session.merge(target)
        session.commit()
    finally:
        session.close()

    assert (
        db.create_monitor_notification_for_trigger(
            target.id, "Subject", "Body", datetime(2026, 9, 8, tzinfo=timezone.utc)
        )
        is None
    )
    session = db.Session()
    try:
        assert session.query(MonitorNotification).count() == 0
    finally:
        session.close()
    assert db.get_monitor_target(target.id).last_state is False


def test_create_notification_rolls_back_target_update_when_insert_fails(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    target = _target(db)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    original_add = type(db.Session()).add

    def fail_add(self, value, *args, **kwargs):
        if isinstance(value, MonitorNotification):
            raise RuntimeError("insert failed")
        return original_add(self, value, *args, **kwargs)

    monkeypatch.setattr(type(db.Session()), "add", fail_add)
    with pytest.raises(RuntimeError, match="insert failed"):
        db.create_monitor_notification_for_trigger(target.id, "Subject", "Body", now)
    assert db.get_monitor_target(target.id).last_state is False


def test_claims_due_notifications_and_recovers_stale_leases(tmp_path):
    db = _sqlite_storage(tmp_path)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    first = _notification(db, _target(db).id, now)
    second = _notification(db, _target(db).id, now)

    claimed = db.claim_due_monitor_notifications(now, 1)
    assert [str(row.id) for row in claimed] == [first]
    assert _load(db, first).state == NotificationDeliveryState.PROCESSING.value
    assert db.claim_due_monitor_notifications(now, 10)[0].id.hex == second.replace("-", "")

    session = db.Session()
    try:
        row = session.get(MonitorNotification, UUID(first))
        row.claimed_at = now - timedelta(minutes=31)
        session.commit()
    finally:
        session.close()
    assert [str(row.id) for row in db.claim_due_monitor_notifications(now, 10)] == [first]


def test_delivery_retry_terminal_failure_and_error_sanitization(tmp_path):
    db = _sqlite_storage(tmp_path)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    notification_id = _notification(db, _target(db).id, now)

    assert db.claim_due_monitor_notifications(now, 1)
    assert (
        db.record_monitor_notification_failure(notification_id, "token=secret https://example.test/x", now)
        == NotificationDeliveryState.PENDING
    )
    saved = _load(db, notification_id)
    assert (saved.attempt_count, saved.next_attempt_at, saved.last_error) == (
        1,
        (now + timedelta(minutes=1)).replace(tzinfo=None),
        "[redacted] [redacted]",
    )
    assert saved.claimed_at is None

    for attempt in range(2, 6):
        when = _load(db, notification_id).next_attempt_at
        assert db.claim_due_monitor_notifications(when, 1)
        state = db.record_monitor_notification_failure(notification_id, "delivery failed", when)
    saved = _load(db, notification_id)
    assert (state, saved.state, saved.attempt_count) == (
        NotificationDeliveryState.FAILED,
        NotificationDeliveryState.FAILED.value,
        5,
    )
    assert saved.claimed_at is None
    assert db.mark_monitor_notification_delivered(notification_id, now) is False


def test_mark_delivered_requires_processing_notification(tmp_path):
    db = _sqlite_storage(tmp_path)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    notification_id = _notification(db, _target(db).id, now)

    assert not db.mark_monitor_notification_delivered(notification_id, now)
    db.claim_due_monitor_notifications(now, 1)
    assert db.mark_monitor_notification_delivered(notification_id, now)
    saved = _load(db, notification_id)
    assert saved.state == NotificationDeliveryState.DELIVERED.value
    assert saved.claimed_at is None


def test_failure_for_cancelled_notification_returns_cancelled(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = _target(db)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    notification_id = _notification(db, target.id, now)
    db.claim_due_monitor_notifications(now, 1)

    session = db.Session()
    try:
        session.get(MonitorNotification, UUID(notification_id)).state = NotificationDeliveryState.CANCELLED.value
        session.commit()
    finally:
        session.close()

    assert (
        db.record_monitor_notification_failure(notification_id, "delivery failed", now)
        == NotificationDeliveryState.CANCELLED
    )
