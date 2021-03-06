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
import numpy as np
import pandas_market_calendars as mcal
from bs4 import BeautifulSoup
import motor.motor_asyncio
from common import *
from proxy import get_proxy


# logging.getLogger('aiohttp.client').setLevel(logging.DEBUG)
worker_restrict = False
enable_proxy = False


headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36'
}

timeout = aiohttp.ClientTimeout(total=5)

market = mcal.get_calendar('XSHG')
holidays = list(market.holidays().holidays)

pattern_timestamp = re.compile(r'\d{4}-\d{2}-\d{2}')


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
        self.mongodb_client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = self.mongodb_client['fund']
        self.collection_general_info = self.db['general_info']


    @retry(times=10)
    async def fetch(self, session, url, params, checker):
        if worker_restrict:
            while True:
                if self.worker_count >= self.max_workers:
                    await asyncio.sleep(3)
                else:
                    self.worker_count += 1
                    break

        result = None
        proxy = None
        if enable_proxy:
            proxy = get_proxy()['http']

        async with session.get(url, params=params, proxy=proxy) as resp:
            if resp.status != 200:
                raise RuntimeError(f"status: {resp.status}, {url}, {params}")

            result = await resp.text()
            if not checker(result):
                raise RuntimeError(result)

        if worker_restrict: self.worker_count -= 1

        return result


    def get_all_fund_general_info(self):
        if not os.path.exists(all_general_info_csv) or \
                is_older_than_30_days(all_general_info_csv):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(download_all_fund_general_info())

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


    def download_history_netvalues(self, fund_id: str, start_date: str, end_date: str):
        output_file_name = os.path.join(history_netvalue_path, f"{fund_id}.csv")
        async def foo():
            df = await self.do_download_history_netvalues(fund_id, start_date, end_date)
            await self.save_history_netvalues(output_file_name, df)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(foo())


    async def do_download_history_netvalues(self, fund_id: str, start_date: str, end_date: str):
        df = None
        page_count = self.calculate_page_count(start_date, end_date)

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            tasks = [self.fetch_history_netvalues(session, fund_id, start_date, end_date, i)
                     for i in range(1, page_count + 1)]
            pages = await asyncio.gather(*tasks)
            for page in pages:
                if page is not None:
                    df0 = pd.read_html(page, encoding='utf-8')[0]
                    if df is None:
                        df = df0
                    else:
                        df = df.append(df0, ignore_index=True)
        return df


    async def fetch_history_netvalues(self,
                                      session,
                                      fund_id: str,
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

        return await self.fetch(session, history_url, params, self.history_netvalue_checker)


    async def save_history_netvalues(self, output, df):
        print("save_history_netvalues: start")
        if df is not None:
            async with aiofiles.open(output, mode='w') as f:
                tmp = df.to_csv(encoding='utf_8_sig', index=False)
                await f.write(tmp)


    def calculate_page_count(self, start_date: str, end_date: str) -> int:
        item_per_page = 20
        sdate = datetime.strptime(start_date, '%Y-%m-%d')
        edate = datetime.strptime(end_date, '%Y-%m-%d')
        days = np.busday_count(sdate.date(), edate.date(), holidays=holidays)
        page_count = days // item_per_page
        if days % item_per_page:
            page_count += 1

        return page_count


    def history_netvalue_checker(self, page):
        df = pd.read_html(page, encoding='utf-8')[0]
        return pattern_timestamp.match(df.iat[0, 0])


    # general info
    def download_general_info(self, fund_ids: list[str]):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.do_download_general_info(fund_ids))


    async def do_download_general_info(self, fund_ids: list[str]):
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            tasks = [self.fetch_and_save_general_info(session, fund_id)
                     for fund_id in fund_ids]
            await asyncio.gather(*tasks)


    async def fetch_and_save_general_info(self, session, fund_id: str):
        page = await self.fetch_general_info(session, fund_id)
        await self.save_general_info(fund_id, page)


    async def fetch_general_info(self, session, fund_id: str):
        # http://fundf10.eastmoney.com/jbgk_000001.html
        general_info_url = f"http://fundf10.eastmoney.com/jbgk_{fund_id}.html"
        return await self.fetch(session, general_info_url, None, self.general_info_checker)


    async def save_general_info(self, fund_id, page):
        fund_name = None
        launch_date = None
        asset_size = None
        fund_company = None
        managers = {}

        soup = BeautifulSoup(page, 'lxml')
        for th in soup.find_all('th'):
            if th.text == u'????????????':
                fund_name = th.next_sibling.text
                continue

            if th.text == u'????????????':
                Y, M, D, tmp = re.split(u'???|???|???', th.next_sibling.text)
                launch_date = f'{Y}-{M}-{D}'
                continue

            if th.text == u'????????????':
                asset_size_mch = re.match('([0-9.]+)', th.next_sibling.text)
                if asset_size_mch:
                    asset_size = asset_size_mch.group(1)
                continue

            if th.text == u'???????????????':
                a = th.next_sibling.find('a')
                ref = a.get('href').strip('//')
                fund_company = [a.text, ref]
                continue

            if th.text == u'???????????????':
                for a in th.next_sibling.find_all('a'):
                    ref = a.get('href').strip('//')
                    manager_id_mch = re.match('[a-zA-Z./]+(\d+)\.html', ref)
                    if manager_id_mch:
                        manager_id = manager_id_mch.group(1)
                        manager_name = a.text
                        managers[manager_id] = [manager_name, ref]
                break

        if fund_id and fund_name and launch_date \
                and asset_size and fund_company \
                and managers:
            document = {'fund_id': fund_id,
                        'fund_name': fund_name,
                        'launch_date': launch_date,
                        'asset_size': asset_size,
                        'fund_company': fund_company,
                        'managers': managers}
            await self.collection_general_info.insert_one(document)


    def general_info_checker(self, page):
        return True
