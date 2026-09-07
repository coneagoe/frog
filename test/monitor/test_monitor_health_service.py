from datetime import datetime, timezone
from types import SimpleNamespace

from monitor.domain_enums import MonitorEvaluationErrorKind
from monitor.monitor_health import MONITOR_ERROR_SUMMARIES
from monitor.monitor_health_service import MonitorOperationalState, MonitorTargetHealthService


def _target(target_id: int, **updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": target_id,
        "stock_code": "600519",
        "market": "A",
        "frequency": "daily",
        "workflow": "scheduled",
        "enabled": True,
        "paused": False,
        "last_state": False,
        "last_checked_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "triggered_at": None,
        "latest_error_kind": None,
        "latest_error_detail": None,
        "latest_error_at": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


class FakeStorage:
    def __init__(self, targets: list[SimpleNamespace]):
        self.targets = targets

    def list_monitor_target_health(self) -> list[SimpleNamespace]:
        return self.targets


def test_get_health_derives_states_summary_and_safe_target_fields():
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(1, enabled=False, paused=True, last_state=True),
                _target(2, enabled=True, paused=True, last_state=False),
                _target(3, enabled=True, paused=False, last_state=False, frequency="intraday"),
            ]
        )
    )

    health = service.get_health()

    assert [target["operational_state"] for target in health["targets"]] == [
        MonitorOperationalState.DISABLED,
        MonitorOperationalState.PAUSED,
        MonitorOperationalState.RUNNING,
    ]
    assert health["summary"] == {
        "total": 3,
        "running": 1,
        "paused": 1,
        "disabled": 1,
        "triggered": 1,
        "daily": 2,
        "intraday": 1,
    }
    assert health["targets"][0]["workflow"] == "scheduled"
    assert {"condition", "note", "evidence"}.isdisjoint(health["targets"][0])


def test_get_health_serializes_valid_and_corrupt_latest_errors():
    occurred_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(1),
                _target(
                    2,
                    latest_error_kind=MonitorEvaluationErrorKind.MARKET_DATA.value,
                    latest_error_detail="provider timed out",
                    latest_error_at=occurred_at,
                ),
                _target(
                    3,
                    latest_error_kind="corrupt",
                    latest_error_detail="must not be exposed",
                    latest_error_at=occurred_at,
                ),
            ]
        )
    )

    targets = service.get_health()["targets"]

    assert targets[0]["latest_error"] is None
    assert targets[1]["latest_error"] == {
        "kind": MonitorEvaluationErrorKind.MARKET_DATA,
        "summary": MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.MARKET_DATA],
        "detail": "provider timed out",
        "occurred_at": occurred_at,
    }
    assert targets[2]["latest_error"] == {
        "kind": MonitorEvaluationErrorKind.UNKNOWN,
        "summary": MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.UNKNOWN],
        "detail": None,
        "occurred_at": occurred_at,
    }


def test_get_health_resanitizes_legacy_sensitive_valid_error_detail():
    occurred_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(
                    1,
                    latest_error_kind="storage",
                    latest_error_detail='ValueError: X-Api-Key: leaked https://example.com/x#fragment /srv/frog/a.py',
                    latest_error_at=occurred_at,
                )
            ]
        )
    )

    error = service.get_health()["targets"][0]["latest_error"]
    assert error["kind"] == MonitorEvaluationErrorKind.STORAGE
    assert error["summary"] == MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.STORAGE]
    for sensitive in ("ValueError:", "leaked", "example.com", "fragment", "/srv/frog/a.py"):
        assert sensitive not in (error["detail"] or "")
