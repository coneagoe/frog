import pytest
from types import SimpleNamespace

# The tests now exercise the shared runner contract. Importing the runner
# module is expected to fail for Task 1 (module not implemented yet).
from common.obos_hk_runner import ObosHkSkip, run_obos_hk_backtest


def test_skip_when_redis_not_success(monkeypatch):
    def fake_run(*a, **k):
        raise ObosHkSkip("download result is fail")

    monkeypatch.setattr("common.obos_hk_runner.run_obos_hk_backtest", fake_run)

    with pytest.raises(ObosHkSkip):
        run_obos_hk_backtest()


def test_success_email_path(monkeypatch):
    def fake_run(*a, **k):
        return SimpleNamespace(status="success", email_subject="obos_hk_2024-11-01", email_body="OK")

    monkeypatch.setattr("common.obos_hk_runner.run_obos_hk_backtest", fake_run)

    res = run_obos_hk_backtest()
    assert res.status == "success"
    assert "obos_hk_2024-11-01" in res.email_subject
    assert "OK" in res.email_body


def test_subprocess_failure_path(monkeypatch):
    def fake_run(*a, **k):
        return SimpleNamespace(status="failed", error="some error", email_body="Backtest failed with error: some error")

    monkeypatch.setattr("common.obos_hk_runner.run_obos_hk_backtest", fake_run)

    res = run_obos_hk_backtest()
    assert res.status == "failed"
    assert "some error" in res.error
    assert "Backtest failed with error: some error" in res.email_body
