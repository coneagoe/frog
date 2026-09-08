import logging
from datetime import datetime, timezone

from celery_app import app
from monitor.domain_enums import NotificationDeliveryState
from storage import get_storage
from utility import send_email

logger = logging.getLogger(__name__)

_CLAIM_LIMIT = 100


@app.task
def deliver_monitor_notifications() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    storage = get_storage()
    notifications = storage.claim_due_monitor_notifications(now, _CLAIM_LIMIT)
    summary = {"claimed": len(notifications), "delivered": 0, "retried": 0, "failed": 0, "cancelled": 0}

    for notification in notifications:
        notification_id = str(notification.id)
        try:
            send_email(notification.subject, notification.body)
        except Exception:
            logger.warning(
                "Monitor notification delivery failed notification_id=%s target_id=%s",
                notification_id,
                notification.target_id,
            )
            state = storage.record_monitor_notification_failure(notification_id, "email delivery failed", now)
            if state == NotificationDeliveryState.CANCELLED:
                summary["cancelled"] += 1
            elif state == NotificationDeliveryState.FAILED:
                summary["failed"] += 1
            else:
                summary["retried"] += 1
            continue

        if storage.mark_monitor_notification_delivered(notification_id, now):
            summary["delivered"] += 1
            logger.info(
                "Monitor notification delivered notification_id=%s target_id=%s",
                notification_id,
                notification.target_id,
            )
        else:
            summary["cancelled"] += 1
            logger.info(
                "Monitor notification cancelled notification_id=%s target_id=%s",
                notification_id,
                notification.target_id,
            )

    return summary
