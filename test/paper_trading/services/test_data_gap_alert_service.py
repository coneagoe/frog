from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError

from paper_trading.domain.enums import DataGapRecoveryAlertDeliveryState
from paper_trading.services.data_gap_alert_service import DataGapAlertService
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository


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

    def claim_alert(self, gap_id, cycle_key, evidence):
        for retry in range(100):
            key = cycle_key if retry == 0 else f"{cycle_key}:retry:{retry}"
            existing = self.alerts.get((gap_id, key))
            if existing is None:
                return self.record_alert(gap_id, key, evidence), True
            if existing.delivery_state != DataGapRecoveryAlertDeliveryState.FAILED:
                return existing, False
        raise RuntimeError("unable to claim test alert cycle")

    def update_alert_delivery(self, alert_id, state, metadata):
        alert = next(alert for alert in self.alerts.values() if alert.id == alert_id)
        alert.delivery_state = state
        alert.evidence = {**alert.evidence, "delivery": metadata}
        return alert


def gap(market="a_share", stock_id="000001"):
    return SimpleNamespace(
        id=4, status="escalated", business_date=date(2026, 9, 15), market=market, stock_id=stock_id, adjust="bfq"
    )


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


def test_hk_alert_persists_market_and_renders_it_in_body():
    repository = RecordingRepository()
    sent = []
    service = DataGapAlertService(repository=repository, sender=lambda subject, body: sent.append(body))

    alert = service.send_escalation(gap("hk_connect", "00700"), failure_class="approval_required")

    assert alert.evidence["market"] == "hk_connect"
    assert alert.evidence["stock_id"] == "00700"
    assert "market=hk_connect" in sent[0]
    assert "stock_id=00700" in sent[0]


def test_hk_alert_rejects_wrong_symbol_identity():
    service = DataGapAlertService(repository=RecordingRepository(), sender=lambda *_: None)

    with pytest.raises(ValueError, match="invalid gap identifier"):
        service.send_escalation(gap("hk_connect", "000001"))


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


def test_failed_cycle_is_retryable_but_delivered_cycle_is_not():
    repository = RecordingRepository()
    calls = iter([RuntimeError("temporary"), None])
    service = DataGapAlertService(repository=repository, sender=lambda *_: None)

    def sender(*_):
        result = next(calls)
        if isinstance(result, Exception):
            raise result

    service.sender = sender
    failed = service.send_recovery_system_failure(gap(), failure_class="provider_timeout")
    retried = service.send_recovery_system_failure(gap(), failure_class="provider_timeout")
    delivered_again = service.send_recovery_system_failure(gap(), failure_class="provider_timeout")

    assert failed.delivery_state == DataGapRecoveryAlertDeliveryState.FAILED
    assert retried.delivery_state == DataGapRecoveryAlertDeliveryState.DELIVERED
    assert retried.cycle_key.endswith(":retry:1")
    assert delivered_again is retried


def test_recovery_system_failure_uses_safe_config_and_rejects_control_tokens(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_MAIL_FROM", "alerts@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "not-in-output")
    monkeypatch.setenv("ALERT_EMAILS", "ops@example.test")
    sent = []

    class SMTP:
        def __init__(self, host, port):
            assert (host, port) == ("smtp.example.test", 465)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def login(self, user, password):
            assert (user, password) == ("alerts@example.test", "not-in-output")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("paper_trading.services.data_gap_alert_service.smtplib.SMTP_SSL", SMTP)
    DataGapAlertService._send_smtp("Data gap recovery system failure", "provider_timeout")
    assert sent[0]["To"] == "ops@example.test"
    assert sent[0]["Subject"] == "Data gap recovery system failure"
    assert DataGapAlertService._safe_token("Provider_Timeout", "failure_class") == "provider_timeout"
    try:
        DataGapAlertService._safe_token("provider\nBcc: attacker", "failure_class")
    except ValueError:
        pass
    else:
        raise AssertionError("control characters must be rejected")


def test_claim_collision_rereads_contested_key_before_allocating_retry():
    session = Mock()
    savepoint = Mock()
    savepoint.__enter__ = Mock(return_value=savepoint)
    savepoint.__exit__ = Mock(return_value=None)
    session.begin_nested.return_value = savepoint
    repository = DataGapRecoveryRepository(session)
    winner = SimpleNamespace(delivery_state=DataGapRecoveryAlertDeliveryState.PENDING)
    get_alert = Mock(side_effect=[None, winner])
    record_alert = Mock(side_effect=IntegrityError("insert", {}, Exception("collision")))
    setattr(repository, "get_alert", get_alert)
    setattr(repository, "record_alert", record_alert)

    alert, claimed = repository.claim_alert(4, "recovery_system:provider_timeout", {})

    assert alert is winner
    assert claimed is False
    assert record_alert.call_count == 1
    assert get_alert.call_args_list == [
        ((4, "recovery_system:provider_timeout"), {}),
        ((4, "recovery_system:provider_timeout"), {}),
    ]


def test_existing_failed_base_cycle_allocates_retry_one():
    session = Mock()
    savepoint = Mock()
    savepoint.__enter__ = Mock(return_value=savepoint)
    savepoint.__exit__ = Mock(return_value=None)
    session.begin_nested.return_value = savepoint
    repository = DataGapRecoveryRepository(session)
    failed = SimpleNamespace(delivery_state=DataGapRecoveryAlertDeliveryState.FAILED)
    retry = SimpleNamespace(
        cycle_key="recovery_system:provider_timeout:retry:1",
        delivery_state=DataGapRecoveryAlertDeliveryState.PENDING,
    )
    get_alert = Mock(side_effect=[failed, None])
    record_alert = Mock(return_value=retry)
    setattr(repository, "get_alert", get_alert)
    setattr(repository, "record_alert", record_alert)

    alert, claimed = repository.claim_alert(4, "recovery_system:provider_timeout", {})

    assert alert is retry
    assert claimed is True
    assert record_alert.call_args.args[1] == "recovery_system:provider_timeout:retry:1"
