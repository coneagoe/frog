import re

import akshare as ak
import pandas as pd
import retrying

from common.const import (
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)
from utility import change_proxy

pattern_a_stock_id = r"60|00|30|68"


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_general_info_stock_ak() -> pd.DataFrame:
    df = ak.stock_info_a_code_name()
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    df = df.loc[df["code"].str.match(pattern_a_stock_id)]
    df = df.rename(columns={"code": COL_STOCK_ID, "name": COL_STOCK_NAME})
    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_general_info_etf_ak() -> pd.DataFrame:
    df = ak.fund_name_em()
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_general_info_hk_ggt_stock_ak() -> pd.DataFrame:
    df = ak.stock_hk_ggt_components_em()
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    df = df[["代码", "名称"]]
    df = df.rename(columns={"代码": COL_STOCK_ID, "名称": COL_STOCK_NAME})
    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_history_data_etf_ak(
    etf_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    try:
        df = ak.fund_etf_hist_em(
            symbol=etf_id, period=period.value, adjust=adjust.value
        )
        assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
        assert not df.empty, f"download history data {etf_id} fail, please check"
    except KeyError:
        df = ak.fund_money_fund_info_em(etf_id)
        assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
        assert not df.empty, f"download history data {etf_id} fail, please check"
        df = df.rename(columns={"净值日期": COL_DATE, "每万份收益": COL_CLOSE})

        # 为回测调整数据
        df = df.rename(columns={"净值日期": COL_DATE, "每万份收益": COL_CLOSE})
        df[COL_OPEN] = df[COL_CLOSE]
        df[COL_HIGH] = df[COL_CLOSE]
        df[COL_LOW] = df[COL_CLOSE]
        df[COL_VOLUME] = 0
        df = df[
            [COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME]
            + [
                x
                for x in df.columns
                if x
                not in [
                    COL_DATE,
                    COL_CLOSE,
                    COL_OPEN,
                    COL_HIGH,
                    COL_LOW,
                    COL_VOLUME,
                ]
            ]
        ]

    df["date"] = pd.to_datetime(df[COL_DATE])
    mask = (df["date"] >= pd.to_datetime(start_date)) & (
        df["date"] <= pd.to_datetime(end_date)
    )
    df = df.loc[mask].copy()
    df.drop(columns=["date"], inplace=True)

    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_history_data_us_index_ak(
    index: str, period: PeriodType = PeriodType.DAILY
) -> pd.DataFrame:
    """
    :param index: str, one of [".IXIC", ".DJI", ".INX"]
        .IXIC: NASDAQ Composite
        .DJI: Dow Jones Industrial Average
        .INX: S&P 500
    :return:
    """
    assert index in [".IXIC", ".DJI", ".INX"]

    df = ak.index_us_stock_sina(symbol=index)
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert not df.empty, f"download history data {index} fail, please check"

    df = df.rename(columns={"date": COL_DATE, "close": COL_CLOSE})
    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_history_data_stock_ak(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    assert re.match(r"^\d{6}$", stock_id), "Stock ID must be 6 digits."

    df = ak.stock_zh_a_hist(
        symbol=stock_id,
        period=period.value,
        adjust=adjust.value,
    )
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert not df.empty, f"download history data {stock_id} fail, please check"

    return df


@retrying.retry(wait_fixed=5000, stop_max_attempt_number=5)
@change_proxy
def download_history_data_stock_hk_ak(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.HFQ,
) -> pd.DataFrame:
    assert re.match(r"\d{5}", stock_id)

    df = ak.stock_hk_hist(
        symbol=stock_id,
        period=period.value,
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust=adjust.value,
    )
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert not df.empty, f"download history data {stock_id} fail, please check"

    df[COL_DATE] = pd.to_datetime(df[COL_DATE])
    df[COL_STOCK_ID] = stock_id

    df = df.rename(columns={"涨跌幅": COL_CHANGE_RATE, "换手率": COL_TURNOVER_RATE})

    numeric_columns = df.select_dtypes(include=["number"]).columns
    df[numeric_columns] = df[numeric_columns].fillna(0)

    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
@change_proxy
def download_history_data_a_index_ak(
    index: str, start_date: str, end_date: str
) -> pd.DataFrame:
    df = ak.stock_zh_index_daily_em(symbol=index)
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert not df.empty, f"download history data {index} fail, please check"

    # df = df.iloc[:, :6]
    # df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
    return df
