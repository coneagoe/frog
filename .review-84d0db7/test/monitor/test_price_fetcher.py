import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from monitor.price_fetcher import fetch_current_price, fetch_price


def _install_tushare_stub(monkeypatch, pro_client):
    ts_stub = SimpleNamespace(pro_api=lambda token: pro_client)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)


def test_fetch_price_a_share_uses_rt_k(monkeypatch):
    pro_client = SimpleNamespace(
        rt_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 1800.5}])
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("600519", "A") == 1800.5


def test_fetch_price_hk_uses_rt_hk_k(monkeypatch):
    pro_client = SimpleNamespace(
        rt_hk_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 64.85}])
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("00001", "HK") == 64.85


def test_fetch_price_returns_nan_without_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    assert np.isnan(fetch_price("600519", "A"))


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


def test_fetch_price_a_5xx_is_sz(monkeypatch):
    # Ensure market="A" does NOT treat 5-prefix ETF codes as Shanghai (.SH)
    def rt_k(ts_code):
        close = 1.0 if ts_code.endswith(".SZ") else 2.0
        return pd.DataFrame([{"ts_code": ts_code, "close": close}])

    pro_client = SimpleNamespace(rt_k=rt_k)
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("510300", "A") == 1.0
