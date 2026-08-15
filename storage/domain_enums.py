from enum import StrEnum
from typing import Any


class BlackroomMarket(StrEnum):
    A = "A"
    HK = "HK"
    ETF = "ETF"


class BlackroomSource(StrEnum):
    MANUAL = "manual"
    SHAREHOLDER_SELLING = "shareholder_selling"
    SHAREHOLDER_REDUCTION = "shareholder_reduction"


class DailyBarDiagnosticAdjust(StrEnum):
    BFQ = "bfq"
    QFQ = "qfq"
    HFQ = "hfq"
    RAW = "raw"


class DailyBarDiagnosticClassification(StrEnum):
    MISSING_MARKET_DATA = "missing_market_data"
    MISSING_EXACT_DATE = "missing_exact_date"
    PROVIDER_ERROR = "provider_error"
    DOWNLOADED = "downloaded"
    RESOLVED = "resolved"


class ForecastSnapshotStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderOutcomeStatus(StrEnum):
    DOWNLOADED = "downloaded"
    EMPTY = "empty"
    ERROR = "error"


class SSFChangeSignalStatus(StrEnum):
    SIGNAL = "signal"
    NO_SIGNAL = "no_signal"


class SSFEventType(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NEW_ENTRY = "new_entry"
    EXIT = "exit"


def validate_provider_outcomes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("provider_outcomes must be a list")

    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("provider_outcomes items must be objects")
        try:
            status = ProviderOutcomeStatus(item["status"])
        except (KeyError, ValueError) as exc:
            raise ValueError("provider_outcomes items must have a valid status") from exc
        normalized.append({**item, "status": status.value})
    return normalized


def validate_ssf_event_types(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("event_types must be a list")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("event_types items must be strings")
        try:
            normalized.append(SSFEventType(item).value)
        except ValueError as exc:
            raise ValueError("event_types items must be valid event types") from exc
    return normalized
