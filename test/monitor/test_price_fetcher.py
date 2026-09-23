import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from common.const import COL_CLOSE, COL_DATE, AdjustType, PeriodType
from monitor.price_fetcher import (
    fetch_current_price,
    fetch_final_close_history_df,
    fetch_history_df,
    fetch_price,
)


def _install_tushare_stub(monkeypatch, pro_client):
    ts_stub = SimpleNamespace(pro_api=lambda token: pro_client)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)


def test_fetch_price_a_share_uses_rt_k(monkeypatch):
    pro_client = SimpleNamespace(rt_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 1800.5}]))
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("600519", "A") == 1800.5


def test_fetch_price_hk_uses_rt_hk_k(monkeypatch):
    pro_client = SimpleNamespace(rt_hk_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 64.85}]))
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("00001", "HK") == 64.85


def test_fetch_price_surfaces_client_creation_failure(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(ConnectionError):
        fetch_price("600519", "A")


def test_fetch_price_does_not_fallback_to_env_file(monkeypatch, tmp_path):
    class ProClient:
        def rt_k(self, ts_code):
            return pd.DataFrame([{"ts_code": ts_code, "close": 27.56}])

    env_file = tmp_path / ".env"
    env_file.write_text('TUSHARE_TOKEN="env-token"\n', encoding="utf-8")

    def pro_api(token):
        assert token == "env-token"
        return ProClient()

    ts_stub = SimpleNamespace(pro_api=pro_api)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(ConnectionError):
        fetch_price("002558", "A")


def test_fetch_price_returns_nan_on_api_error(monkeypatch):
    def _raise(_ts_code):
        raise Exception("频率超限")

    pro_client = SimpleNamespace(rt_k=_raise)
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert np.isnan(fetch_price("510300", "ETF"))


def test_fetch_current_price_delegates_to_fetch_price(monkeypatch):
    monkeypatch.setattr("monitor.price_fetcher.fetch_price", lambda code, market: 3.25)
    assert fetch_current_price("510300", "ETF") == 3.25


def test_fetch_price_rejects_unsupported_a_code(monkeypatch):
    def rt_k(ts_code):
        close = 1.0 if ts_code.endswith(".SZ") else 2.0
        return pd.DataFrame([{"ts_code": ts_code, "close": close}])

    pro_client = SimpleNamespace(rt_k=rt_k)
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    with pytest.raises(ValueError):
        fetch_price("510300", "A")


def test_fetch_price_map_applies_shared_provider_code_to_distinct_input_keys(monkeypatch):
    pro_client = SimpleNamespace(
        rt_k=lambda ts_code: pd.DataFrame([{"ts_code": "600519.SH", "close": 1800.5}])
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    from monitor.price_fetcher import fetch_price_map

    monkeypatch.setattr(
        "monitor.price_fetcher._to_ts_code",
        lambda code, market: "600519.SH" if (code, market) in {("600519", "A"), ("510300", "ETF")} else "",
    )

    assert fetch_price_map([("600519", "A"), ("510300", "ETF")]) == {
        ("600519", "A"): 1800.5,
        ("510300", "ETF"): 1800.5,
    }


def test_fetch_price_map_ignores_unrequested_provider_rows(monkeypatch):
    pro_client = SimpleNamespace(
        rt_k=lambda ts_code: pd.DataFrame(
            [{"ts_code": ts_code, "close": 1800.5}, {"ts_code": "999999.SZ", "close": 1.0}]
        )
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("600519", "A") == 1800.5


def test_fetch_history_df_prefers_tushare_daily_for_a_share(monkeypatch):
    class ProClient:
        def daily(self, ts_code, start_date, end_date):
            assert ts_code == "002558.SZ"
            return pd.DataFrame(
                [
                    {"trade_date": "20260601", "close": 25.0},
                    {"trade_date": "20260602", "close": 26.0},
                    {"trade_date": "20260603", "close": 27.0},
                ]
            )

    storage = SimpleNamespace(load_history_data_stock=lambda **kwargs: pd.DataFrame({"日期": ["old"], "收盘": [1.0]}))
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, ProClient())
    monkeypatch.setattr("monitor.price_fetcher.get_storage", lambda: storage)

    result = fetch_history_df("002558", "A", min_periods=3)

    assert result is not None
    assert list(result["日期"]) == ["20260601", "20260602", "20260603"]
    assert list(result["收盘"]) == [25.0, 26.0, 27.0]


@pytest.mark.parametrize(
    ("stock_code", "market"),
    [("51030", "ETF"), ("1234", "HK"), ("600519", "UNKNOWN")],
)
def test_fetch_history_df_validates_code_and_market_before_source_selection(
    monkeypatch, stock_code, market
):
    monkeypatch.setattr("monitor.price_fetcher.get_storage", lambda: pytest.fail("source must not be selected"))
    with pytest.raises(ValueError):
        fetch_history_df(stock_code, market, min_periods=3)


def test_fetch_final_close_history_uses_hfq_storage_only(monkeypatch):
    storage = SimpleNamespace(
        load_history_data_stock=MagicMock(
            return_value=pd.DataFrame({COL_DATE: ["2026-06-03", "2026-06-02"], COL_CLOSE: [11.0, 10.0]})
        )
    )
    monkeypatch.setattr("monitor.price_fetcher.get_storage", lambda: storage)
    monkeypatch.setattr(
        "monitor.price_fetcher._fetch_a_share_daily_history_from_tushare",
        lambda *_args: pytest.fail("final-close history must not call Tushare"),
    )

    result = fetch_final_close_history_df("600519", date(2026, 6, 3), min_periods=2)

    storage.load_history_data_stock.assert_called_once_with(
        stock_id="600519",
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
        start_date="2026-05-28",
        end_date="2026-06-03",
    )
    assert result is not None
    assert list(result[COL_DATE]) == ["2026-06-02", "2026-06-03"]


def test_fetch_final_close_history_returns_none_for_short_storage_result(monkeypatch):
    storage = SimpleNamespace(
        load_history_data_stock=MagicMock(return_value=pd.DataFrame({COL_DATE: ["2026-06-03"], COL_CLOSE: [11.0]}))
    )
    monkeypatch.setattr("monitor.price_fetcher.get_storage", lambda: storage)

    assert fetch_final_close_history_df("600519", date(2026, 6, 3), min_periods=2) is None
