import importlib
import os
import sys
from types import SimpleNamespace

from celery.schedules import crontab

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import celery_config  # noqa: E402
from monitor.domain_enums import NotificationDeliveryState  # noqa: E402

delivery_module = importlib.import_module("task.monitor_notification_delivery")


class FakeStorage:
    def __init__(self, notifications, delivered=True, failure_state=NotificationDeliveryState.PENDING):
        self.notifications = notifications
        self.delivered = delivered
        self.failure_state = failure_state
        self.claims = []
        self.deliveries = []
        self.failures = []

    def claim_due_monitor_notifications(self, now, limit):
        self.claims.append((now, limit))
        return self.notifications

    def mark_monitor_notification_delivered(self, notification_id, delivered_at):
        self.deliveries.append((notification_id, delivered_at))
        return self.delivered

    def record_monitor_notification_failure(self, notification_id, error, occurred_at):
        self.failures.append((notification_id, error, occurred_at))
        return self.failure_state


def _notification(notification_id="notification-1", target_id=42, subject="Saved subject", body="Saved body"):
    return SimpleNamespace(id=notification_id, target_id=target_id, subject=subject, body=body)


def _run(monkeypatch, storage, send_email=lambda *_args: None):
    monkeypatch.setattr(delivery_module, "get_storage", lambda: storage)
    monkeypatch.setattr(delivery_module, "send_email", send_email)
    return delivery_module.deliver_monitor_notifications.run()


def test_delivery_returns_empty_summary_when_no_notifications_are_due(monkeypatch):
    storage = FakeStorage([])

    assert _run(monkeypatch, storage) == {
        "claimed": 0,
        "delivered": 0,
        "retried": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert storage.claims[0][1] > 0


def test_delivery_sends_stored_content_and_records_success(monkeypatch):
    storage = FakeStorage([_notification()])
    sent = []

    result = _run(monkeypatch, storage, lambda subject, body: sent.append((subject, body)))

    assert result == {
        "claimed": 1,
        "delivered": 1,
        "retried": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert sent == [("Saved subject", "Saved body")]
    assert storage.deliveries[0][0] == "notification-1"


def test_delivery_records_retry_when_email_fails_before_terminal_attempt(monkeypatch):
    storage = FakeStorage([_notification()], failure_state=NotificationDeliveryState.PENDING)

    result = _run(monkeypatch, storage, lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp unavailable")))

    assert result == {
        "claimed": 1,
        "delivered": 0,
        "retried": 1,
        "failed": 0,
        "cancelled": 0,
    }
    assert storage.failures[0][0] == "notification-1"


def test_delivery_records_terminal_failure_when_email_fails_on_final_attempt(monkeypatch):
    storage = FakeStorage([_notification()], failure_state=NotificationDeliveryState.FAILED)

    result = _run(monkeypatch, storage, lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp unavailable")))

    assert result == {
        "claimed": 1,
        "delivered": 0,
        "retried": 0,
        "failed": 1,
        "cancelled": 0,
    }


def test_delivery_counts_cancelled_when_email_fails_after_target_deletion(monkeypatch):
    storage = FakeStorage([_notification()], failure_state=NotificationDeliveryState.CANCELLED)

    result = _run(monkeypatch, storage, lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp unavailable")))

    assert result == {
        "claimed": 1,
        "delivered": 0,
        "retried": 0,
        "failed": 0,
        "cancelled": 1,
    }


def test_delivery_counts_claim_lost_before_success_as_cancelled(monkeypatch):
    storage = FakeStorage([_notification()], delivered=False)

    assert _run(monkeypatch, storage) == {
        "claimed": 1,
        "delivered": 0,
        "retried": 0,
        "failed": 0,
        "cancelled": 1,
    }


def test_celery_beat_preserves_existing_schedule_and_adds_delivery_every_minute():
    assert (
        celery_config.beat_schedule["small_market_capital_2_daily"]["task"]
        == "task.small_market_capital_2.small_market_capital_2"
    )
    delivery = celery_config.beat_schedule["deliver_monitor_notifications"]
    assert delivery["task"] == "task.monitor_notification_delivery.deliver_monitor_notifications"
    assert delivery["schedule"] == crontab(minute="*")
