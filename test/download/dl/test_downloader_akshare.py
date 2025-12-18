import importlib
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from common.const import AdjustType, PeriodType  # noqa: E402


@pytest.fixture(scope="function")
def downloader_module(monkeypatch):
    module_name = "download.dl.downloader_akshare"
    sys.modules.pop(module_name, None)
    sys.modules.pop("akshare", None)
    sys.modules.pop("retrying", None)
    sys.modules.pop("utility", None)

    ak_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "akshare", ak_stub)

    def retry_decorator(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    retrying_stub = types.ModuleType("retrying")
    retrying_stub.retry = retry_decorator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "retrying", retrying_stub)

    utility_stub = types.ModuleType("utility")

    def get_proxy_func():
        return {"http": "http://test:8080", "https": "http://test:8080"}

    utility_stub.get_proxy = get_proxy_func  # type: ignore[attr-defined]

    def change_proxy_decorator(func):
        return func

    utility_stub.change_proxy = change_proxy_decorator  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "utility", utility_stub)

    module = importlib.import_module(module_name)
    module = importlib.reload(module)

    return module, ak_stub


def test_download_general_info_stock_filters_codes(downloader_module):
    module, ak_stub = downloader_module

    sample = pd.DataFrame(
        {
            "code": ["600000", "000001", "300123", "002001", "900001"],
            "name": ["A", "B", "C", "D", "E"],
        }
    )
    ak_stub.stock_info_a_code_name = lambda: sample

    result = module.download_general_info_stock_ak()

    assert result[module.COL_STOCK_ID].tolist() == [
        "600000",
        "000001",
        "300123",
        "002001",
    ]
    assert list(result.columns) == [module.COL_STOCK_ID, module.COL_STOCK_NAME]


def test_download_history_data_etf_fallback_to_money_fund(downloader_module):
    module, ak_stub = downloader_module

    def fail_fund_etf_hist_em(*args, **kwargs):
        raise KeyError("fallback")

    ak_stub.fund_etf_hist_em = fail_fund_etf_hist_em

    ak_stub.fund_money_fund_info_em = lambda symbol: pd.DataFrame(
        {
            "净值日期": ["2024-01-01"],
            "每万份收益": [1.234],
            "extra": ["keep"],
        }
    )

    result = module.download_history_data_etf_ak("512000", "2024-01-01", "2024-01-01")

    assert list(result.columns[:6]) == [
        module.COL_DATE,
        module.COL_CLOSE,
        module.COL_OPEN,
        module.COL_HIGH,
        module.COL_LOW,
        module.COL_VOLUME,
    ]
    assert result[module.COL_OPEN].iloc[0] == pytest.approx(
        result[module.COL_CLOSE].iloc[0]
    )
    assert result[module.COL_HIGH].iloc[0] == pytest.approx(
        result[module.COL_CLOSE].iloc[0]
    )
    assert result[module.COL_LOW].iloc[0] == pytest.approx(
        result[module.COL_CLOSE].iloc[0]
    )
    assert result[module.COL_VOLUME].iloc[0] == 0
    assert "extra" in result.columns


def test_download_history_data_stock_hk_returns_correct_data(
    tmp_path, downloader_module, monkeypatch
):
    module, ak_stub = downloader_module

    stock_id = "01234"
    captured = {}

    def fake_stock_hk_hist(symbol, period, start_date, end_date, adjust):
        captured.update(
            {
                "symbol": symbol,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
                "adjust": adjust,
            }
        )
        return pd.DataFrame(
            {
                "日期": ["2024-01-03", "2024-01-02"],
                "开盘": [10.6, 10.2],
                "收盘": [10.9, 10.4],
                "最高": [11.1, 10.8],
                "最低": [10.4, 10.1],
                "成交量": [1300, 1150],
            }
        )

    ak_stub.stock_hk_hist = fake_stock_hk_hist

    result = module.download_history_data_stock_hk_ak(
        stock_id=stock_id,
        start_date="2024-01-01",
        end_date="2024-01-04",
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
    )

    # 验证 API 调用参数
    assert captured["symbol"] == stock_id
    assert captured["start_date"] == "20240101"
    assert captured["adjust"] == AdjustType.HFQ.value
    assert len(captured["end_date"]) == 8

    # 验证返回的数据格式和列名转换
    assert isinstance(result, pd.DataFrame)
    assert module.COL_DATE in result.columns
    assert module.COL_CLOSE in result.columns
    assert module.COL_OPEN in result.columns
    assert module.COL_HIGH in result.columns
    assert module.COL_LOW in result.columns
    assert module.COL_VOLUME in result.columns

    # 验证数据内容和格式
    assert len(result) == 2
    expected_dates = pd.to_datetime(["2024-01-03", "2024-01-02"])
    assert result[module.COL_DATE].tolist() == expected_dates.tolist()
    assert result[module.COL_CLOSE].tolist() == [
        pytest.approx(10.9),
        pytest.approx(10.4),
    ]
    assert result[module.COL_VOLUME].tolist() == [1300, 1150]

    # 验证日期列已被转换为 datetime 类型
    assert pd.api.types.is_datetime64_any_dtype(result[module.COL_DATE])
