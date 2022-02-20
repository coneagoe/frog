# -*- coding: utf-8 -*-
import os
import logging
import pandas as pd
from pathlib import Path
import json
import re
import functools
import aiohttp
import asyncio
import aiofiles
from datetime import datetime
import requests
import numpy as np
import pandas_market_calendars as mcal
from common import *
from proxy import get_proxy


# logging.getLogger('aiohttp.client').setLevel(logging.DEBUG)
enable_proxy = False


headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36'
}

timeout = aiohttp.ClientTimeout(total=5)

market = mcal.get_calendar('XSHG')
holidays = list(market.holidays().holidays)


def retry(times):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            for i in range(times):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if str(e) != "":
                        logging.error(e)
                await asyncio.sleep(3)
            return None
        return wrapped
    return wrapper


# class TooManyTriesException(BaseException):
#     pass


# def retry(times):
    # def func_wrapper(func):
        # @functools.wraps(func)
        # async def wrapper(*args, **kwargs):
            # for time in range(times):
                # print('times:', time + 1)
                # # noinspection
                # # PyBroadException
                # try:
                    # return await func(*args, **kwargs)
                # except Exception as exc:
                    # pass
                # raise TooManyTriesException() from exc
            # return wrapper
#         return func_wrapper


def check_path():
    path = Path(fund_data_path)
    if not path.exists():
        path.mkdir(parents=True)


def is_older_than_30_days(f):
    dt = datetime.now() - datetime.fromtimestamp(os.path.getmtime(f))
    return dt.days > 30


class TianTianCrawler(object):
    def __init__(self):
        self.i = 0
        self.max_workers = 8
        self.worker_count = 0


    def get_all_fund_general_info(self):
        if not os.path.exists(all_general_info_csv) or \
                is_older_than_30_days(all_general_info_csv):
            asyncio.run(download_all_fund_general_info())

        if not os.path.exists(all_general_info_csv):
            return None

        return pd.read_csv(all_general_info_csv)


    async def download_all_fund_general_info(self):
        async with aiohttp.ClientSession(headers=headers) as session:
            fund_dict_path = 'http://fund.eastmoney.com/js/fundcode_search.js'
            async with session.get(fund_dict_path) as resp:
                if resp.status == 200:
                    # you have to download all fund general info first,
                    # writng csv asynchronously is meaningless.
                    # (only one task at that time)
                    tmp = re.sub(r'^var\s*r\s*=\s*', '', await resp.text()).strip(';')
                    tmp = json.loads(tmp)
                    df = pd.DataFrame(tmp,
                                      columns=[col_fund_id, col_pinyin_abbreviation,
                                               col_fund_name, col_fund_type, col_pinyin])
                    df.to_csv(all_general_info_csv, encoding='utf_8_sig', index=False)
                else:
                    logging.warning(f"status: {resp.status}")


    def calculate_page_count(self, start_date: str, end_date: str) -> int:
        item_per_page = 20
        sdate = datetime.strptime(start_date, '%Y-%m-%d')
        edate = datetime.strptime(end_date, '%Y-%m-%d')
        days = np.busday_count(sdate.date(), edate.date(), holidays=holidays)
        page_count = days // item_per_page
        if days % item_per_page:
            page_count += 1

        return page_count


    async def do_download_history_netvalues(self, fund_id: str, start_date: str, end_date: str):
        df = None
        page_count = self.calculate_page_count(start_date, end_date)
        print(f"download_history_netvalues: page_count = {page_count}")

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            tasks = [self.fetch_history_netvalues(fund_id, session, start_date, end_date, i) for i in range(1, page_count + 1)]
            pages = await asyncio.gather(*tasks)
            for page in pages:
                if page is not None:
                    df0 = pd.read_html(page, encoding='utf-8')[0]
                    if df is None:
                        df = df0
                    else:
                        df = df.append(df0, ignore_index=True)
        return df


    @retry(times=10)
    async def fetch(self, session, url, params):
        if enable_proxy:
            while True:
                if self.worker_count >= self.max_workers:
                    await asyncio.sleep(3)
                else:
                    self.worker_count += 1
                    break


        result = None
        proxy = get_proxy()
        # logging.info(f"fetch: params: {params}, proxy: {proxy}, worker: {self.worker_count}")

        async with session.get(url, params=params, proxy=proxy['http']) as resp:
            if resp.status != 200:
                raise RuntimeError(f"status: {resp.status}, {url}, {params}")
            result = await resp.text()

        if enable_proxy: self.worker_count -= 1
        return result


    # http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2001-12-18&edate=2020-05-18&per=20&page=1
    async def fetch_history_netvalues(self, fund_id: str,
                                      session,
                                      start_date: str,
                                      end_date: str,
                                      page: int):
        '''
        :param start_date: YYYY-MM-DD
        :param end_date: YYYY-MM-DD
        :return:
        '''
        history_url = "http://fund.eastmoney.com/f10/F10DataApi.aspx"
        params = {'type': 'lsjz', 'code': fund_id, 'per': 20, 'page': page}
        if start_date: params['sdate'] = start_date
        if end_date: params['edate'] = end_date

        return await self.fetch(session, history_url, params)


    def download_directly(self, url, params):
        result = None
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            result = resp.content
        else:
            logging.warning(f"status: {resp.status_code}, fund_id = {fund_id}, page = {page}")
        return result


    async def save_history_netvalues(self, output, df):
        print("save_history_netvalues: start")
        if df is not None:
            async with aiofiles.open(output, mode='w') as f:
                tmp = df.to_csv(encoding='utf_8_sig', index=False)
                await f.write(tmp)


    def download_history_netvalues(self, fund_id: str, start_date: str, end_date: str):
        output_file_name = os.path.join(history_netvalue_path, f"{fund_id}.csv")
        async def foo():
            df = await self.do_download_history_netvalues(fund_id, start_date, end_date)
            await self.save_history_netvalues(output_file_name, df)
        asyncio.run(foo())


