import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import conf  # noqa: E402
from stock.const import (  # noqa: E402
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)
from stock.data.access_data import (  # noqa: E402
    drop_delisted_stocks,
    drop_low_price_stocks,
    drop_st,
    get_security_name,
    is_hk_ggt_stock,
    is_st,
    is_stock,
    load_300_ingredients,
    load_500_ingredients,
    load_all_hk_ggt_stock_general_info,
    load_history_data_a_index,
    load_history_data_etf,
    load_history_data_stock,
    load_history_data_stock_hk,
    load_history_data_us_index,
)

conf.parse_config()


stocks = (
    "000009",
    "000021",
    "000027",
    "000031",
    "000039",
    "000050",
    "000060",
    "000066",
    "000089",
    "000155",
    "000156",
    "000400",
    "000401",
    "000402",
    "000423",
    "000513",
    "000519",
    "000537",
    "000539",
    "000547",
    "000553",
    "000559",
    "000563",
)


class TestAccessData(unittest.TestCase):
    def test_load_history_data_stock(self):
        df = load_history_data_stock(
            "000001", "daily", "2022-01-01", "2023-01-02", "hfq"
        )
        self.assertIsInstance(df, pd.DataFrame)
        df = load_history_data_stock(
            "002683", "daily", "2024-11-01", "2025-04-18", "hfq"
        )
        self.assertFalse((df[COL_OPEN] >= 2683).any())
        self.assertFalse((df[COL_CLOSE] >= 2683).any())
        self.assertFalse((df[COL_HIGH] >= 2683).any())
        self.assertFalse((df[COL_LOW] >= 2683).any())

    def test_load_history_data_stock_hk(self):
        df = load_history_data_stock_hk(
            "00700", "daily", "2022-01-01", "2023-01-02", "hfq"
        )
        self.assertIsInstance(df, pd.DataFrame)
        df = load_history_data_stock_hk(
            "02510", "daily", "2024-11-01", "2025-06-23", "hfq"
        )
        # print(df.tail())
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_etf(self):
        df = load_history_data_etf("510300", "daily", "2022-01-01", "2023-01-02", "hfq")
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_us_index(self):
        df = load_history_data_us_index(".DJI", "daily", "2022-01-01", "2023-01-02")
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_history_data_a_index(self):
        df = load_history_data_a_index("sz399987", "daily", "2022-01-01", "2023-01-02")
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_all_hk_ggt_stock_general_info(self):
        df = load_all_hk_ggt_stock_general_info()
        self.assertIsInstance(df, pd.DataFrame)

    def test_is_hk_ggt_stock(self):
        self.assertTrue(is_hk_ggt_stock("00700"))

    def test_is_st(self):
        self.assertFalse(is_st("000001"))
        # self.assertTrue(is_st('000023'))
        # self.assertTrue(is_st('000040'))

    def test_drop_st(self):
        df_stocks = pd.DataFrame(stocks, columns=[COL_STOCK_ID])
        df = drop_st(df_stocks)
        self.assertTrue(
            all(not ("ST" in str(name).upper()) for name in df[COL_STOCK_NAME])
        )

    def test_drop_low_stocks(self):
        df_stocks = pd.DataFrame(stocks, columns=[COL_STOCK_ID])
        drop_low_price_stocks(df_stocks, "2023-10-01", "2023-11-01")

    def test_load_300_ingredients(self):
        stocks = load_300_ingredients("2021-01-01")
        self.assertTrue("000001" in stocks)

    def test_is_stock(self):
        self.assertTrue(is_stock("600000"))
        self.assertTrue(is_stock("000001"))
        self.assertTrue(is_stock("300043"))

    def test_load_500_ingredients(self):
        # Test with a specific date
        stocks = load_500_ingredients("2023-01-01")
        self.assertIsInstance(stocks, list)
        self.assertTrue(len(stocks) > 0)

        # Check if all stock IDs are strings of length 6
        for stock in stocks:
            self.assertIsInstance(stock, str)
            self.assertEqual(len(stock), 6)

        # Test that the function handles different dates correctly
        stocks_july = load_500_ingredients("2023-07-01")
        stocks_august = load_500_ingredients("2023-08-15")
        self.assertEqual(
            stocks_july, stocks_august
        )  # Should use the same data for July-December

        stocks_january = load_500_ingredients("2023-01-01")
        stocks_june = load_500_ingredients("2023-06-30")
        self.assertEqual(
            stocks_january, stocks_june
        )  # Should use the same data for January-June

        # Test with an invalid date format
        with self.assertRaises(AssertionError):
            load_500_ingredients("2023/01/01")

    def test_drop_delisted_stocks(self):
        stocks = ["600240", "000001", "000003", "002147"]
        result = drop_delisted_stocks(stocks, "2023-01-01", "2024-01-01")
        self.assertEqual(result, ["000001"])

    def test_get_security_name(self):
        # Test US indices
        self.assertEqual(get_security_name(".IXIC"), "NASDAQ Composite")
        self.assertEqual(get_security_name(".DJI"), "Dow Jones Industrial Average")
        self.assertEqual(get_security_name(".INX"), "S&P 500")

        self.assertEqual(get_security_name("000001"), "平安银行")
        self.assertEqual(get_security_name("00700"), "腾讯控股")
        self.assertEqual(get_security_name("513100"), "国泰纳斯达克100ETF")


if __name__ == "__main__":
    unittest.main()
