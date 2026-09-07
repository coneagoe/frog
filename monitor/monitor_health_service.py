from enum import StrEnum
from typing import Any

from monitor.domain_enums import MonitorEvaluationErrorKind
from monitor.monitor_health import MONITOR_ERROR_SUMMARIES
from storage import get_storage


class MonitorOperationalState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    DISABLED = "disabled"


class MonitorTargetHealthService:
    def __init__(self, storage: Any = None):
        self.storage = storage or get_storage()

    @staticmethod
    def _operational_state(target: Any) -> MonitorOperationalState:
        if not target.enabled:
            return MonitorOperationalState.DISABLED
        if target.paused:
            return MonitorOperationalState.PAUSED
        return MonitorOperationalState.RUNNING

    @staticmethod
    def _latest_error(target: Any) -> dict[str, Any] | None:
        if target.latest_error_kind is None or target.latest_error_at is None:
            return None
        try:
            kind = MonitorEvaluationErrorKind(target.latest_error_kind)
        except ValueError:
            kind = MonitorEvaluationErrorKind.UNKNOWN
            detail = None
        else:
            detail = target.latest_error_detail
        return {
            "kind": kind,
            "summary": MONITOR_ERROR_SUMMARIES[kind],
            "detail": detail,
            "occurred_at": target.latest_error_at,
        }

    def _serialize_target(self, target: Any) -> dict[str, Any]:
        return {
            "id": target.id,
            "stock_code": target.stock_code,
            "market": target.market,
            "frequency": target.frequency,
            "workflow": target.workflow,
            "enabled": target.enabled,
            "paused": target.paused,
            "operational_state": self._operational_state(target),
            "last_state": target.last_state,
            "last_checked_at": target.last_checked_at,
            "triggered_at": target.triggered_at,
            "latest_error": self._latest_error(target),
        }

    def get_health(self) -> dict[str, Any]:
        summary = {"total": 0, "running": 0, "paused": 0, "disabled": 0, "triggered": 0, "daily": 0, "intraday": 0}
        targets = []
        for target in self.storage.list_monitor_target_health():
            serialized = self._serialize_target(target)
            targets.append(serialized)
            summary["total"] += 1
            summary[serialized["operational_state"]] += 1
            if target.last_state:
                summary["triggered"] += 1
            summary[target.frequency] += 1
        return {"summary": summary, "targets": targets}


def get_monitor_target_health_service() -> MonitorTargetHealthService:
    return MonitorTargetHealthService(storage=get_storage())
