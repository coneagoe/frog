import os
import sys
from unittest.mock import Mock

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import conf  # noqa: E402
from common.const import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_VOLUME,
    PeriodType,
)
from download.dl import Downloader  # noqa: E402

conf.parse_config()


class TestDownloader:
    def test_dl_general_info_stock(self, monkeypatch):
        mock_data = pd.DataFrame(
            {"code": ["000001", "600000"], "name": ["平安银行", "浦发银行"]}
        )
        mock_ak_stock_info_a_code_name = Mock(return_value=mock_data)
        monkeypatch.setattr(
            "download.dl.downloader_akshare.ak.stock_info_a_code_name",
            mock_ak_stock_info_a_code_name,
        )

        result = Downloader.dl_general_info_stock()

        mock_ak_stock_info_a_code_name.assert_called_once()

        assert isinstance(result, pd.DataFrame)
        assert COL_STOCK_ID in result.columns
        assert COL_STOCK_NAME in result.columns

        assert len(result) == 2
        assert result[COL_STOCK_ID].tolist() == ["000001", "600000"]
        assert result[COL_STOCK_NAME].tolist() == ["平安银行", "浦发银行"]

    def test_dl_general_info_etf(self, monkeypatch):
        mock_data = pd.DataFrame(
            {
                COL_ETF_ID: ["510300", "510500"],
                COL_ETF_NAME: ["沪深300ETF", "中证500ETF"],
            }
        )
        mock_ak_fund_name_em = Mock(return_value=mock_data)
        monkeypatch.setattr(
            "download.dl.downloader_akshare.ak.fund_name_em", mock_ak_fund_name_em
        )

        result = Downloader.dl_general_info_etf()

        mock_ak_fund_name_em.assert_called_once()

        assert isinstance(result, pd.DataFrame)
        assert COL_ETF_ID in result.columns
        assert COL_ETF_NAME in result.columns

        assert len(result) == 2
        assert result[COL_ETF_ID].tolist() == ["510300", "510500"]
        assert result[COL_ETF_NAME].tolist() == ["沪深300ETF", "中证500ETF"]

    def test_dl_general_info_hk_ggt_stock(self, monkeypatch):
        """
        测试 Downloader.dl_general_info_hk_ggt_stock
        """
        # 准备模拟数据 - 港股通信息（使用原始中文列名）
        mock_data = pd.DataFrame(
            {
                "代码": ["00700", "00939"],
                "名称": ["腾讯控股", "中国建设银行"],
            }
        )
        mock_ak_stock_hk_ggt_components_em = Mock(return_value=mock_data)
        monkeypatch.setattr(
            "download.dl.downloader_akshare.ak.stock_hk_ggt_components_em",
            mock_ak_stock_hk_ggt_components_em,
        )

        # 调用被测试的方法
        result = Downloader.dl_general_info_hk_ggt_stock()

        # 断言 akshare 函数被调用
        mock_ak_stock_hk_ggt_components_em.assert_called_once()

        # 验证返回的数据框结构正确（重命名后的列名）
        assert isinstance(result, pd.DataFrame)
        assert COL_STOCK_ID in result.columns
        assert COL_STOCK_NAME in result.columns

        # 验证数据内容
        assert len(result) == 2
        assert result[COL_STOCK_ID].tolist() == ["00700", "00939"]
        assert result[COL_STOCK_NAME].tolist() == ["腾讯控股", "中国建设银行"]

    def test_dl_history_data_stock(self, monkeypatch):
        # Mock baostock login
        mock_login_result = Mock()
        mock_login_result.error_code = "0"
        mock_login_result.error_msg = ""
        mock_bs_login = Mock(return_value=mock_login_result)
        monkeypatch.setattr("baostock.login", mock_bs_login)

        # Mock baostock logout
        mock_bs_logout = Mock()
        monkeypatch.setattr("baostock.logout", mock_bs_logout)

        # Mock query_history_k_data_plus
        mock_rs = Mock()
        mock_rs.error_code = "0"
        mock_rs.fields = ["date", "code", "open", "high", "low", "close", "volume"]
        mock_rs.next.side_effect = [True, True, False]  # 2 rows of data, then False
        mock_rs.get_row_data.side_effect = [
            ["2024-01-01", "sz.000001", "10.0", "10.3", "9.9", "10.2", "1000000"],
            ["2024-01-02", "sz.000001", "10.5", "11.0", "10.3", "10.8", "1200000"],
        ]

        mock_query_history_k_data_plus = Mock(return_value=mock_rs)
        monkeypatch.setattr(
            "baostock.query_history_k_data_plus", mock_query_history_k_data_plus
        )

        dl = Downloader()
        result = dl.dl_history_data_stock(
            stock_id="000001", start_date="20240101", end_date="20240102"
        )

        # 断言 baostock 函数被调用
        mock_bs_login.assert_called_once()
        mock_query_history_k_data_plus.assert_called_once()
        mock_bs_logout.assert_called_once()

        # 验证返回的数据框结构正确
        assert isinstance(result, pd.DataFrame)
        assert COL_DATE in result.columns
        assert COL_OPEN in result.columns
        assert COL_CLOSE in result.columns
        assert COL_HIGH in result.columns
        assert COL_LOW in result.columns
        assert COL_VOLUME in result.columns

        # 验证数据内容
        assert len(result) == 2

    def test_dl_history_data_etf(self, monkeypatch):
        """
        测试 Downloader.dl_history_data_etf
        """
        # 准备模拟数据 - ETF历史数据
        mock_data = pd.DataFrame(
            {
                "日期": ["2024-01-01", "2024-01-02"],
                "开盘": [3.0, 3.1],
                "收盘": [3.2, 3.3],
                "最高": [3.3, 3.4],
                "最低": [2.9, 3.0],
                "成交量": [500000, 600000],
            }
        )
        mock_ak_fund_etf_hist_em = Mock(return_value=mock_data)
        monkeypatch.setattr(
            "download.dl.downloader_akshare.ak.fund_etf_hist_em",
            mock_ak_fund_etf_hist_em,
        )

        # 调用被测试的方法
        result = Downloader.dl_history_data_etf(
            etf_id="510300", start_date="2024-01-01", end_date="2024-01-02"
        )

        # 断言 akshare 函数被调用
        mock_ak_fund_etf_hist_em.assert_called_once_with(
            symbol="510300", period="daily", adjust="qfq"
        )

        # 验证返回的数据框结构正确
        assert isinstance(result, pd.DataFrame)
        assert COL_DATE in result.columns
        assert COL_OPEN in result.columns
        assert COL_CLOSE in result.columns
        assert COL_HIGH in result.columns
        assert COL_LOW in result.columns
        assert COL_VOLUME in result.columns

        # 验证数据内容
        assert len(result) == 2

    def test_dl_history_data_us_index(self, monkeypatch):
        """
        测试 Downloader.dl_history_data_us_index
        """
        # 准备模拟数据 - 美股指数历史数据
        mock_data = pd.DataFrame(
            {
                "日期": ["2024-01-01", "2024-01-02"],
                "开盘": [4500.0, 4520.0],
                "收盘": [4550.0, 4580.0],
                "最高": [4560.0, 4590.0],
                "最低": [4480.0, 4510.0],
                "成交量": [2000000, 2100000],
            }
        )
        mock_ak_index_us_stock_sina = Mock(return_value=mock_data)
        monkeypatch.setattr(
            "download.dl.downloader_akshare.ak.index_us_stock_sina",
            mock_ak_index_us_stock_sina,
        )

        # 调用被测试的方法
        result = Downloader.dl_history_data_us_index(
            index=".DJI", period=PeriodType.DAILY
        )

        # 断言 akshare 函数被调用
        mock_ak_index_us_stock_sina.assert_called_once_with(symbol=".DJI")

        # 验证返回的数据框结构正确
        assert isinstance(result, pd.DataFrame)
        assert COL_DATE in result.columns
        assert COL_OPEN in result.columns
        assert COL_CLOSE in result.columns
        assert COL_HIGH in result.columns
        assert COL_LOW in result.columns
        assert COL_VOLUME in result.columns

        # 验证数据内容
        assert len(result) == 2

    def test_downloader_method_assignments(self):
        """
        测试 Downloader 类方法正确映射到对应的实现函数
        """
        # 验证方法映射关系
        from download.dl.downloader_akshare import (
            download_general_info_etf_ak,
            download_general_info_hk_ggt_stock_ak,
            download_general_info_stock_ak,
            download_history_data_etf_ak,
            download_history_data_us_index_ak,
        )
        from download.dl.downloader_baostock import download_history_data_stock_bs

        assert Downloader.dl_general_info_stock == download_general_info_stock_ak
        assert Downloader.dl_general_info_etf == download_general_info_etf_ak
        assert (
            Downloader.dl_general_info_hk_ggt_stock
            == download_general_info_hk_ggt_stock_ak
        )
        assert Downloader.dl_history_data_etf == download_history_data_etf_ak
        assert Downloader.dl_history_data_stock == download_history_data_stock_bs
        assert Downloader.dl_history_data_us_index == download_history_data_us_index_ak


if __name__ == "__main__":
    pytest.main([__file__])
