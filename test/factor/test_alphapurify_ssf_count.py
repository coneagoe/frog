import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import factor.alphapurify_ssf_count as alphapurify_ssf_count  # noqa: E402
from common.const import COL_CLOSE, COL_DATE, COL_STOCK_ID  # noqa: E402


def _make_price_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2024-01-02", periods=5),
            COL_CLOSE: [10.0, 10.2, 10.4, 10.5, 10.8],
        }
    )


def _make_top10_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "股票代码": ["000001", "000001", "000001"],
            "公告日期": pd.to_datetime(["2024-03-31", "2024-03-31", "2023-12-31"]),
            "股东名称": ["全国社保基金一一八组合", "全国社保基金五零三组合", "全国社保基金一一八组合"],
            "占总流通股本持股比例": [1.5, 0.6, 1.2],
        }
    )


def test_main_loads_ssf_count_panel_and_writes_report(tmp_path, monkeypatch):
    stock_info = pd.DataFrame({COL_STOCK_ID: ["000001"]})
    storage = SimpleNamespace(
        load_general_info_stock=lambda: stock_info,
        load_top10_floatholders_history=lambda stock_id, limit_ann_dates=12: _make_top10_history(),
        load_history_data_stock=lambda stock_id, period, adjust, start_date=None, end_date=None: _make_price_history(),
    )
    monkeypatch.setattr(alphapurify_ssf_count, "get_storage", lambda: storage)

    captured = {}

    class FakeFigure:
        def write_html(self, path):
            Path(path).write_text("ok", encoding="utf-8")

    class FakeFactorAnalyzer:
        def __init__(self, base_df, trade_date_col, symbol_col, price_col, factor_name, research_cfg=None, analysis_cfg=None):
            captured["base_df"] = base_df.copy()
            captured["factor_name"] = factor_name

        def run(self):
            captured["run_called"] = True

        def create_single_fac_ic_sheet(self):
            return FakeFigure()

    monkeypatch.setattr(alphapurify_ssf_count, "FactorAnalyzer", FakeFactorAnalyzer)

    output_path = tmp_path / "ssf_count_ic.html"
    code = alphapurify_ssf_count.main(["--max-stocks", "1", "--report-html", str(output_path)])

    assert code == 0
    assert captured["run_called"] is True
    assert captured["factor_name"] == "ssf_count"
    assert not captured["base_df"].empty
    assert output_path.exists()
