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
    is_st,
    drop_st,

    drop_low_price_stocks,

)   # noqa: E402

from stock.const import (

    COL_STOCK_ID,
)



conf.parse_config()


stocks = (

    '000009',
    '000021',

    '000027',

    '000031',

    '000039',

    '000050',

    '000060',

    '000066',

    '000089',

    '000155',

    '000156',

    '000400',

    '000401',

    '000402',

    '000423',

    '000513',

    '000519',

    '000537',

    '000539',

    '000547',

    '000553',

    '000559',

    '000563',
)

 

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



    def test_is_st(self):

        self.assertFalse(is_st('000001'))

        self.assertTrue(is_st('000023'))

        self.assertTrue(is_st('000040'))



    def test_drop_st(self):

        df_stocks = pd.DataFrame(stocks, columns=[COL_STOCK_ID])

        df = drop_st(df_stocks)
        print(df)



    def test_drop_low_stocks(self):

        df_stocks = pd.DataFrame(stocks, columns=[COL_STOCK_ID])

        df = drop_low_price_stocks(df_stocks, '2023-10-01', '2023-11-01')
        print(df)



if __name__ == '__main__':

    unittest.main()

