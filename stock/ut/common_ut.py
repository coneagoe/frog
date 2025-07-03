import os
import sys
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import conf
from stock.common import (is_a_market_open, is_hk_market_open)


conf.parse_config()


class TestIsAMarketOpen(unittest.TestCase):
    def test_is_a_market_open(self):
        # Test a known trading day (weekday)
        self.assertTrue(is_a_market_open('2025-04-10'))  # Thursday

        # Test weekend days (typically non-trading days)
        self.assertFalse(is_a_market_open('2025-04-12'))  # Saturday
        self.assertFalse(is_a_market_open('2025-04-13'))  # Sunday

        # Test a known Chinese holiday (example: Chinese New Year)
        # Assuming 2025-02-01 is Chinese New Year holiday
        self.assertFalse(is_a_market_open('2025-01-29'))


class TestIsHkMarketOpen(unittest.TestCase):
    def test_is_hk_market_open(self):
        # Test a known trading day (weekday)
        self.assertTrue(is_hk_market_open('2025-04-10'))  # Thursday

        # Test weekend days (typically non-trading days)
        self.assertFalse(is_hk_market_open('2025-04-12'))  # Saturday
        self.assertFalse(is_hk_market_open('2025-04-13'))  # Sunday

        # Test a known Hong Kong holiday (Good Friday)
        self.assertFalse(is_hk_market_open('2025-04-18'))
        
        # Test another known Hong Kong holiday (Labour Day)
        self.assertFalse(is_hk_market_open('2025-05-01'))


if __name__ == '__main__':
    unittest.main()
