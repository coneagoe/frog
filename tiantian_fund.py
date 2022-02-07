# -*- coding: utf-8 -*-
import os

import requests
import logging
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path


history_netvalue_path = 'data/fund/history_netvalue'

found_code = '111111'
page_number = ''
#start_date='2010-08-20'
end_date = ''

url = 'http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz'\
      '&code=110022&page=10&sdate=2019-01-01&edate=2019-02-13&per=1'


def get_start_date(fund_id):
    pass
#    # 本函数查询基金起始日期，返回日期字符串
#    search_url = f"http://fund.eastmoney.com/{fund_id}.html?spm=search"
#    response = requests.get(search_url)
#    text = response.content.decode('utf-8')
#
#    start_date = re.findall('<td><span class="letterSpace01">成 立 日</span>：(.*?)</td>', text)
#    # 以防止输入的编码查不到信息，对无记录基金代码进行标注，后续方便剔除
#    if start_date == []:
#        start_date = ['无记录']
#    return start_date[0]


class TianTianFund(object):
    def __init__(self, fund_id: str):
        self.fund_id = fund_id
        self.history_netvalue_csv = os.path.join(history_netvalue_path, f"{self.fund_id}.csv")

    # http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2001-12-18&edate=2020-05-18&per=20&page=1
    def _get_history_netvalues(self, start_date=None, end_date=None, page=1):
        '''
        :param start_date: YYYY-MM-DD
        :param end_date: YYYY-MM-DD
        :return:
        '''
        history_url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={self.fund_id}"
        if start_date is not None:
            history_url += f"&sdate={start_date}"

        if end_date is not None:
            history_url += f"&edate={end_date}"

        history_url += f"&page={page}"

        response = requests.get(history_url)
        if response.status_code == requests.codes.ok:
            return response.content
            #print(response.content)
            #return BeautifulSoup(response.content, 'html.parser')
        else:
            logging.warning(f"status: {response.status_code}")
            return None

    def download_history_netvalues(self, start_date=None, end_date=None):
        page = 1
        df = None
        while True:
            content = self._get_history_netvalues(start_date, end_date, page)
            if content is None:
                break
            df0 = pd.read_html(content, encoding='utf-8')[0]

            if end_date is not None:
                if df is None:
                    df = df0
                else:
                    df = df.append(df0, ignore_index=True)

                if df0.iat[-1, 0] == start_date:
                    return df
                else:
                    page += 1
            else:
                return df

    def save_history_netvalues(self, df):
        if df is not None:
            path = Path(history_netvalue_path)
            if not path.exists():
                path.mkdir(parents=True)

            df.to_csv(self.history_netvalue_csv, encoding='utf_8_sig', index=False)
