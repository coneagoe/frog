# -*- coding: utf-8 -*-
import os
import logging
import pandas as pd
from pathlib import Path
import json
import re
import aiohttp
import asyncio
import aiofiles
from datetime import datetime
from common import *



def check_path():
    path = Path(fund_data_path)
    if not path.exists():
        path.mkdir(parents=True)


def is_older_than_30_days(f):
    dt = datetime.now() - datetime.fromtimestamp(os.path.getmtime(f))
    return dt.days > 30


def get_all_fund_general_info():
    if not os.path.exists(all_general_info_csv) or \
            is_older_than_30_days(all_general_info_csv):
        asyncio.run(download_all_fund_general_info())

    if not os.path.exists(all_general_info_csv):
        return None

    return pd.read_csv(all_general_info_csv)


def parse(html):
    pass
#     soup = BeautifulSoup(html,'html.parser')
    # body = soup.find('div', attrs={'class':'entry-content'})
#     return [normalize('NFKD',para.get_text()) for para in body.find_all('p')]


async def fetch_and_parse(session, url):
    html = await fetch(session, url)
    paras = parse(html)
    return paras

async def scrape_urls(urls):
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(
            *(fetch_and_parse(session, url) for url in urls)
        )


async def download_all_fund_general_info():
    async with aiohttp.ClientSession() as session:
        fund_dict_path = 'http://fund.eastmoney.com/js/fundcode_search.js'
        async with session.get(fund_dict_path) as resp:
            if resp.status == 200:
                # you have download all fund general info first,
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


def calculate_page_count(start_date: str, end_date: str) -> int:
    item_per_page = 20
    sdate = datetime.strptime(start_date, '%Y-%m-%d')
    edate = datetime.strptime(end_date, '%Y-%m-%d')
    delta_date = edate - sdate
    page_count = (delta_date.days + 1) // item_per_page
    if (delta_date.days + 1) % item_per_page:
        page_count += 1

    return page_count


async def do_download_history_netvalues(fund_id: str, start_date: str, end_date: str):
    print("download_history_netvalues: start")
    df = None
    page_count = calculate_page_count(start_date, end_date)

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_history_netvalues(fund_id, session, start_date, end_date, i) for i in range(1, page_count + 1)]
        pages = await asyncio.gather(*tasks)
        for page in pages:
            df0 = pd.read_html(page, encoding='utf-8')[0]
            if df is None:
                df = df0
            else:
                df = df.append(df0, ignore_index=True)
    return df


# http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2001-12-18&edate=2020-05-18&per=20&page=1
async def fetch_history_netvalues(fund_id: str,
                                  session,
                                  start_date: str = None,
                                  end_date: str = None,
                                  page: int = 1):
    '''
    :param start_date: YYYY-MM-DD
    :param end_date: YYYY-MM-DD
    :return:
    '''
    print("fetch_history_netvalues: start")
    history_url = "http://fund.eastmoney.com/f10/F10DataApi.aspx"
    # async with aiohttp.ClientSession() as session:
    params = {'type': 'lsjz', 'code': fund_id, 'page': page}
    if start_date: params['sdate'] = start_date
    if end_date: params['edate'] = end_date

    async with session.get(history_url, params=params) as resp:
        if resp.status == 200:
            return await resp.text()
        else:
            logging.warning(f"status: {resp.status_code}, fund_id = {fund_id}, page = {page}")
            return None


async def save_history_netvalues(output, df):
    print("save_history_netvalues: start")
    if df is not None:
        async with aiofiles.open(output, mode='w') as f:
            tmp = df.to_csv(encoding='utf_8_sig', index=False)
            await f.write(tmp)


# async def fetch(session, url, params=None):
    # async with session.get(url, params=params) as response:
#         return response


def download_history_netvalues(fund_id: str, start_date: str, end_date: str):
    output_file_name = os.path.join(history_netvalue_path, f"{fund_id}.csv")
    async def foo():
        df = await do_download_history_netvalues(fund_id, start_date, end_date)
        await save_history_netvalues(output_file_name, df)
    asyncio.run(foo())


