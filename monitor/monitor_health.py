import re
from collections.abc import Mapping
from urllib.parse import urlsplit

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
_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:token|api_token|api_key|access_token|secret|password|authorization)\s*=\s*\S+",
    re.IGNORECASE,
)
_POSIX_PATH_PATTERN = re.compile(r"(?:~|/)[^\s\"']+")
_WINDOWS_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\[^\s\"']+")
_TRACEBACK_PATTERN = re.compile(r"traceback \(most recent call last\):?", re.IGNORECASE)


def _sanitize_url(match: re.Match[str]) -> str:
    try:
        urlsplit(match.group())
    except ValueError:
        pass
    return "[redacted]"


def sanitize_error_detail(value: object, max_length: int = 240) -> str | None:
    """Return a concise error detail without credentials, paths, or traceback markers."""
    detail = str(value)
    detail = _URL_PATTERN.sub(_sanitize_url, detail)
    detail = _BEARER_PATTERN.sub("[redacted]", detail)
    detail = _ASSIGNMENT_PATTERN.sub("[redacted]", detail)
    detail = _POSIX_PATH_PATTERN.sub("[path]", detail)
    detail = _WINDOWS_PATH_PATTERN.sub("[path]", detail)
    detail = _TRACEBACK_PATTERN.sub("", detail)
    detail = " ".join(detail.split())
    if not detail or max_length <= 0:
        return None
    if max_length < len(detail):
        if max_length <= 3:
            return detail[:max_length]
        return f"{detail[: max(0, max_length - 3)]}..."
    return detail
