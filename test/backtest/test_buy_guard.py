import os
import sys
from unittest.mock import MagicMock

import backtrader as bt
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backtest.buy_guard import (  # noqa: E402
    filter_explicit_buy_codes,
    should_block_positive_target,
)
from backtest.my_strategy import MyStrategy  # noqa: E402


def test_filter_explicit_buy_codes_prunes_banned_codes():
    service = MagicMock()
    service.filter.return_value = {
        "success": True,
        "data": {"allowed": ["000001", "000003"], "banned": ["000002"]},
    }

    allowed = filter_explicit_buy_codes(
        ["000001", "000002", "000003"], market="A", service=service
    )

    assert allowed == ["000001", "000003"]
    service.filter.assert_called_once_with(
        candidates=["000001", "000002", "000003"], market="A"
    )


def test_filter_explicit_buy_codes_raises_on_service_failure():
    service = MagicMock()
    service.filter.return_value = {
        "success": False,
        "code": "STORAGE_ERROR",
        "message": "service unavailable",
        "data": None,
    }

    with pytest.raises(RuntimeError, match="STORAGE_ERROR: service unavailable"):
        filter_explicit_buy_codes(["000001"], market="A", service=service)


def test_should_block_positive_target_blocks_banned_code():
    service = MagicMock()
    service.check.return_value = {
        "success": True,
        "data": {"stock_code": "000001", "market": "A", "banned": True},
    }

    blocked = should_block_positive_target(
        "000001", target=0.2, market="A", service=service
    )

    assert blocked is True
    service.check.assert_called_once_with(stock_code="000001", market="A")


def test_should_block_positive_target_ignores_non_positive_targets():
    service = MagicMock()

    assert (
        should_block_positive_target("000001", target=0.0, market="A", service=service)
        is False
    )
    assert (
        should_block_positive_target("000001", target=-0.1, market="A", service=service)
        is False
    )

    service.check.assert_not_called()


def test_my_strategy_order_target_percent_skips_banned_positive_target(monkeypatch):
    strategy = MyStrategy.__new__(MyStrategy)
    strategy.buy_guard_market = "A"
    data = type("Data", (), {"_name": "000001"})()

    parent_calls = []

    def _fake_parent(self, data=None, target=0.0, **kwargs):
        parent_calls.append((data, target, kwargs))
        return "delegated"

    monkeypatch.setattr(
        "backtest.my_strategy.should_block_positive_target",
        lambda stock_code, target, market: True,
    )
    monkeypatch.setattr(bt.Strategy, "order_target_percent", _fake_parent)

    result = MyStrategy.order_target_percent(strategy, data=data, target=0.2)

    assert result is None
    assert parent_calls == []


def test_my_strategy_order_target_percent_allows_zero_target(monkeypatch):
    strategy = MyStrategy.__new__(MyStrategy)
    strategy.buy_guard_market = "A"
    data = type("Data", (), {"_name": "000001"})()

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("buy guard should not run for non-positive targets")

    def _fake_parent(self, data=None, target=0.0, **kwargs):
        return {"data": data, "target": target, "kwargs": kwargs}

    monkeypatch.setattr(
        "backtest.my_strategy.should_block_positive_target", _should_not_be_called
    )
    monkeypatch.setattr(bt.Strategy, "order_target_percent", _fake_parent)

    result = MyStrategy.order_target_percent(strategy, data=data, target=0.0)

    assert result == {"data": data, "target": 0.0, "kwargs": {}}
