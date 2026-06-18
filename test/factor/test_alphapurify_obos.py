import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import factor.alphapurify_obos as alphapurify_obos  # noqa: E402
from common.const import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_STOCK_ID,
)


def _make_history_df(rows: int = 60) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    closes = [100 + i * 0.2 for i in range(rows)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_CLOSE: closes,
            COL_HIGH: highs,
            COL_LOW: lows,
        }
    )


def test_main_loads_db_data_and_writes_ic_report(tmp_path, monkeypatch):
    stock_info = pd.DataFrame({COL_STOCK_ID: ["000001", "000002"]})

    history_map = {
        "000001": _make_history_df(),
        "000002": _make_history_df(),
    }

    storage = SimpleNamespace(
        load_general_info_stock=lambda: stock_info,
        load_history_data_stock=lambda stock_id, period, adjust, start_date=None, end_date=None: history_map[stock_id],
    )

    monkeypatch.setattr(alphapurify_obos, "get_storage", lambda: storage)

    captured = {}

    class FakeFigure:
        def write_html(self, path):
            Path(path).write_text("ok", encoding="utf-8")

    class FakeFactorAnalyzer:
        def __init__(
            self,
            base_df,
            trade_date_col,
            symbol_col,
            price_col,
            factor_name,
            research_cfg=None,
            analysis_cfg=None,
        ):
            captured["base_df"] = base_df.copy()
            captured["trade_date_col"] = trade_date_col
            captured["symbol_col"] = symbol_col
            captured["price_col"] = price_col
            captured["factor_name"] = factor_name

        def run(self):
            captured["run_called"] = True

        def create_single_fac_ic_sheet(self):
            captured["ic_sheet_called"] = True
            return FakeFigure()

    monkeypatch.setattr(alphapurify_obos, "FactorAnalyzer", FakeFactorAnalyzer)

    output_path = tmp_path / "obos_ic.html"
    code = alphapurify_obos.main(
        [
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-12-31",
            "--max-stocks",
            "2",
            "--report-html",
            str(output_path),
        ]
    )

    assert code == 0
    assert captured["run_called"] is True
    assert captured["ic_sheet_called"] is True
    assert output_path.exists()
    assert captured["trade_date_col"] == "datetime"
    assert captured["symbol_col"] == "symbol"
    assert captured["price_col"] == "close"
    assert captured["factor_name"] == "obos"
    assert not captured["base_df"].empty
