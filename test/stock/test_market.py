import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import conf  # noqa: E402
from stock.market import (  # noqa: E402
    get_a_stock_trading_window,
    is_a_market_open,
    is_a_market_open_today,
    is_hk_market_open,
    is_market_open_now,
)

conf.parse_config()


class TestIsAMarketOpen(unittest.TestCase):
    def test_is_a_market_open(self):
        self.assertTrue(is_a_market_open("2025-04-10"))
        self.assertFalse(is_a_market_open("2025-04-12"))
        self.assertFalse(is_a_market_open("2025-04-13"))
        self.assertFalse(is_a_market_open("2025-01-29"))

    def test_is_a_market_open_requires_date(self):
        self.assertRaises(TypeError, is_a_market_open)

    def test_is_a_market_open_today_uses_is_a_market_open(self):
        with (
            patch("stock.market.datetime") as mock_datetime,
            patch(
                "stock.market.is_a_market_open",
                return_value=True,
            ) as mock_is_a_market_open,
        ):
            mock_datetime.now.return_value = datetime(2025, 4, 10, 10, 0)

            self.assertTrue(is_a_market_open_today())
            mock_is_a_market_open.assert_called_once_with("2025-04-10")

    def test_is_market_open_now_during_trading_session(self):
        with (
            patch("stock.market.datetime") as mock_datetime,
            patch(
                "stock.market.is_a_market_open",
                return_value=True,
            ),
        ):
            mock_datetime.now.return_value = datetime(2025, 4, 10, 10, 0)

            self.assertTrue(is_market_open_now())

    def test_is_market_open_now_after_close(self):
        with (
            patch("stock.market.datetime") as mock_datetime,
            patch(
                "stock.market.is_a_market_open",
                return_value=True,
            ),
        ):
            mock_datetime.now.return_value = datetime(2025, 4, 10, 15, 1)

            self.assertFalse(is_market_open_now())

    def test_is_market_open_now_on_holiday(self):
        with (
            patch("stock.market.datetime") as mock_datetime,
            patch(
                "stock.market.is_a_market_open",
                return_value=False,
            ),
        ):
            mock_datetime.now.return_value = datetime(2025, 1, 29, 10, 0)

            self.assertFalse(is_market_open_now())


class TestIsHkMarketOpen(unittest.TestCase):
    def test_is_hk_market_open(self):
        self.assertTrue(is_hk_market_open("2025-04-10"))
        self.assertFalse(is_hk_market_open("2025-04-12"))
        self.assertFalse(is_hk_market_open("2025-04-13"))
        self.assertFalse(is_hk_market_open("2025-04-18"))
        self.assertFalse(is_hk_market_open("2025-05-01"))


def test_get_a_stock_trading_window_returns_none_for_weekend_only_range():
    assert get_a_stock_trading_window("20260711", "2026-07-12") is None


def test_get_a_stock_trading_window_shrinks_range_to_trading_days():
    assert get_a_stock_trading_window("20260711", "2026-07-14") == ("20260713", "20260714")


def test_get_a_stock_trading_window_returns_none_when_start_after_end():
    assert get_a_stock_trading_window("20260714", "20260713") is None


if __name__ == "__main__":
    unittest.main()
