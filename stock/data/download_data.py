from datetime import datetime
# import logging
import os
import akshare as ak
import pandas as pd
import retrying
from stock.const import (
    COL_DATE,
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)
from stock.common import (
    get_stock_general_info_path,
    get_etf_general_info_path,
    get_stock_data_path_1d,
    get_stock_data_path_1w,
    get_stock_data_path_1M,
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
def download_history_data_etf(etf_id: str, period: str, start_date: str, end_date: str,
                              adjust="qfq"):
    assert period in ['daily', 'week', 'month']
    assert adjust in ['', 'qfq', 'hfq']

    etf_file_name = f"{etf_id}_{adjust}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), etf_file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), etf_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), etf_file_name)

    if not os.path.exists(data_path):
        try:
            df = ak.fund_etf_hist_em(symbol=etf_id, period=period,
                                     adjust=adjust)
            assert not df.empty, f"download history data {etf_id} fail, please check"

            df.to_csv(data_path, encoding='utf_8_sig', index=False)
        except KeyError:
            df = ak.fund_money_fund_info_em(etf_id)
            assert not df.empty, f"download history data {etf_id} fail, please check"
            df = df.rename(columns={'净值日期': COL_DATE, '每万份收益': COL_CLOSE})

            # 为回测调整数据
            df = df.rename(columns={'净值日期': COL_DATE, '每万份收益': COL_CLOSE})
            df[COL_OPEN] = df[COL_CLOSE]
            df[COL_HIGH] = df[COL_CLOSE]
            df[COL_LOW] = df[COL_CLOSE]
            df[COL_VOLUME] = 0
            df = df[[COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME] +
                    [x for x in df.columns if x not in [COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME]]]

            df.to_csv(data_path, encoding='utf_8_sig', index=False)
    else:
        end_date_ts0 = pd.Timestamp(end_date)
        df = pd.read_csv(data_path, encoding='utf_8_sig')
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])

        if end_date_ts0 <= df[COL_DATE].iloc[-1]:
            return
        else:
            start_date_ts1 = df[COL_DATE].iloc[-1] + pd.Timedelta(days=1)
            end_date_ts1 = pd.Timestamp(datetime.today().strftime('%Y-%m-%d'))
            try:
                df0 = ak.fund_etf_hist_em(symbol=etf_id, period=period,
                                          start_date=start_date_ts1.strftime('%Y%m%d'),
                                          end_date=end_date_ts1.strftime('%Y%m%d'),
                                          adjust=adjust)
                assert not df0.empty, f"download history data {etf_id} fail, please check"

                df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
                df = pd.concat([df, df0], ignore_index=True)
                df = df.sort_values(by=[COL_DATE], ascending=True)
                df = df.drop_duplicates(subset=[COL_DATE])
                df.to_csv(data_path, encoding='utf_8_sig', index=False)
            except KeyError:
                df = ak.fund_money_fund_info_em(etf_id)
                assert not df.empty, f"download history data {etf_id} fail, please check"

                # 为回测调整数据
                df = df.rename(columns={'净值日期': COL_DATE, '每万份收益': COL_CLOSE})
                df[COL_OPEN] = df[COL_CLOSE]
                df[COL_HIGH] = df[COL_CLOSE]
                df[COL_LOW] = df[COL_CLOSE]
                df[COL_VOLUME] = 0
                df = df[[COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME] +
                        [x for x in df.columns if x not in [COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME]]]

                df.to_csv(data_path, encoding='utf_8_sig', index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_us_index(index: str, period: str,
                                   start_date: str, end_date: str):
    """
    :param index: str, one of [".IXIC", ".DJI", ".INX"]
        .IXIC: NASDAQ Composite
        .DJI: Dow Jones Industrial Average
        .INX: S&P 500
    :return:
    """
    assert index in [".IXIC", ".DJI", ".INX"]
    assert period in ['daily', 'week', 'month']

    index_file_name = f"{index}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), index_file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), index_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), index_file_name)

    if not os.path.exists(data_path):
        df = ak.index_us_stock_sina(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.rename(columns={'date': COL_DATE, 'close': COL_CLOSE})
        df.to_csv(data_path, encoding='utf_8_sig', index=False)

        return

    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if end_date_ts0 <= df[COL_DATE].iloc[-1]:
        return
    else:
        df = ak.index_us_stock_sina(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.rename(columns={'date': COL_DATE, 'close': COL_CLOSE})
        df.to_csv(data_path, encoding='utf_8_sig', index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_stock(stock_id: str, period: str, start_date: str, end_date: str,
                                adjust="qfq"):
    assert period in ['daily', 'week', 'month']
    assert adjust in ['', 'qfq', 'hfq']

    stock_file_name = f"{stock_id}_{adjust}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), stock_file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), stock_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), stock_file_name)

    if not os.path.exists(data_path):
        df = ak.stock_zh_a_hist(symbol=stock_id, period=period,
                                adjust=adjust)
        assert not df.empty, f"download history data {stock_id} fail, please check"

        df.to_csv(data_path, encoding='utf_8_sig', index=False)
        return

    # start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if end_date_ts0 <= df[COL_DATE].iloc[-1]:
        return
    else:
        start_date_ts1 = df[COL_DATE].iloc[-1] + pd.Timedelta(days=1)
        end_date_ts1 = pd.Timestamp(datetime.today().strftime('%Y-%m-%d'))
        df0 = ak.stock_zh_a_hist(symbol=stock_id, period=period,
                                start_date=start_date_ts1.strftime('%Y%m%d'),
                                end_date=end_date_ts1.strftime('%Y%m%d'),
                                adjust=adjust)
        assert not df0.empty, f"download history data {stock_id} fail, please check"

        df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
        df = pd.concat([df, df0], ignore_index=True)
        df = df.sort_values(by=[COL_DATE], ascending=True)
        df = df.drop_duplicates(subset=[COL_DATE])
        df.to_csv(data_path, encoding='utf_8_sig', index=False)
