import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from common.const import (  # noqa: E402
    COL_AMOUNT,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_IS_ST,
    COL_LOW,
    COL_OPEN,
    COL_PB_MRQ,
    COL_PCF_NCF_TTM,
    COL_PE_TTM,
    COL_PS_TTM,
    COL_STOCK_ID,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)


@pytest.fixture(scope="function")
def downloader_bs_module(monkeypatch):
    """Setup baostock downloader module with mocked dependencies."""
    module_name = "download.dl.downloader_baostock"

    # First, remove any existing modules from sys.modules to ensure clean import
    modules_to_remove = [
        module_name,
        "download.dl.downloader",
        "download.dl",
        "download.download_manager",
        "download",
    ]

    for mod in modules_to_remove:
        sys.modules.pop(mod, None)

    # Mock baostock module with nested structure BEFORE any imports
    bs_stub = types.SimpleNamespace()

    # Mock the nested data.resultset structure
    data_stub = types.SimpleNamespace()
    resultset_stub = types.SimpleNamespace()
    resultset_stub.ResultData = object  # Mock ResultData type
    data_stub.resultset = resultset_stub
    bs_stub.data = data_stub

    # Mock both the main module and the submodule
    monkeypatch.setitem(sys.modules, "baostock", bs_stub)
    monkeypatch.setitem(sys.modules, "baostock.data", data_stub)
    monkeypatch.setitem(sys.modules, "baostock.data.resultset", resultset_stub)

    # Now import the module
    module = importlib.import_module(module_name)
    return module, bs_stub


def test_download_history_data_stock_bs_valid_input(downloader_bs_module):
    """Test successful download of stock history data with valid input."""
    module, bs_stub = downloader_bs_module

    # Mock baostock login response
    login_mock = Mock()
    login_mock.error_code = "0"
    login_mock.error_msg = "success"
    bs_stub.login = Mock(return_value=login_mock)

    # Mock baostock query response
    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turn",
        "pctChg",
        "peTTM",
        "pbMRQ",
        "psTTM",
        "pcfNcfTTM",
        "isST",
    ]
    query_mock.next = Mock(
        side_effect=[True, True, False]
    )  # Return True twice, then False
    query_mock.get_row_data = Mock(
        side_effect=[
            [
                "2024-01-01",
                "000001",
                "10.0",
                "10.5",
                "9.5",
                "10.2",
                "1000000",
                "10200000",
                "5.2",
                "2.0",
                "15.5",
                "1.2",
                "2.1",
                "8.5",
                "0",
            ],
            [
                "2024-01-02",
                "000001",
                "10.2",
                "11.0",
                "10.1",
                "10.8",
                "1200000",
                "12960000",
                "5.8",
                "5.9",
                "16.2",
                "1.3",
                "2.2",
                "9.1",
                "0",
            ],
        ]
    )

    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test the function
    result = module.download_history_data_stock_bs(
        stock_id="000001",
        start_date="2024-01-01",
        end_date="2024-01-02",
        period=PeriodType.DAILY,
        adjust=AdjustType.QFQ,
    )

    # Verify baostock functions were called correctly
    bs_stub.login.assert_called_once()
    bs_stub.query_history_k_data_plus.assert_called_once_with(
        "sz.000001",
        "date,code,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
        "2024-01-01",
        "2024-01-02",
        frequency="d",
        adjustflag="1",
    )
    bs_stub.logout.assert_called_once()

    # Verify result structure
    assert isinstance(result, pd.DataFrame)
    expected_columns = [
        COL_DATE,
        COL_STOCK_ID,
        COL_OPEN,
        COL_HIGH,
        COL_LOW,
        COL_CLOSE,
        COL_VOLUME,
        COL_AMOUNT,
        COL_TURNOVER_RATE,
        COL_CHANGE_RATE,
        COL_PE_TTM,
        COL_PB_MRQ,
        COL_PS_TTM,
        COL_PCF_NCF_TTM,
        COL_IS_ST,
    ]
    assert list(result.columns) == expected_columns
    assert len(result) == 2

    # Verify data content
    assert result[COL_DATE].tolist() == ["2024-01-01", "2024-01-02"]
    assert result[COL_STOCK_ID].tolist() == ["000001", "000001"]
    assert result[COL_CLOSE].tolist() == [10.2, 10.8]


def test_download_history_data_stock_bs_weekly_period(downloader_bs_module):
    """Test download with weekly period setting."""
    module, bs_stub = downloader_bs_module

    # Mock baostock responses
    login_mock = Mock()
    login_mock.error_code = "0"
    bs_stub.login = Mock(return_value=login_mock)

    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
    ]
    query_mock.next = Mock(return_value=False)  # No data
    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test weekly period
    result = module.download_history_data_stock_bs(
        stock_id="600000",
        start_date="2024-01-01",
        end_date="2024-01-31",
        period=PeriodType.WEEKLY,
        adjust=AdjustType.QFQ,
    )

    # Verify weekly frequency was used
    bs_stub.query_history_k_data_plus.assert_called_once_with(
        "sh.600000",
        "date,code,open,high,low,close,volume,amount,turn,pctChg",
        "2024-01-01",
        "2024-01-31",
        frequency="w",
        adjustflag="1",
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0  # No data returned


def test_download_history_data_stock_bs_hfq_adjustment(downloader_bs_module):
    """Test download with HFQ (后复权) adjustment."""
    module, bs_stub = downloader_bs_module

    # Mock baostock responses
    login_mock = Mock()
    login_mock.error_code = "0"
    bs_stub.login = Mock(return_value=login_mock)

    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
    ]
    query_mock.next = Mock(return_value=False)  # No data
    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test HFQ adjustment
    module.download_history_data_stock_bs(
        stock_id="300123",
        start_date="2024-01-01",
        end_date="2024-01-02",
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
    )

    # Verify HFQ adjustment flag was used
    bs_stub.query_history_k_data_plus.assert_called_once_with(
        "sz.300123",
        "date,code,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
        "2024-01-01",
        "2024-01-02",
        frequency="d",
        adjustflag="2",
    )


def test_download_history_data_stock_bs_bfq_adjustment(downloader_bs_module):
    """Test download with BFQ (不复权) adjustment."""
    module, bs_stub = downloader_bs_module

    # Mock baostock responses
    login_mock = Mock()
    login_mock.error_code = "0"
    bs_stub.login = Mock(return_value=login_mock)

    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
    ]
    query_mock.next = Mock(return_value=False)  # No data
    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test BFQ adjustment
    module.download_history_data_stock_bs(
        stock_id="002001",
        start_date="2024-01-01",
        end_date="2024-01-02",
        period=PeriodType.DAILY,
        adjust=AdjustType.BFQ,
    )

    # Verify BFQ adjustment flag was used
    bs_stub.query_history_k_data_plus.assert_called_once_with(
        "sz.002001",
        "date,code,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
        "2024-01-01",
        "2024-01-02",
        frequency="d",
        adjustflag="3",
    )


def test_download_history_data_stock_bs_invalid_stock_id(downloader_bs_module):
    """Test function raises assertion error for invalid stock ID format."""
    module, bs_stub = downloader_bs_module

    # Mock baostock login response to succeed (login happens before assertion)
    login_mock = Mock()
    login_mock.error_code = "0"
    login_mock.error_msg = "success"
    bs_stub.login = Mock(return_value=login_mock)
    bs_stub.logout = Mock()

    # Test invalid stock ID formats - now login will be called first, then assertion
    with pytest.raises(AssertionError, match="Stock ID must be 6 digits"):
        module.download_history_data_stock_bs(
            stock_id="12345",  # Only 5 digits
            start_date="2024-01-01",
            end_date="2024-01-02",
        )

    with pytest.raises(AssertionError, match="Stock ID must be 6 digits"):
        module.download_history_data_stock_bs(
            stock_id="1234567",  # 7 digits
            start_date="2024-01-01",
            end_date="2024-01-02",
        )

    with pytest.raises(AssertionError, match="Stock ID must be 6 digits"):
        module.download_history_data_stock_bs(
            stock_id="ABC123",  # Contains letters
            start_date="2024-01-01",
            end_date="2024-01-02",
        )

    # Verify baostock login was called for each attempt (decorator behavior)
    assert bs_stub.login.call_count == 3
    # Verify logout was also called for each attempt (decorator cleanup)
    assert bs_stub.logout.call_count == 3


def test_download_history_data_stock_bs_login_failure(downloader_bs_module):
    """Test function raises ConnectionError when login fails."""
    module, bs_stub = downloader_bs_module

    # Mock failed login
    login_mock = Mock()
    login_mock.error_code = "1"
    login_mock.error_msg = "Login failed"
    bs_stub.login = Mock(return_value=login_mock)

    with pytest.raises(ConnectionError, match="Baostock login failed: Login failed"):
        module.download_history_data_stock_bs(
            stock_id="000001", start_date="2024-01-01", end_date="2024-01-02"
        )

    bs_stub.login.assert_called_once()


def test_download_history_data_stock_bs_query_error(downloader_bs_module):
    """Test function handles query errors properly."""
    module, bs_stub = downloader_bs_module

    # Mock successful login
    login_mock = Mock()
    login_mock.error_code = "0"
    bs_stub.login = Mock(return_value=login_mock)

    # Mock query with error
    query_mock = Mock()
    query_mock.error_code = "1"  # Error code
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
    ]
    query_mock.next = Mock(return_value=False)  # No iteration
    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    result = module.download_history_data_stock_bs(
        stock_id="000001", start_date="2024-01-01", end_date="2024-01-02"
    )

    # Should return empty DataFrame when query has error
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
    # When there's an error, the function should still map columns to Chinese names
    # But only for the fields that were actually requested
    expected_columns = [
        COL_DATE,
        COL_STOCK_ID,
        COL_OPEN,
        COL_HIGH,
        COL_LOW,
        COL_CLOSE,
        "preclose",
        COL_VOLUME,
        COL_AMOUNT,
        "adjustflag",
    ]
    assert list(result.columns) == expected_columns
    bs_stub.logout.assert_called_once()


def test_download_history_data_stock_bs_empty_values_replaced_with_zero(
    downloader_bs_module,
):
    """Test that empty values are properly replaced with 0."""
    module, bs_stub = downloader_bs_module

    # Mock baostock login response
    login_mock = Mock()
    login_mock.error_code = "0"
    login_mock.error_msg = "success"
    bs_stub.login = Mock(return_value=login_mock)

    # Mock baostock query response with empty values
    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turn",
        "pctChg",
        "peTTM",
        "pbMRQ",
        "psTTM",
        "pcfNcfTTM",
        "isST",
    ]
    query_mock.next = Mock(
        side_effect=[True, True, False]
    )  # Return True twice, then False
    query_mock.get_row_data = Mock(
        side_effect=[
            [
                "2024-01-01",
                "000001",
                "10.0",  # open - valid value
                "10.5",  # high - valid value
                "9.5",  # low - valid value
                "10.2",  # close - valid value
                "",  # volume - empty value
                "10200000",  # amount - valid value
                "",  # turn - empty value
                "2.0",  # pctChg - valid value
                "",  # peTTM - empty value
                "1.2",  # pbMRQ - valid value
                "",  # psTTM - empty value
                "8.5",  # pcfNcfTTM - valid value
                "0",  # isST - valid value
            ],
            [
                "2024-01-02",
                "000001",
                "",  # open - empty value
                "11.0",  # high - valid value
                "10.1",  # low - valid value
                "",  # close - empty value
                "1200000",  # volume - valid value
                "12960000",  # amount - valid value
                "5.8",  # turn - valid value
                "",  # pctChg - empty value
                "16.2",  # peTTM - valid value
                "",  # pbMRQ - empty value
                "2.2",  # psTTM - valid value
                "",  # pcfNcfTTM - empty value
                "0",  # isST - valid value
            ],
        ]
    )

    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test the function
    result = module.download_history_data_stock_bs(
        stock_id="000001",
        start_date="2024-01-01",
        end_date="2024-01-02",
        period=PeriodType.DAILY,
        adjust=AdjustType.QFQ,
    )

    # Verify baostock functions were called correctly
    bs_stub.login.assert_called_once()
    bs_stub.query_history_k_data_plus.assert_called_once()
    bs_stub.logout.assert_called_once()

    # Verify result structure
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2

    # Verify that empty values were replaced with 0
    # First row: volume and turn and peTTM and psTTM should be 0
    assert result[COL_VOLUME].iloc[0] == 0
    assert result[COL_TURNOVER_RATE].iloc[0] == 0
    assert result[COL_PE_TTM].iloc[0] == 0
    assert result[COL_PS_TTM].iloc[0] == 0

    # Second row: open, close, pctChg, pbMRQ, pcfNcfTTM should be 0
    assert result[COL_OPEN].iloc[1] == 0
    assert result[COL_CLOSE].iloc[1] == 0
    assert result[COL_CHANGE_RATE].iloc[1] == 0
    assert result[COL_PB_MRQ].iloc[1] == 0
    assert result[COL_PCF_NCF_TTM].iloc[1] == 0

    # Verify that valid values remain unchanged
    assert result[COL_OPEN].iloc[0] == 10.0
    assert result[COL_CLOSE].iloc[0] == 10.2
    assert result[COL_HIGH].iloc[1] == 11.0
    assert result[COL_LOW].iloc[1] == 10.1
    assert result[COL_AMOUNT].iloc[0] == 10200000
    assert result[COL_AMOUNT].iloc[1] == 12960000

    # Verify data types are numeric
    numeric_columns = [
        COL_OPEN,
        COL_HIGH,
        COL_LOW,
        COL_CLOSE,
        COL_VOLUME,
        COL_AMOUNT,
        COL_TURNOVER_RATE,
        COL_CHANGE_RATE,
        COL_PE_TTM,
        COL_PB_MRQ,
        COL_PS_TTM,
        COL_PCF_NCF_TTM,
    ]

    for col in numeric_columns:
        if col in result.columns:
            # Check that the column contains numeric values (not strings)
            assert (
                pd.api.types.is_numeric_dtype(result[col].dtype)
                or result[col].dtype == "int64"
                or result[col].dtype == "float64"
            )


def test_validate_and_convert_date_valid_formats(downloader_bs_module):
    """Test date validation and conversion with various valid formats."""
    module, bs_stub = downloader_bs_module

    # Test various valid date formats
    test_cases = [
        ("2024-01-01", "2024-01-01"),  # YYYY-MM-DD
        ("2024/01/01", "2024-01-01"),  # YYYY/MM/DD
        ("2024.01.01", "2024-01-01"),  # YYYY.MM.DD
        ("01-01-2024", "2024-01-01"),  # DD-MM-YYYY
        ("01/01/2024", "2024-01-01"),  # DD/MM/YYYY
        ("01.01.2024", "2024-01-01"),  # DD.MM.YYYY
        ("20240101", "2024-01-01"),  # YYYYMMDD
    ]

    for input_date, expected_output in test_cases:
        result = module._validate_and_convert_date(input_date)
        assert result == expected_output


def test_validate_and_convert_date_invalid_format(downloader_bs_module):
    """Test date validation raises error for invalid formats."""
    module, bs_stub = downloader_bs_module

    with pytest.raises(ValueError, match="Invalid date format"):
        module._validate_and_convert_date("invalid-date")


def test_download_history_data_stock_bs_monthly_period(downloader_bs_module):
    """Test download with monthly period setting."""
    module, bs_stub = downloader_bs_module

    # Mock baostock responses
    login_mock = Mock()
    login_mock.error_code = "0"
    bs_stub.login = Mock(return_value=login_mock)

    query_mock = Mock()
    query_mock.error_code = "0"
    query_mock.fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
    ]
    query_mock.next = Mock(return_value=False)  # No data
    bs_stub.query_history_k_data_plus = Mock(return_value=query_mock)
    bs_stub.logout = Mock()

    # Test monthly period
    result = module.download_history_data_stock_bs(
        stock_id="600000",
        start_date="2024-01-01",
        end_date="2024-01-31",
        period=PeriodType.MONTHLY,
        adjust=AdjustType.QFQ,
    )

    # Verify monthly frequency was used
    bs_stub.query_history_k_data_plus.assert_called_once_with(
        "sh.600000",
        "date,code,open,high,low,close,volume,amount,turn,pctChg",
        "2024-01-01",
        "2024-01-31",
        frequency="m",
        adjustflag="1",
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0  # No data returned


if __name__ == "__main__":
    pytest.main([__file__])
