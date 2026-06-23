import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import conf  # noqa: E402
from stock.market import is_a_market_open, is_hk_market_open  # noqa: E402

conf.parse_config()


class TestIsAMarketOpen(unittest.TestCase):
    def test_is_a_market_open(self):
        self.assertTrue(is_a_market_open("2025-04-10"))
        self.assertFalse(is_a_market_open("2025-04-12"))
        self.assertFalse(is_a_market_open("2025-04-13"))
        self.assertFalse(is_a_market_open("2025-01-29"))


class TestIsHkMarketOpen(unittest.TestCase):
    def test_is_hk_market_open(self):
        self.assertTrue(is_hk_market_open("2025-04-10"))
        self.assertFalse(is_hk_market_open("2025-04-12"))
        self.assertFalse(is_hk_market_open("2025-04-13"))
        self.assertFalse(is_hk_market_open("2025-04-18"))
        self.assertFalse(is_hk_market_open("2025-05-01"))


if __name__ == "__main__":
    unittest.main()
