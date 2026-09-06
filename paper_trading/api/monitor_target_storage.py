"""Manual-only storage adapter for the shared monitor target console."""

from __future__ import annotations

from typing import Any

from monitor.monitor_target_service import TargetValidationError


class ManualMonitorTargetStorage:
    """Expose the service's generic storage interface for manual targets only."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    def list_monitor_targets(
        self,
        *,
        frequency: str | None = None,
        enabled: bool | None = None,
        market: str | None = None,
        condition_type: str | None = None,
    ) -> list[Any]:
        return self._storage.list_manual_monitor_targets(
            frequency=frequency,
            enabled=enabled,
            market=market,
            condition_type=condition_type,
        )

    def get_monitor_target(self, target_id: int) -> Any | None:
        return self._storage.get_manual_monitor_target(target_id)

    def create_monitor_target(
        self,
        stock_code: str,
        market: str,
        condition: dict[str, Any],
        note: str | None = None,
        frequency: str = "daily",
        reset_mode: str = "auto",
        enabled: bool = True,
        last_state: bool = False,
    ) -> Any:
        if condition.get("workflow") is not None:
            raise TargetValidationError("workflow-owned targets cannot be created here")
        return self._storage.create_manual_monitor_target(
            stock_code=stock_code,
            market=market,
            condition=condition,
            note=note,
            frequency=frequency,
            reset_mode=reset_mode,
            enabled=enabled,
            last_state=last_state,
        )

    def update_monitor_target(self, target_id: int, **updates: Any) -> Any | None:
        condition = updates.get("condition")
        if isinstance(condition, dict) and condition.get("workflow") is not None:
            raise TargetValidationError("workflow-owned targets cannot be updated here")
        return self._storage.update_manual_monitor_target(target_id, **updates)

    def delete_monitor_target(self, target_id: int) -> bool:
        return self._storage.delete_manual_monitor_target(target_id)
