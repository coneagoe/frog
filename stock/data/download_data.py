import logging
import os
import akshare as ak
import pandas as pd
import retrying
from stock.common import (
    COL_DATE,
    COL_CLOSE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    get_stock_general_info_path,
    get_etf_general_info_path,
    get_stock_1d_path
)


pattern_stock_id = r'60|00|30|68'


# TODO
# def is_st(stock_id: str):
#     pass


def download_general_info_stock():
    df = ak.stock_info_a_code_name()
    df = df.loc[df['code'].str.match(pattern_stock_id)]
    df = df.rename(columns={'code': COL_STOCK_ID, 'name': COL_STOCK_NAME})
    df.to_csv(get_stock_general_info_path(), encoding='utf_8_sig', index=False)


def download_general_info_etf():
    df = ak.fund_name_em()
    df.to_csv(get_etf_general_info_path(), encoding='utf_8_sig', index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_stock(stock_id: str, period: str, start_date: str, end_date: str,
                                adjust="qfq") -> pd.DataFrame | None:
    df = ak.stock_zh_a_hist(symbol=stock_id, period=period,
                            start_date=start_date, end_date=end_date,
                            adjust=adjust)
    if df.empty:
        logging.warning(f"No data available for stock({stock_id}) from {start_date} to {end_date}.")
        return None

    return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_etf(security_id: str, period: str, start_date: str, end_date: str,
                              adjust="qfq") -> pd.DataFrame | None:
    try:
        df = ak.fund_etf_hist_em(symbol=security_id, period=period,
                                 start_date=start_date, end_date=end_date,
                                 adjust=adjust)
        return df
    except KeyError:
        start_timestamp = pd.Timestamp(start_date)
        end_timestamp = pd.Timestamp(end_date)
        df = ak.fund_money_fund_info_em(security_id)
        df[u'净值日期'] = pd.to_datetime(df[u'净值日期'])
        df = df[(df[u'净值日期'] >= start_timestamp) & (df[u'净值日期'] <= end_timestamp)]
        df = df.rename(columns={'净值日期': COL_DATE, '每万份收益': COL_CLOSE})
        df[COL_CLOSE] = df[COL_CLOSE].astype(float)
        df = df.set_index(COL_DATE)
        df = df.sort_index(ascending=True)
        df = df.reset_index()

        return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_us_index(security_id: str) -> pd.DataFrame:
    """
    :param security_id: str, one of [".IXIC", ".DJI", ".INX"]
        .IXIC: NASDAQ Composite
        .DJI: Dow Jones Industrial Average
        .INX: S&P 500
    :return:
    """
    df = ak.index_us_stock_sina(symbol=security_id)
    df = df.rename(columns={'date': COL_DATE, 'close': COL_CLOSE})
    return df


def download_history_stock_1d(stock_id: str, start_date: str, end_date: str):
    data_path = os.path.join(get_stock_1d_path(), f"{stock_id}.csv")
    if not os.path.exists(data_path):
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")

        if df.empty:
            logging.warning(f"download history data {stock_id} fail, please check")
            return False

        df.to_csv(data_path, encoding='utf_8_sig', index=False)

        return True

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if start_date_ts0 < df[COL_DATE].iloc[0]:
        end_date_ts1 = df[COL_DATE].iloc[0] - pd.Timedelta(days=1)
        df0 = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                 start_date=start_date, end_date=end_date_ts1.strftime('%Y%m%d'),
                                 adjust="")
        df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
        df = pd.concat([df, df0], ignore_index=True)

    if end_date_ts0 > df[COL_DATE].iloc[-1]:
        start_date_ts1 = df[COL_DATE].iloc[-1] + pd.Timedelta(days=1)
        df0 = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                 start_date=start_date_ts1.strftime('%Y%m%d'), end_date=end_date,
                                 adjust="")
        df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
        df = pd.concat([df, df0], ignore_index=True)

    df = df.sort_values(by=[COL_DATE], ascending=True)
    df = df.drop_duplicates(subset=[COL_DATE])

    df.to_csv(data_path, encoding='utf_8_sig', index=False)
