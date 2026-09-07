import pytest

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


@pytest.mark.parametrize(
    ("max_length", "expected"),
    [(0, None), (1, "a"), (2, "ab"), (3, "abc"), (6, "abc...")],
)
def test_sanitizer_never_exceeds_requested_max_length(max_length, expected):
    detail = sanitize_error_detail("abcdefg", max_length=max_length)
    assert detail == expected
    assert detail is None or len(detail) <= max_length


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com:bad/path?token=x#fragment-secret",
        "https://[invalid/path?api_key=x#fragment-secret",
    ],
)
def test_sanitizer_conservatively_redacts_malformed_url_sensitive_content(raw):
    detail = sanitize_error_detail(raw)
    assert detail is not None
    for sensitive in ("token", "api_key", "x", "fragment-secret"):
        assert sensitive not in detail


def test_sanitizer_redacts_url_fragment():
    detail = sanitize_error_detail("https://example.com/path#fragment-secret")
    assert detail is not None
    assert "fragment-secret" not in detail
    assert "[redacted]" in detail
