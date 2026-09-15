from datetime import date
from types import SimpleNamespace

from paper_trading.domain.enums import DataGapRecoveryAlertDeliveryState
from paper_trading.services.data_gap_alert_service import DataGapAlertService


class RecordingRepository:
    def __init__(self):
        self.alerts = {}
        self.next_id = 1

    def get_alert(self, gap_id, cycle_key):
        return self.alerts.get((gap_id, cycle_key))

    def record_alert(self, gap_id, cycle_key, evidence):
        alert = SimpleNamespace(
            id=self.next_id,
            gap_id=gap_id,
            cycle_key=cycle_key,
            evidence=evidence,
            delivery_state=DataGapRecoveryAlertDeliveryState.PENDING,
        )
        self.next_id += 1
        self.alerts[(gap_id, cycle_key)] = alert
        return alert

    def update_alert_delivery(self, alert_id, state, metadata):
        alert = next(alert for alert in self.alerts.values() if alert.id == alert_id)
        alert.delivery_state = state
        alert.evidence = {**alert.evidence, "delivery": metadata}
        return alert


def gap():
    return SimpleNamespace(id=4, status="escalated", business_date=date(2026, 9, 15), stock_id="000001")


def test_escalation_is_deduplicated_by_failure_class_and_records_success(monkeypatch):
    repository = RecordingRepository()
    sent = []
    service = DataGapAlertService(repository=repository, sender=lambda subject, body: sent.append((subject, body)))

    first = service.send_escalation(gap(), failure_class="approval_required")
    second = service.send_escalation(gap(), failure_class="approval_required")

    assert first is second
    assert len(sent) == 1
    assert first.delivery_state == DataGapRecoveryAlertDeliveryState.DELIVERED
    assert first.evidence["delivery"]["state"] == "delivered"


def test_account_failure_uses_account_and_failure_cycle_and_keeps_gap_status(monkeypatch):
    repository = RecordingRepository()
    service = DataGapAlertService(repository=repository, sender=lambda subject, body: None)
    unresolved = gap()

    alert = service.send_account_recovery_failure(unresolved, account_id=22, failure_class="snapshot")

    assert alert.cycle_key == "account:22:snapshot"
    assert unresolved.status == "escalated"


def test_delivery_failure_is_persisted_without_secret_metadata():
    repository = RecordingRepository()

    def fail(_subject, _body):
        raise RuntimeError("smtp password=super-secret connection refused")

    alert = DataGapAlertService(repository=repository, sender=fail).send_recovery_system_failure(
        gap(), failure_class="provider_timeout"
    )

    assert alert.delivery_state == DataGapRecoveryAlertDeliveryState.FAILED
    delivery = alert.evidence["delivery"]
    assert delivery["state"] == "failed"
    assert "super-secret" not in str(delivery)
