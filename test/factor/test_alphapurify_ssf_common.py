import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from common.const import (  # noqa: E402
    COL_ANN_DATE,
    COL_CLOSE,
    COL_DATE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_STOCK_ID,
)
from factor.alphapurify_ssf_common import (  # noqa: E402
    SSF_FACTOR_COUNT,
    SSF_FACTOR_RATIO,
    SSF_FACTOR_RATIO_CHANGE,
    build_ssf_factor_history,
    build_ssf_factor_panel_from_db,
    build_stock_factor_panel,
)


def _make_top10_history_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_STOCK_ID: ["000001"] * 5,
            COL_ANN_DATE: pd.to_datetime(
                ["2024-03-31", "2024-03-31", "2023-12-31", "2023-12-31", "2023-09-30"]
            ),
            COL_FLOAT_HOLDER_NAME: [
                "全国社保基金一一八组合",
                "全国社保基金五零三组合",
                "全国社保基金一一八组合",
                "香港中央结算有限公司",
                "全国社保基金四零一组合",
            ],
            COL_FLOAT_HOLDER_HOLD_AMOUNT: [1200.0, 500.0, 1000.0, 800.0, 700.0],
            COL_FLOAT_HOLDER_HOLD_RATIO: [1.5, 0.6, 1.2, 0.9, 0.8],
        }
    )


def _make_daily_history_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(["2024-01-05", "2024-02-05", "2024-04-10", "2024-04-11"]),
            COL_CLOSE: [10.0, 10.5, 11.0, 11.2],
        }
    )


def test_build_ssf_factor_history_computes_count_ratio_and_ratio_change():
    history = build_ssf_factor_history(_make_top10_history_df())

    latest = history.loc[history[COL_ANN_DATE] == pd.Timestamp("2024-03-31")].iloc[0]
    previous = history.loc[history[COL_ANN_DATE] == pd.Timestamp("2023-12-31")].iloc[0]

    assert latest[SSF_FACTOR_COUNT] == 2
    assert round(latest[SSF_FACTOR_RATIO], 4) == 2.1
    assert round(latest[SSF_FACTOR_RATIO_CHANGE], 4) == 0.9
    assert previous[SSF_FACTOR_COUNT] == 1
    assert round(previous[SSF_FACTOR_RATIO], 4) == 1.2


def test_build_stock_factor_panel_forward_fills_latest_announced_factor():
    factor_history = build_ssf_factor_history(_make_top10_history_df())
    panel = build_stock_factor_panel(
        history_df=_make_daily_history_df(),
        stock_id="000001",
        factor_history_df=factor_history,
        factor_name=SSF_FACTOR_RATIO,
    )

    assert panel["symbol"].tolist() == ["000001"] * 4
    assert panel[SSF_FACTOR_RATIO].tolist() == [1.2, 1.2, 2.1, 2.1]


def test_build_ssf_factor_panel_from_db_skips_empty_factor_rows():
    stock_info = pd.DataFrame({COL_STOCK_ID: ["000001"]})
    storage = SimpleNamespace(
        load_general_info_stock=lambda: stock_info,
        load_top10_floatholders_history=lambda stock_id, limit_ann_dates=12: _make_top10_history_df(),
        load_history_data_stock=lambda stock_id, period, adjust, start_date=None, end_date=None: (
            _make_daily_history_df()
        ),
    )

    panel = build_ssf_factor_panel_from_db(
        storage=storage,
        factor_name=SSF_FACTOR_RATIO_CHANGE,
        start_date="2024-01-01",
        end_date="2024-12-31",
        max_stocks=10,
        adjust="qfq",
    )

    assert not panel.empty
    assert panel[SSF_FACTOR_RATIO_CHANGE].notna().all()


def test_build_ssf_factor_history_first_ratio_change_is_nan():
    # first announcement has no prior, so ratio_change should be NaN
    history = build_ssf_factor_history(_make_top10_history_df())
    first_row = history.sort_values(COL_ANN_DATE).iloc[0]
    assert pd.isna(first_row[SSF_FACTOR_RATIO_CHANGE])


def test_build_stock_factor_panel_before_first_announcement_and_exact_match():
    # Prepare a factor history with an announcement that matches a trading date
    factor_history = pd.DataFrame(
        {
            COL_ANN_DATE: pd.to_datetime(["2024-03-31", "2024-04-10"]),
            SSF_FACTOR_RATIO: [2.1, 2.5],
        }
    )

    daily = pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(["2024-03-30", "2024-03-31", "2024-04-10"]),
            COL_CLOSE: [9.5, 10.0, 11.0],
        }
    )

    panel = build_stock_factor_panel(
        history_df=daily,
        stock_id="000001",
        factor_history_df=factor_history,
        factor_name=SSF_FACTOR_RATIO,
    )

    # date before first announcement -> NA
    assert pd.isna(panel.loc[panel[COL_DATE] == pd.Timestamp("2024-03-30"), SSF_FACTOR_RATIO].iloc[0])
    # announcement date equal to trading date -> exact value
    assert panel.loc[panel[COL_DATE] == pd.Timestamp("2024-03-31"), SSF_FACTOR_RATIO].iloc[0] == 2.1
    assert panel.loc[panel[COL_DATE] == pd.Timestamp("2024-04-10"), SSF_FACTOR_RATIO].iloc[0] == 2.5


def test_build_stock_factor_panel_with_empty_factor_history_returns_na():
    daily = _make_daily_history_df()
    empty_fh = pd.DataFrame(columns=[COL_ANN_DATE, SSF_FACTOR_RATIO])
    panel = build_stock_factor_panel(
        history_df=daily,
        stock_id="000001",
        factor_history_df=empty_fh,
        factor_name=SSF_FACTOR_RATIO,
    )

    assert "symbol" in panel.columns
    assert SSF_FACTOR_RATIO in panel.columns
    assert panel[SSF_FACTOR_RATIO].isna().all()


def test_build_ssf_factor_panel_from_db_handles_no_ssf():
    # storage returns top10 data without any "社保基金" substring
    stock_info = pd.DataFrame({COL_STOCK_ID: ["000002"]})

    def _non_ssf_top10(stock_id, limit_ann_dates=12):
        df = _make_top10_history_df().copy()
        df[COL_FLOAT_HOLDER_NAME] = ["Alpha Fund", "Beta Fund", "Gamma Fund", "Delta", "Epsilon"]
        return df

    storage = SimpleNamespace(
        load_general_info_stock=lambda: stock_info,
        load_top10_floatholders_history=lambda stock_id, limit_ann_dates=12: _non_ssf_top10(stock_id),
        load_history_data_stock=lambda stock_id, period, adjust, start_date=None, end_date=None: (
            _make_daily_history_df()
        ),
    )

    panel = build_ssf_factor_panel_from_db(
        storage=storage,
        factor_name=SSF_FACTOR_RATIO,
        start_date="2024-01-01",
        end_date="2024-12-31",
        max_stocks=10,
        adjust="qfq",
    )

    # No SSF in top10 -> no panels produced
    assert panel.empty
