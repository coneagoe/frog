from datetime import date
from unittest.mock import MagicMock

import pytest

from monitor import daily_bar_completeness as completeness


def test_non_trading_day_returns_skip_result(monkeypatch):
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: False)

    result = completeness.verify_daily_bar_completeness(date(2026, 8, 8), redis_client=MagicMock())

    assert result == {
        "trade_date": "2026-08-08",
        "is_trading_day": False,
        "complete": False,
        "status": "skipped",
    }


def test_complete_trading_day_returns_success(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = '{"date":"2026-08-06","result":"success","status":"success","missing_symbols":[]}'
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)

    result = completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)

    assert result["complete"] is True
    assert result["trade_date"] == "2026-08-06"


def test_incomplete_trading_day_raises_before_workflow_mutation(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = (
        '{"date":"2026-08-06","result":"success","status":"warning",'
        '"missing_symbols":["600001"]}'
    )
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)

    with pytest.raises(RuntimeError, match="daily bars incomplete"):
        completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)
