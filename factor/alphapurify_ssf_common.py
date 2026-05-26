from typing import List

import pandas as pd

from common.const import (
    COL_ANN_DATE,
    COL_DATE,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_STOCK_ID,
)

# exported factor names
SSF_FACTOR_COUNT = "ssf_factor_count"
SSF_FACTOR_RATIO = "ssf_factor_ratio"
SSF_FACTOR_RATIO_CHANGE = "ssf_factor_ratio_change"


def build_ssf_factor_history(history_df: pd.DataFrame) -> pd.DataFrame:
    """
    Given top10 floatholders history records, compute per-announcement-date SSF counts,
    total SSF holding ratio, and ratio change vs previous announcement.
    We identify SSF holders by presence of the substring "社保基金" in the holder name.
    Returns a dataframe with columns: COL_ANN_DATE, SSF_FACTOR_COUNT, SSF_FACTOR_RATIO, SSF_FACTOR_RATIO_CHANGE
    """
    if history_df is None or history_df.empty:
        return pd.DataFrame(columns=[COL_ANN_DATE, SSF_FACTOR_COUNT, SSF_FACTOR_RATIO, SSF_FACTOR_RATIO_CHANGE])

    df = history_df.copy()
    # identify SSF holders by substring
    mask = df[COL_FLOAT_HOLDER_NAME].astype(str).str.contains("社保基金")
    ssf = df[mask]

    if ssf.empty:
        return pd.DataFrame(columns=[COL_ANN_DATE, SSF_FACTOR_COUNT, SSF_FACTOR_RATIO, SSF_FACTOR_RATIO_CHANGE])

    grouped = (
        ssf.groupby(COL_ANN_DATE)
        .agg(
            **{
                SSF_FACTOR_COUNT: (COL_FLOAT_HOLDER_NAME, lambda x: x.nunique()),
                SSF_FACTOR_RATIO: (COL_FLOAT_HOLDER_HOLD_RATIO, "sum"),
            }
        )
        .reset_index()
        .sort_values(COL_ANN_DATE)
    )

    grouped[SSF_FACTOR_RATIO_CHANGE] = grouped[SSF_FACTOR_RATIO].diff()

    return grouped


def build_stock_factor_panel(
    history_df: pd.DataFrame,
    stock_id: str,
    factor_history_df: pd.DataFrame,
    factor_name: str,
) -> pd.DataFrame:
    """
    For a single stock, join daily history with the announcement-based factor history by
    forward-filling the latest announced factor value to each trading date (merge_asof).
    """
    if history_df is None or history_df.empty:
        return pd.DataFrame()

    df = history_df.copy()
    df = df.sort_values(COL_DATE).reset_index(drop=True)

    if factor_history_df is None or factor_history_df.empty:
        # still return symbol column so caller can decide to skip
        df_result = df.copy()
        df_result["symbol"] = stock_id
        df_result[factor_name] = pd.NA
        return df_result

    fh = factor_history_df[[COL_ANN_DATE, factor_name]].drop_duplicates().sort_values(COL_ANN_DATE)

    merged = pd.merge_asof(
        df,
        fh,
        left_on=COL_DATE,
        right_on=COL_ANN_DATE,
        direction="backward",
    )

    merged["symbol"] = stock_id

    return merged


def build_ssf_factor_panel_from_db(
    storage,
    factor_name: str,
    start_date: str,
    end_date: str,
    max_stocks: int = 100,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    Build a combined panel for many stocks by loading stock list and per-stock histories from storage.
    Skips stocks or rows where the requested factor is missing (NaN).
    """
    stocks = storage.load_general_info_stock()
    if stocks is None or stocks.empty:
        return pd.DataFrame()

    panels: List[pd.DataFrame] = []

    for stock_id in stocks[COL_STOCK_ID].tolist()[:max_stocks]:
        top10 = storage.load_top10_floatholders_history(stock_id, limit_ann_dates=12)
        factor_history = build_ssf_factor_history(top10)
        if factor_history is None or factor_history.empty:
            continue

        # call storage.load_history_data_stock with positional args to match various implementations
        history = storage.load_history_data_stock(stock_id, "daily", adjust, start_date, end_date)
        stock_panel = build_stock_factor_panel(history_df=history, stock_id=stock_id, factor_history_df=factor_history, factor_name=factor_name)
        if stock_panel is None or stock_panel.empty:
            continue

        # drop rows without the factor value
        if factor_name not in stock_panel.columns:
            continue

        stock_panel = stock_panel[stock_panel[factor_name].notna()].copy()
        if stock_panel.empty:
            continue

        panels.append(stock_panel)

    if not panels:
        return pd.DataFrame()

    combined = pd.concat(panels, ignore_index=True)
    return combined
