import os
import sys
import unittest
# from unittest.mock import patch
import pandas as pd
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import conf     # noqa: E402
from stock.data.access_data import (
    load_history_data_stock,
    load_history_data_etf,
    load_history_data_us_index,
    load_history_data_a_index,
    load_all_hk_ggt_stock_general_info,
    is_hk_ggt_stock,
)


conf.parse_config()


class TestAccessData(unittest.TestCase):
    def test_load_history_data_stock(self):
        df = load_history_data_stock('000001', 'daily', '2022-01-01', '2023-01-02', 'hfq')
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_etf(self):
        df = load_history_data_etf('510300', 'daily', '2022-01-01', '2023-01-02', 'hfq')
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_us_index(self):
        df = load_history_data_us_index('.DJI', 'daily', '2022-01-01', '2023-01-02')
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_a_index(self):
        df = load_history_data_a_index('sz399987', 'daily', '2022-01-01', '2023-01-02')
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_all_hk_ggt_stock_general_info(self):
        df = load_all_hk_ggt_stock_general_info()
        self.assertIsInstance(df, pd.DataFrame)

    def test_is_hk_ggt_stock(self):
        self.assertTrue(is_hk_ggt_stock('00700'))

if __name__ == '__main__':
    unittest.main()
