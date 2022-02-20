# -*- coding: utf-8 -*-

import requests
import re


proxypool_url = 'http://127.0.0.1:5555/random'
test_url="http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=000001&sdate=2001-12-18&edate=2020-05-18&per=20&page=1"


def get_proxy():
    # while True:
    tmp = requests.get(proxypool_url).text.strip()
    return {'http': f'http://{tmp}'}

    if re.match(r'.*:80\b', tmp):
        return {'http': f'http://{tmp}'}
    if re.match(r'.*:(8080|3128)\b', tmp):
        return {'https': f'https://{tmp}'}


def get_https_proxies():
    return [f"https://{x['proxy']}" for x in requests.get("http://127.0.0.1:5010/all?type=https").json()]


def get_http_proxy():
    while True:
        tmp = requests.get("http://127.0.0.1:5010/get/").json()
        if tmp['https']:
            continue

        return tmp['proxy']


def get_http_proxies():
    tmp = requests.get("http://127.0.0.1:5010/all").json()
    candidate_proxies = [f"http://{x['proxy']}" for x in tmp if re.match(r'.*:80\b', x['proxy'])]
    print(candidate_proxies)
    proxies = []
    for proxy in candidate_proxies:
    # for i in tmp:
        try:
            resp = requests.get(test_url, proxies={'http': i['proxy']}, timeout=1)
            if resp.status_code == requests.codes.ok:
                proxies.append(proxy)
        except:
            pass

    return proxies


def get_https_proxies():
    tmp = requests.get("http://127.0.0.1:5010/all").json()
    return [x['proxy'] for x in tmp if re.match(r'.*:(8080|3128)\b', x['proxy'])]


