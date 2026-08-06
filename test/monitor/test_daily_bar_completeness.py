from datetime import date
from unittest.mock import MagicMock

import pytest

from monitor import daily_bar_completeness as completeness


def test_non_trading_day_returns_skip_result(monkeypatch):
    redis_client = MagicMock()
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: False)

    result = completeness.verify_daily_bar_completeness(date(2026, 8, 8), redis_client=redis_client)

    assert result == {
        "trade_date": "2026-08-08",
        "is_trading_day": False,
        "complete": False,
        "status": "skipped",
    }
    redis_client.get.assert_not_called()


def test_complete_trading_day_returns_success(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = '{"date":"2026-08-06","result":"success","status":"success","missing_symbols":[]}'
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)

    result = completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)

    assert result == {
        "trade_date": "2026-08-06",
        "is_trading_day": True,
        "complete": True,
        "status": "success",
    }
    redis_client.get.assert_called_once_with(completeness.REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY)


class FalseyRedisClient:
    def __init__(self, result):
        self.result = result
        self.keys = []

    def __bool__(self):
        return False

    def get(self, key):
        self.keys.append(key)
        return self.result


def test_falsey_injected_redis_client_is_used(monkeypatch):
    redis_client = FalseyRedisClient('{"date":"2026-08-06","result":"success","status":"success","missing_symbols":[]}')
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)
    monkeypatch.setattr(completeness, "_get_redis_client", lambda: pytest.fail("used default Redis client"))

    completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)

    assert redis_client.keys == [completeness.REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY]


@pytest.mark.parametrize(
    "raw_result",
    [
        None,
        "not valid JSON",
        '{"date":"2026-08-05","result":"success","status":"success","missing_symbols":[]}',
        '{"date":"2026-08-06","result":"failed","status":"success","missing_symbols":[]}',
        '{"date":"2026-08-06","result":"success","status":"failed","missing_symbols":[]}',
        '{"date":"2026-08-06","result":"success","status":"success","missing_symbols":["600001"]}',
    ],
    ids=["missing", "malformed", "stale", "failed_result", "failed_status", "missing_symbols"],
)
def test_invalid_trading_day_aggregate_raises_with_provider_evidence(monkeypatch, raw_result):
    redis_client = MagicMock()
    redis_client.get.return_value = raw_result
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)

    with pytest.raises(RuntimeError, match="daily bars incomplete"):
        completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)
