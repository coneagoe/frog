"""Verify that the daily stock-bar download completed for a trade date."""

import json
import os
from datetime import date
from typing import Any

import redis

from common.const import DEFAULT_REDIS_URL, REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY
from stock.market import is_a_share_trade_date


def _get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(os.getenv("REDIS_URL", DEFAULT_REDIS_URL), decode_responses=True)


def verify_daily_bar_completeness(as_of_date: date, redis_client: Any = None) -> dict[str, Any]:
    """Return completeness for a date, or raise when a trading-day aggregate is invalid."""
    trade_date = as_of_date.isoformat()
    if not is_a_share_trade_date(as_of_date):
        return {
            "trade_date": trade_date,
            "is_trading_day": False,
            "complete": False,
            "status": "skipped",
        }

    client = _get_redis_client() if redis_client is None else redis_client
    raw_result = client.get(REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY)
    evidence: Any = raw_result
    try:
        if not isinstance(raw_result, str) or not raw_result:
            raise ValueError("missing Redis aggregate")
        evidence = json.loads(raw_result)
        if not isinstance(evidence, dict):
            raise ValueError("aggregate is not a JSON object")
        if (
            evidence.get("date") != trade_date
            or evidence.get("result") != "success"
            or evidence.get("status") != "success"
            or evidence.get("missing_symbols") != []
        ):
            raise ValueError("aggregate does not confirm complete daily bars")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"daily bars incomplete for {trade_date}: {evidence!r}") from exc

    return {
        "trade_date": trade_date,
        "is_trading_day": True,
        "complete": True,
        "status": "success",
    }
