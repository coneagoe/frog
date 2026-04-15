"""Service layer for monitor target management with validation and stable payloads."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from storage import get_storage


class TargetValidationError(ValueError):
    """Raised when monitor target input is invalid."""


class TargetNotFoundError(LookupError):
    """Raised when monitor target cannot be found."""


class TargetManagementService:
    _ALLOWED_MARKETS = {"A", "HK", "ETF"}
    _ALLOWED_FREQUENCY = {"daily", "intraday"}
    _ALLOWED_RESET_MODE = {"auto", "manual"}
    _ALLOWED_UPDATE_FIELDS = {
        "stock_code",
        "market",
        "condition",
        "note",
        "frequency",
        "reset_mode",
        "enabled",
        "last_state",
        "triggered_at",
    }

    def __init__(self, storage: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage

    def add_target(
        self,
        stock_code: str,
        market: str,
        condition: dict[str, Any] | str,
        note: Optional[str] = None,
        frequency: str = "daily",
        reset_mode: str = "auto",
        enabled: bool = True,
        last_state: bool = False,
    ) -> dict[str, Any]:
        try:
            parsed_condition = self._parse_and_validate_condition(condition)
            self._validate_stock_code(stock_code)
            self._validate_market(market)
            self._validate_frequency(frequency)
            self._validate_reset_mode(reset_mode)
            self._validate_bool(enabled, "enabled")
            self._validate_bool(last_state, "last_state")
            target = self.storage.create_monitor_target(
                stock_code=stock_code,
                market=market,
                condition=parsed_condition,
                note=note,
                frequency=frequency,
                reset_mode=reset_mode,
                enabled=enabled,
                last_state=last_state,
            )
            return self._result(
                True, "OK", "target created", self._serialize_target(target)
            )
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    def update_target(self, target_id: int, **updates: Any) -> dict[str, Any]:
        try:
            self._validate_target_id(target_id)
            if not updates:
                raise TargetValidationError("至少需要一个更新字段")

            invalid_fields = set(updates) - self._ALLOWED_UPDATE_FIELDS
            if invalid_fields:
                raise TargetValidationError(f"不支持更新字段: {sorted(invalid_fields)}")

            if "stock_code" in updates:
                self._validate_stock_code(updates["stock_code"])
            if "market" in updates:
                self._validate_market(updates["market"])
            if "condition" in updates:
                updates["condition"] = self._parse_and_validate_condition(
                    updates["condition"]
                )
            if "frequency" in updates:
                self._validate_frequency(updates["frequency"])
            if "reset_mode" in updates:
                self._validate_reset_mode(updates["reset_mode"])
            if "enabled" in updates:
                self._validate_bool(updates["enabled"], "enabled")
            if "last_state" in updates:
                self._validate_bool(updates["last_state"], "last_state")
            if (
                "triggered_at" in updates
                and updates["triggered_at"] is not None
                and not isinstance(updates["triggered_at"], datetime)
            ):
                raise TargetValidationError("triggered_at 必须是 datetime 或 None")

            target = self.storage.update_monitor_target(target_id, **updates)
            if target is None:
                raise TargetNotFoundError(f"monitor target not found: {target_id}")
            return self._result(
                True, "OK", "target updated", self._serialize_target(target)
            )
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except TargetNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    def remove_target(self, target_id: int) -> dict[str, Any]:
        try:
            self._validate_target_id(target_id)
            deleted = self.storage.delete_monitor_target(target_id)
            if not deleted:
                raise TargetNotFoundError(f"monitor target not found: {target_id}")
            return self._result(
                True, "OK", "target deleted", {"id": target_id, "deleted": True}
            )
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except TargetNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    def get_target(self, target_id: int) -> dict[str, Any]:
        try:
            self._validate_target_id(target_id)
            target = self.storage.get_monitor_target(target_id)
            if target is None:
                raise TargetNotFoundError(f"monitor target not found: {target_id}")
            return self._result(
                True, "OK", "target fetched", self._serialize_target(target)
            )
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except TargetNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    def get(self, target_id: int) -> dict[str, Any]:
        return self.get_target(target_id)

    def list_targets(
        self, frequency: Optional[str] = None, enabled: Optional[bool] = None
    ) -> dict[str, Any]:
        try:
            if frequency is not None:
                self._validate_frequency(frequency)
            if enabled is not None:
                self._validate_bool(enabled, "enabled")
            targets = self.storage.list_monitor_targets(
                frequency=frequency, enabled=enabled
            )
            data = [self._serialize_target(target) for target in targets]
            return self._result(True, "OK", "targets listed", data)
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    def list(
        self, frequency: Optional[str] = None, enabled: Optional[bool] = None
    ) -> dict[str, Any]:
        return self.list_targets(frequency=frequency, enabled=enabled)

    def update(self, target_id: int, **updates: Any) -> dict[str, Any]:
        return self.update_target(target_id, **updates)

    def remove(self, target_id: int) -> dict[str, Any]:
        return self.remove_target(target_id)

    def get_status(self) -> dict[str, Any]:
        targets = self.storage.list_monitor_targets(frequency=None, enabled=None)
        data = {
            "total": len(targets),
            "enabled": sum(
                1 for target in targets if getattr(target, "enabled", False)
            ),
            "disabled": sum(
                1 for target in targets if not getattr(target, "enabled", False)
            ),
            "triggered": sum(
                1 for target in targets if getattr(target, "last_state", False)
            ),
            "daily": sum(
                1 for target in targets if getattr(target, "frequency", None) == "daily"
            ),
            "intraday": sum(
                1
                for target in targets
                if getattr(target, "frequency", None) == "intraday"
            ),
        }
        return self._result(True, "OK", "status fetched", data)

    def set_target_status(self, target_id: int, enabled: bool) -> dict[str, Any]:
        try:
            self._validate_target_id(target_id)
            self._validate_bool(enabled, "enabled")
            target = self.storage.update_monitor_target(target_id, enabled=enabled)
            if target is None:
                raise TargetNotFoundError(f"monitor target not found: {target_id}")
            return self._result(
                True, "OK", "target status updated", self._serialize_target(target)
            )
        except TargetValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except TargetNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    @staticmethod
    def _result(success: bool, code: str, message: str, data: Any) -> dict[str, Any]:
        return {
            "success": success,
            "code": code,
            "message": message,
            "data": data,
        }

    @staticmethod
    def _validate_target_id(target_id: Any) -> None:
        if type(target_id) is not int or target_id <= 0:
            raise TargetValidationError("target_id 必须是正整数")

    @staticmethod
    def _validate_bool(value: Any, field_name: str) -> None:
        if not isinstance(value, bool):
            raise TargetValidationError(f"{field_name} 必须是布尔值")

    @staticmethod
    def _validate_stock_code(stock_code: Any) -> None:
        if not isinstance(stock_code, str) or not stock_code.strip():
            raise TargetValidationError("stock_code 不能为空")

    def _validate_market(self, market: Any) -> None:
        if not isinstance(market, str) or market not in self._ALLOWED_MARKETS:
            raise TargetValidationError(
                f"market 必须是 {sorted(self._ALLOWED_MARKETS)} 之一"
            )

    def _validate_frequency(self, frequency: Any) -> None:
        if not isinstance(frequency, str) or frequency not in self._ALLOWED_FREQUENCY:
            raise TargetValidationError(
                f"frequency 必须是 {sorted(self._ALLOWED_FREQUENCY)} 之一"
            )

    def _validate_reset_mode(self, reset_mode: Any) -> None:
        if (
            not isinstance(reset_mode, str)
            or reset_mode not in self._ALLOWED_RESET_MODE
        ):
            raise TargetValidationError(
                f"reset_mode 必须是 {sorted(self._ALLOWED_RESET_MODE)} 之一"
            )

    def _parse_and_validate_condition(
        self, condition: dict[str, Any] | str
    ) -> dict[str, Any]:
        parsed = condition
        if isinstance(condition, str):
            try:
                parsed = json.loads(condition)
            except json.JSONDecodeError as exc:
                raise TargetValidationError("condition 不是合法JSON") from exc

        if not isinstance(parsed, dict):
            raise TargetValidationError("condition 必须是JSON对象")

        self._validate_condition_rules(parsed)
        return parsed

    @staticmethod
    def _expect_numeric(condition: dict[str, Any], field_name: str) -> float:
        value = condition.get(field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TargetValidationError(f"condition.{field_name} 必须是数字")
        return float(value)

    @staticmethod
    def _expect_int(condition: dict[str, Any], field_name: str) -> int:
        value = condition.get(field_name)
        if type(value) is not int or value <= 0:
            raise TargetValidationError(f"condition.{field_name} 必须是正整数")
        return value

    def _validate_condition_rules(self, condition: dict[str, Any]) -> None:
        ctype = condition.get("type")
        if not isinstance(ctype, str):
            raise TargetValidationError("condition.type 必须是字符串")

        if ctype == "price_threshold":
            self._validate_direction(condition.get("direction"), {"above", "below"})
            self._expect_numeric(condition, "value")
            return

        if ctype == "change_pct":
            self._validate_direction(condition.get("direction"), {"above", "below"})
            self._expect_numeric(condition, "value")
            return

        if ctype == "price_cross_ma":
            self._validate_direction(condition.get("direction"), {"above", "below"})
            self._expect_int(condition, "period")
            return

        if ctype == "ma_cross":
            self._validate_direction(condition.get("direction"), {"golden", "death"})
            fast = self._expect_int(condition, "fast")
            slow = self._expect_int(condition, "slow")
            if fast >= slow:
                raise TargetValidationError("condition.fast 必须小于 condition.slow")
            return

        if ctype == "rsi":
            self._validate_direction(condition.get("direction"), {"above", "below"})
            period = condition.get("period", 14)
            if type(period) is not int or period <= 0:
                raise TargetValidationError("condition.period 必须是正整数")
            value = self._expect_numeric(condition, "value")
            if value < 0 or value > 100:
                raise TargetValidationError("condition.value 必须在 0 到 100 之间")
            return

        raise TargetValidationError(f"condition.type 不支持: {ctype}")

    @staticmethod
    def _validate_direction(direction: Any, allowed: set[str]) -> None:
        if not isinstance(direction, str) or direction not in allowed:
            raise TargetValidationError(
                f"condition.direction 必须是 {sorted(allowed)} 之一"
            )

    @staticmethod
    def _serialize_target(target: Any) -> dict[str, Any]:
        return {
            "id": getattr(target, "id", None),
            "stock_code": getattr(target, "stock_code", None),
            "market": getattr(target, "market", None),
            "condition": getattr(target, "condition", None),
            "note": getattr(target, "note", None),
            "frequency": getattr(target, "frequency", None),
            "reset_mode": getattr(target, "reset_mode", None),
            "enabled": getattr(target, "enabled", None),
            "last_state": getattr(target, "last_state", None),
            "triggered_at": TargetManagementService._to_iso(
                getattr(target, "triggered_at", None)
            ),
            "created_at": TargetManagementService._to_iso(
                getattr(target, "created_at", None)
            ),
        }

    @staticmethod
    def _to_iso(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value
