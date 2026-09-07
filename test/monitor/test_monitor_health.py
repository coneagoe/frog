from monitor.domain_enums import MonitorEvaluationErrorKind
from monitor.monitor_health import MONITOR_ERROR_SUMMARIES, sanitize_error_detail


def test_summaries_cover_all_error_kinds():
    assert MONITOR_ERROR_SUMMARIES == {
        MonitorEvaluationErrorKind.MARKET_DATA: "Market data unavailable",
        MonitorEvaluationErrorKind.CONDITION: "Condition evaluation failed",
        MonitorEvaluationErrorKind.WORKFLOW_GUARD: "Workflow safety check failed",
        MonitorEvaluationErrorKind.NOTIFICATION: "Alert delivery failed",
        MonitorEvaluationErrorKind.STORAGE: "Monitor state persistence failed",
        MonitorEvaluationErrorKind.UNKNOWN: "Monitor evaluation failed",
    }


def test_sanitizer_filters_then_truncates():
    raw = (
        "Bearer abc token=secret https://u:p@example.com/x?api_key=s "
        "/opt/frog/a.py C:\\frog\\a.ini "
        + "x" * 300
    )
    detail = sanitize_error_detail(raw)
    assert detail is not None and len(detail) <= 240 and detail.endswith("...")
    assert "[redacted]" in detail and "[path]" in detail
    for secret in ("abc", "secret", "api_key", "/opt/frog", "C:\\frog"):
        assert secret not in detail


def test_sanitizer_returns_none_for_blank_content():
    assert sanitize_error_detail(" \n\t") is None


def test_sanitizer_removes_unknown_exception_sensitive_content():
    raw = (
        "RuntimeError: Traceback (most recent call last): Bearer secret-token "
        'File "/opt/frog/monitor/runner.py", line 12'
    )
    detail = sanitize_error_detail(raw)
    assert detail is not None
    for sensitive in ("secret-token", "/opt/frog", "Traceback (most recent call last)"):
        assert sensitive not in detail
