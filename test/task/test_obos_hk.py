import importlib
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import celery_config  # noqa: E402

obos_hk_module = importlib.import_module("task.obos_hk")


class FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


def test_obos_hk_skips_when_redis_result_missing(monkeypatch):
    monkeypatch.setattr(obos_hk_module.conf, "parse_config", lambda: None)
    monkeypatch.setattr(
        obos_hk_module,
        "get_redis_client",
        lambda: FakeRedis(None),
    )
    monkeypatch.setattr(obos_hk_module, "is_hk_market_open_today", lambda: True)
    subprocess_calls = []
    monkeypatch.setattr(
        obos_hk_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_calls.append((args, kwargs)),
    )

    result = obos_hk_module.obos_hk.run()

    assert result == "Skip: missing Redis download result."
    assert subprocess_calls == []


def test_obos_hk_skips_when_redis_result_is_not_from_today(monkeypatch):
    stale_day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setattr(obos_hk_module.conf, "parse_config", lambda: None)
    monkeypatch.setattr(
        obos_hk_module,
        "get_redis_client",
        lambda: FakeRedis(f'{{"date":"{stale_day}","result":"success"}}'),
    )
    monkeypatch.setattr(obos_hk_module, "is_hk_market_open_today", lambda: True)
    subprocess_calls = []
    monkeypatch.setattr(
        obos_hk_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_calls.append((args, kwargs)),
    )

    result = obos_hk_module.obos_hk.run()

    assert result == f"Skip: Redis download result date is {stale_day}"
    assert subprocess_calls == []


def test_obos_hk_runs_when_redis_result_is_success_for_today(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    monkeypatch.setattr(obos_hk_module.conf, "parse_config", lambda: None)
    monkeypatch.setattr(
        obos_hk_module,
        "get_redis_client",
        lambda: FakeRedis(f'{{"date":"{today}","result":"success"}}'),
    )
    monkeypatch.setattr(obos_hk_module, "is_hk_market_open_today", lambda: True)
    monkeypatch.setattr(
        obos_hk_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    sent_emails = []
    monkeypatch.setattr(
        obos_hk_module,
        "send_email",
        lambda **kwargs: sent_emails.append(kwargs),
    )

    result = obos_hk_module.obos_hk.run()

    assert result == "Backtest success."
    assert sent_emails[0]["body"] == "ok"


def test_celery_beat_does_not_schedule_obos_hk_directly():
    assert "obos_hk" not in celery_config.beat_schedule


def test_hk_ggt_dag_checks_hk_market_calendar():
    source = (
        Path(__file__).resolve().parents[2]
        / "dags"
        / "download_hk_ggt_history_daily.py"
    ).read_text(encoding="utf-8")

    assert "from common import is_hk_market_open_today" in source
    assert "if not is_hk_market_open_today():" in source
