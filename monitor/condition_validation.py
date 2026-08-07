from collections.abc import Mapping
from typing import Any


def validate_condition(condition: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(condition, Mapping):
        raise ValueError("condition must be a JSON object")

    normalized = dict(condition)
    condition_type = normalized.get("type")
    if condition_type == "price_threshold":
        _validate_direction(normalized, {"above", "below"})
        _required_number(normalized, "value")
    elif condition_type == "ma_cross":
        _validate_direction(normalized, {"golden", "death"})
        fast = _required_positive_int(normalized, "fast")
        slow = _required_positive_int(normalized, "slow")
        if fast >= slow:
            raise ValueError("condition.fast must be less than condition.slow")
    elif condition_type == "change_pct":
        _validate_direction(normalized, {"above", "below"})
        _required_number(normalized, "value")
    elif condition_type in {"price_cross_ma", "price_vs_ma"}:
        _validate_direction(normalized, {"above", "below"})
        _required_positive_int(normalized, "period")
    elif condition_type == "rsi":
        _validate_direction(normalized, {"above", "below"})
        normalized.setdefault("period", 14)
        _required_positive_int(normalized, "period")
        value = _required_number(normalized, "value")
        if not 0 <= value <= 100:
            raise ValueError("condition.value must be between 0 and 100")
    else:
        raise ValueError(f"condition.type unsupported: {condition_type!r}")
    return normalized


def _validate_direction(condition: Mapping[str, Any], allowed: set[str]) -> None:
    if condition.get("direction") not in allowed:
        raise ValueError("condition.direction is invalid")


def _required_number(condition: Mapping[str, Any], field: str) -> int | float:
    value = condition.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"condition.{field} must be a number")
    return value


def _required_positive_int(condition: Mapping[str, Any], field: str) -> int:
    value = condition.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"condition.{field} must be a positive integer")
    return value
