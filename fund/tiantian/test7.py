# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import pandas as pd
import crawler as ttc


test_url = "http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2021-01-01&edate=2022-01-01&per=20&page=13"
fund_id = '000001'
start_date = '2021-01-01'
end_date = '2022-01-01'


async def foo():
    async with aiohttp.ClientSession(headers=ttc.headers, timeout=ttc.timeout) as session:
        tt = ttc.TianTianCrawler()
        tmp = await tt._fetch_history_netvalues(fund_id,
                                                session,
                                                start_date,
                                                end_date,
                                                13)
        print(pd.read_html(tmp, encoding='utf-8')[0])


asyncio.run(foo())
