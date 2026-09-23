import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dags")))

from common_dags import (  # noqa: E402
    get_default_args,
    get_partition_count,
    get_partition_ids,
    run_partition_items,
)

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


def test_get_partition_count_uses_download_process_count(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", "6")

    assert get_partition_count() == 6
    assert list(get_partition_ids()) == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("download_process_count", ["0", "-1"])
def test_get_partition_count_normalizes_non_positive_values(monkeypatch, download_process_count):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", download_process_count)

    assert get_partition_count() == 1
    assert list(get_partition_ids()) == [0]


def test_get_partition_count_falls_back_to_default_when_missing(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_PROCESS_COUNT", raising=False)

    assert get_partition_count() == 4
    assert list(get_partition_ids()) == [0, 1, 2, 3]


def test_get_partition_count_ignores_airflow_variable_when_env_missing(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_PROCESS_COUNT", raising=False)

    airflow_module = types.ModuleType("airflow")
    airflow_models_module = types.ModuleType("airflow.models")

    class Variable:
        @staticmethod
        def get(name, default_var=None):
            return "9"

    setattr(airflow_models_module, "Variable", Variable)
    setattr(airflow_module, "models", airflow_models_module)
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.models", airflow_models_module)

    assert get_partition_count() == 4
    assert list(get_partition_ids()) == [0, 1, 2, 3]


def test_dags_use_airflow_sdk_skip_exception_imports():
    dag_sources = list(DAGS_DIR.glob("*.py"))

    assert dag_sources
    for dag_source in dag_sources:
        source = dag_source.read_text()
        assert "from airflow.exceptions import AirflowSkipException" not in source
        if "AirflowSkipException" in source:
            assert "from airflow.sdk.exceptions import AirflowSkipException" in source


def test_default_args_use_smtp_notifier_only_when_alert_emails_exist(monkeypatch):
    source = (DAGS_DIR / "common_dags.py").read_text()

    assert "email_on_failure" not in source
    assert "email_on_retry" not in source
    assert "email_on_success" not in source
    assert '"email":' not in source
    assert "SmtpNotifier" in source

    notifier_module = types.ModuleType("airflow.providers.smtp.notifications.smtp")

    class FakeSmtpNotifier:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    setattr(notifier_module, "SmtpNotifier", FakeSmtpNotifier)
    monkeypatch.setitem(sys.modules, "airflow.providers.smtp.notifications.smtp", notifier_module)
    monkeypatch.setenv("ALERT_EMAILS", "first@example.com; second@example.com")

    default_args = get_default_args()

    assert "email" not in default_args
    assert "email_on_failure" not in default_args
    assert "email_on_retry" not in default_args
    assert "email_on_success" not in default_args
    assert len(default_args["on_failure_callback"]) == 1
    assert default_args["on_failure_callback"][0].kwargs["to"] == ["first@example.com", "second@example.com"]


def test_default_args_do_not_enable_smtp_notifier_without_alert_emails(monkeypatch):
    monkeypatch.delenv("ALERT_EMAILS", raising=False)
    monkeypatch.delenv("MAIL_RECEIVERS", raising=False)

    default_args = get_default_args()

    assert "on_failure_callback" not in default_args


def test_run_partition_items_runs_selected_items_and_reports_failures():
    calls = []
    progress = []

    def action(item):
        calls.append(item)
        return f"result-{item}"

    selected, failures = run_partition_items(
        ["a", "b", "c", "d", "e"],
        partition_index=1,
        partition_count=2,
        action=action,
        is_failure=lambda result: result.endswith(("b", "e")),
        on_progress=lambda item, completed, total: progress.append((item, completed, total)),
    )

    assert selected == ["b", "d"]
    assert calls == ["b", "d"]
    assert failures == [("b", "result-b")]
    assert progress == [("b", 1, 2), ("d", 2, 2)]


def test_run_partition_items_empty_selection_does_nothing():
    calls: list[str] = []
    progress: list[tuple[str, int, int]] = []

    result = run_partition_items(
        ["a"],
        1,
        2,
        calls.append,
        lambda outcome: True,
        lambda item, completed, total: progress.append((item, completed, total)),
    )

    assert result == ([], [])
    assert calls == []
    assert progress == []


def test_run_partition_items_does_not_suppress_action_exception():
    def action(_item):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_partition_items(["a"], 0, 1, action, lambda _outcome: False)


def test_run_partition_items_does_not_suppress_is_failure_exception():
    def is_failure(_outcome):
        raise ValueError("classification failed")

    with pytest.raises(ValueError, match="classification failed"):
        run_partition_items(["a"], 0, 1, lambda _item: "result", is_failure)


def test_run_partition_items_does_not_suppress_on_progress_exception():
    def on_progress(_item, _completed, _total):
        raise LookupError("progress failed")

    with pytest.raises(LookupError, match="progress failed"):
        run_partition_items(["a"], 0, 1, lambda _item: "result", lambda _outcome: False, on_progress)
