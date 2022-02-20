# -*- coding: utf-8 -*-

import requests
import proxy
import pandas as pd


test_url="http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2021-01-01&edate=2022-01-01&per=20&page=13"

for i in range(10):
    try:
        p = proxy.get_proxy()
        resp = requests.get(test_url, proxies=p, timeout=2)
        print(f"{resp.status_code}: {p}")
        if resp.status_code == requests.codes.ok:
            print(pd.read_html(resp.content, encoding='utf-8')[0])
    except Exception as e:
        print(e)
