import logging
import os
import re
from datetime import datetime
from enum import Enum

import akshare as ak
import pandas as pd
import retrying

from stock.common import (
    get_etf_general_info_path,
    get_hk_ggt_stock_general_info_path,
    get_stock_data_path_1d,
    get_stock_data_path_1M,
    get_stock_data_path_1w,
    get_stock_general_info_path,
)
from stock.const import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_VOLUME,
)

from . import AdjustType

pattern_stock_id = r"60|00|30|68"


class PeriodType(Enum):
    DAILY = "daily"
    WEEKLY = "week"
    MONTHLY = "month"


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_general_info_stock_ak():
    df = ak.stock_info_a_code_name()
    df = df.loc[df["code"].str.match(pattern_stock_id)]
    df = df.rename(columns={"code": COL_STOCK_ID, "name": COL_STOCK_NAME})
    df.to_csv(get_stock_general_info_path(), encoding="utf_8_sig", index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_general_info_etf_ak():
    df = ak.fund_name_em()
    df.to_csv(get_etf_general_info_path(), encoding="utf_8_sig", index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_general_info_hk_ggt_stock_ak():
    df = ak.stock_hk_ggt_components_em()
    df = df.loc[:, ["代码", "名称"]]
    df = df.rename(columns={"代码": COL_STOCK_ID, "名称": COL_STOCK_NAME})
    df.to_csv(get_hk_ggt_stock_general_info_path(), encoding="utf_8_sig", index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_etf_ak(
    etf_id: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    try:
        df = ak.fund_etf_hist_em(
            symbol=etf_id, period=period.value[0], adjust=adjust.value[0]
        )
        assert not df.empty, f"download history data {etf_id} fail, please check"

        return df
    except KeyError:
        df = ak.fund_money_fund_info_em(etf_id)
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

        return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
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
    assert not df.empty, f"download history data {index} fail, please check"

    df = df.rename(columns={"date": COL_DATE, "close": COL_CLOSE})
    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_stock_ak(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    assert re.match(r"\d{6}", stock_id)

    df = ak.stock_zh_a_hist(symbol=stock_id, period=period, adjust=adjust)
    assert not df.empty, f"download history data {stock_id} fail, please check"

    return df


@retrying.retry(wait_fixed=5000, stop_max_attempt_number=5)
def download_history_data_stock_hk_ak(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.HFQ,
):
    assert re.match(r"\d{5}", stock_id)

    file_name = f"{stock_id}_{adjust}.csv"
    if period == "daily":
        data_path = os.path.join(get_stock_data_path_1d(), file_name)
    elif period == "week":
        data_path = os.path.join(get_stock_data_path_1w(), file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), file_name)

    if not os.path.exists(data_path):
        df = ak.stock_hk_hist(
            symbol=stock_id,
            period=period,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust=adjust,
        )
        df = df.rename(
            columns={
                "日期": COL_DATE,
                "开盘": COL_OPEN,
                "收盘": COL_CLOSE,
                "最高": COL_HIGH,
                "最低": COL_LOW,
                "成交量": COL_VOLUME,
            }
        )
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])
        df.to_csv(data_path, encoding="utf_8_sig", index=False)
        return

    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding="utf_8_sig")
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])
    if end_date_ts0 <= df[COL_DATE].iloc[-1]:
        return

    start_date_ts1 = df[COL_DATE].iloc[-1] + pd.Timedelta(days=1)
    end_date_ts1 = pd.Timestamp(datetime.today().strftime("%Y-%m-%d"))
    try:
        df0 = ak.stock_hk_hist(
            symbol=stock_id,
            period=period,
            start_date=start_date_ts1.strftime("%Y%m%d"),
            end_date=end_date_ts1.strftime("%Y%m%d"),
            adjust=adjust,
        )
    except Exception as e:
        logging.warning(f"stock_id: {stock_id}, {e}")
        raise e

    if df0.empty:
        logging.warning(f"download history data {stock_id} fail, please check")
        return

    df0 = df0.rename(
        columns={
            "日期": COL_DATE,
            "开盘": COL_OPEN,
            "收盘": COL_CLOSE,
            "最高": COL_HIGH,
            "最低": COL_LOW,
            "成交量": COL_VOLUME,
        }
    )
    df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
    df = (
        pd.concat([df, df0], ignore_index=True)
        .sort_values(by=COL_DATE)
        .drop_duplicates(subset=[COL_DATE])
    )
    df.to_csv(data_path, encoding="utf_8_sig", index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_a_index(
    index: str, period: str, start_date: str, end_date: str
):
    assert period in ["daily", "week", "month"]

    file_name = f"{index}.csv"
    if period == "daily":
        data_path = os.path.join(get_stock_data_path_1d(), file_name)
    elif period == "week":
        data_path = os.path.join(get_stock_data_path_1w(), file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), file_name)

    if not os.path.exists(data_path):
        df = ak.stock_zh_index_daily_em(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.iloc[:, :6]
        df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
        df.to_csv(data_path, encoding="utf_8_sig", index=False)
        return

    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding="utf_8_sig")
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if end_date_ts0 <= df[COL_DATE].iloc[-1]:
        return
    else:
        df = ak.stock_zh_index_daily_em(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.iloc[:, :6]
        df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
        df.to_csv(data_path, encoding="utf_8_sig", index=False)
