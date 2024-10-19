from datetime import datetime
import logging
import os
import akshare as ak
import baostock as bs
from bs4 import BeautifulSoup
import pandas as pd
import requests
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
    get_hk_ggt_stock_general_info_path,
    get_stock_300_ingredients_path,
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


def download_general_info_hk_ggt_stock():
    df = ak.stock_hk_ggt_components_em()
    df = df.loc[:, [u'代码', u'名称']]
    df = df.rename(columns={u'代码': COL_STOCK_ID, u'名称': COL_STOCK_NAME})
    df.to_csv(get_hk_ggt_stock_general_info_path(), encoding='utf_8_sig', index=False)


def download_general_info_etf():
    df = ak.fund_name_em()
    df.to_csv(get_etf_general_info_path(), encoding='utf_8_sig', index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_general_info_index():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:107.0) Gecko/20100101 Firefox/107.0"
    }

    url = 'http://quote.eastmoney.com/center/gridlist.html#index_sh'

    try:
        resp = requests.get(url, headers=headers)
    except requests.exceptions.ConnectionError as e:
        logging.error(e.args)
        raise e

    if resp.status_code != requests.codes.ok:
        logging.error(f"download index fail: {resp.status_code}")
        return False

    bs = BeautifulSoup(resp.content, 'lxml')
    print(bs.prettify())

    # df.to_csv(get_stock_general_info_path(), encoding='utf_8_sig', index=False)


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
                        [x for x in df.columns if x not in [COL_DATE,
                                                            COL_CLOSE,
                                                            COL_OPEN,
                                                            COL_HIGH,
                                                            COL_LOW,
                                                            COL_VOLUME]]]

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

    file_name = f"{index}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), file_name)

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

    file_name = f"{stock_id}_{adjust}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), file_name)

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


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_history_data_a_index(index: str, period: str, start_date: str, end_date: str):
    assert period in ['daily', 'week', 'month']

    file_name = f"{index}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), file_name)
    elif period == 'week':
        data_path = os.path.join(get_stock_data_path_1w(), file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), file_name)

    if not os.path.exists(data_path):
        df = ak.stock_zh_index_daily_em(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.iloc[:, :6]
        df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
        df.to_csv(data_path, encoding='utf_8_sig', index=False)
        return

    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if end_date_ts0 <= df[COL_DATE].iloc[-1]:
        return
    else:
        df = ak.stock_zh_index_daily_em(symbol=index)
        assert not df.empty, f"download history data {index} fail, please check"

        df = df.iloc[:, :6]
        df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
        df.to_csv(data_path, encoding='utf_8_sig', index=False)


def download_300_ingredients():
    start_date = datetime(2010, 1, 1)
    end_date = datetime.today()

    lg = bs.login()
    if lg.error_code != '0':
        logging.error(f"baostock login fail: {lg.error_msg}")
        return

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        file_path = os.path.join(get_stock_300_ingredients_path(), f'{date_str}.csv')
        
        if not os.path.exists(file_path):
            rs = bs.query_hs300_stocks(date=date_str)
            hs300_stocks = []
            while (rs.error_code == '0') & rs.next():
                hs300_stocks.append(rs.get_row_data())
            df = pd.DataFrame(hs300_stocks, columns=rs.fields)
            df.rename(columns={'code': COL_STOCK_ID, 'code_name': COL_STOCK_NAME}, inplace=True)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.replace('sh.', '').str.replace('sz.', '')
            df.to_csv(file_path, encoding='utf_8_sig', index=False)
        
        if current_date.month == 1 and current_date.day == 1:
            current_date = datetime(current_date.year, 7, 1)
        else:
            current_date = datetime(current_date.year + 1, 1, 1)

    bs.logout()


# result.to_csv("D:/hs300_stocks.csv", encoding="gbk", index=False)
# print(result)
