import re
from collections.abc import Mapping

from monitor.domain_enums import MonitorEvaluationErrorKind

MONITOR_ERROR_SUMMARIES: Mapping[MonitorEvaluationErrorKind, str] = {
    MonitorEvaluationErrorKind.MARKET_DATA: "Market data unavailable",
    MonitorEvaluationErrorKind.CONDITION: "Condition evaluation failed",
    MonitorEvaluationErrorKind.WORKFLOW_GUARD: "Workflow safety check failed",
    MonitorEvaluationErrorKind.NOTIFICATION: "Alert delivery failed",
    MonitorEvaluationErrorKind.STORAGE: "Monitor state persistence failed",
    MonitorEvaluationErrorKind.UNKNOWN: "Monitor evaluation failed",
}

_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\bbearer\s+\S+", re.IGNORECASE)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:\b|[\"'])(?:x-api-key|token|api[_-]?token|api[_-]?key|access[_-]?token|secret|password|authorization)(?:\b|[\"'])\s*(?:=|:)\s*(?:\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)
_POSIX_PATH_PATTERN = re.compile(r"(?:~|/)[^\s\"']+(?:\s+(?:[^\s\"']*[\\/][^\s\"']*|[^\s\"']+\.[^\s\"']+))*")
_WINDOWS_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\[^\r\n\"']+")
_TRACEBACK_PATTERN = re.compile(r"traceback \(most recent call last\):?", re.IGNORECASE)
_STACK_FRAME_PATTERN = re.compile(r"File\s+[\"'][^\"']+[\"'],\s*line\s+\d+(?:,\s*in\s+\S+)?", re.IGNORECASE)
_EXCEPTION_PREFIX_PATTERN = re.compile(
    r"^(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception|Failure):\s*",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize_error_detail(value: object, max_length: int = 240) -> str | None:
    """Return a concise error detail without credentials, paths, or traceback markers."""
    detail = str(value)
    detail = _URL_PATTERN.sub("[redacted]", detail)
    detail = _BEARER_PATTERN.sub("[redacted]", detail)
    detail = _SECRET_VALUE_PATTERN.sub("[redacted]", detail)
    detail = _STACK_FRAME_PATTERN.sub("", detail)
    detail = _POSIX_PATH_PATTERN.sub("[path]", detail)
    detail = _WINDOWS_PATH_PATTERN.sub("[path]", detail)
    detail = _TRACEBACK_PATTERN.sub("", detail)
    detail = _EXCEPTION_PREFIX_PATTERN.sub("", detail)
    detail = " ".join(detail.split())
    if not detail or max_length <= 0:
        return None
    if max_length < len(detail):
        if max_length <= 3:
            return detail[:max_length]
        return f"{detail[: max(0, max_length - 3)]}..."
    return detail
