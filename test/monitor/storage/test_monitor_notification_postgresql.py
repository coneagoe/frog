from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from monitor.domain_enums import NotificationDeliveryState
from storage.model import MonitorNotification
from storage.storage_db import StorageDb


@pytest.fixture()
def postgres_storage() -> object:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    schema = f"monitor_notification_{uuid4().hex}"
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    db = StorageDb.__new__(StorageDb)
    db.engine = engine
    db.Session = sessionmaker(bind=engine)
    try:
        db.ensure_monitor_notification_tables()
        yield db
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _target(db: StorageDb):
    return db.create_monitor_target("600001", "A", {"type": "price_threshold", "direction": "above", "value": 10})


def _notification(db: StorageDb, target_id: int, when: datetime) -> str:
    notification_id = db.create_monitor_notification_for_trigger(target_id, "Subject", "Body", when)
    assert notification_id is not None
    return notification_id


def _load(db: StorageDb, notification_id: str) -> MonitorNotification:
    session = db.Session()
    try:
        row = session.get(MonitorNotification, UUID(notification_id))
        assert row is not None
        session.expunge(row)
        return row
    finally:
        session.close()


def _clone_db(db: StorageDb) -> StorageDb:
    clone = StorageDb.__new__(StorageDb)
    clone.engine = db.engine
    clone.Session = sessionmaker(bind=db.engine)
    return clone


def test_postgresql_concurrent_claims_return_one_notification(postgres_storage: StorageDb) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    notification_id = _notification(postgres_storage, _target(postgres_storage).id, now)
    workers = (_clone_db(postgres_storage), _clone_db(postgres_storage))

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda worker: worker.claim_due_monitor_notifications(now, 1), workers))

    claimed_ids = [str(row.id) for batch in claims for row in batch]
    assert claimed_ids.count(notification_id) == 1
    assert _load(postgres_storage, notification_id).state == NotificationDeliveryState.PROCESSING.value


def test_postgresql_failure_retries_then_becomes_terminal(postgres_storage: StorageDb) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    notification_id = _notification(postgres_storage, _target(postgres_storage).id, now)

    for attempt in range(1, 6):
        claimed = postgres_storage.claim_due_monitor_notifications(now, 1)[0]
        state = postgres_storage.record_monitor_notification_failure(
            notification_id, "delivery failed", now, claimed.claimed_at
        )
        expected = NotificationDeliveryState.FAILED if attempt == 5 else NotificationDeliveryState.PENDING
        assert state == expected
        if attempt < 5:
            now = _load(postgres_storage, notification_id).next_attempt_at

    assert postgres_storage.claim_due_monitor_notifications(now + timedelta(days=1), 1) == []


def test_postgresql_target_deletion_cancels_pending_and_processing_notifications(
    postgres_storage: StorageDb,
) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    target = _target(postgres_storage)
    pending_id = _notification(postgres_storage, target.id, now)
    assert postgres_storage.claim_due_monitor_notifications(now, 1)[0].id == UUID(pending_id)
    postgres_storage.update_monitor_target_state(target.id, False)
    processing_id = _notification(postgres_storage, target.id, now)
    assert _load(postgres_storage, processing_id).state == NotificationDeliveryState.PENDING.value

    assert postgres_storage.delete_monitor_target(target.id) is True
    assert _load(postgres_storage, pending_id).state == NotificationDeliveryState.CANCELLED.value
    assert _load(postgres_storage, processing_id).state == NotificationDeliveryState.CANCELLED.value
    assert postgres_storage.claim_due_monitor_notifications(now + timedelta(days=1), 10) == []
