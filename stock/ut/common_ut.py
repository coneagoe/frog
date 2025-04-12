import os
import sys
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import conf
from stock.common import (is_trading_day)


conf.parse_config()


class TestIsTrading(unittest.TestCase):
    def test_is_trading_day(self):
        # Test a known trading day (weekday)
        self.assertTrue(is_trading_day('2025-04-10'))  # Thursday

        # Test weekend days (typically non-trading days)
        self.assertFalse(is_trading_day('2025-04-12'))  # Saturday
        self.assertFalse(is_trading_day('2025-04-13'))  # Sunday

        # Test a known Chinese holiday (example: Chinese New Year)
        # Assuming 2025-02-01 is Chinese New Year holiday
        self.assertFalse(is_trading_day('2025-02-01'))


if __name__ == '__main__':
    unittest.main()
