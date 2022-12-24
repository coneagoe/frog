import requests
import re
import json
from urllib.parse import urlencode

def convert_secid(secid: str) -> str:
    if secid[0] == '6' or secid[0] == '5':
        return f'1.{secid}'
    return f'0.{secid}'

def fetch_close_price(secid: str) -> float:
    secid = convert_secid(secid)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:107.0) Gecko/20100101 Firefox/107.0"
    }

    base_url = "http://push2.eastmoney.com/api/qt/stock/get"

    parameters = (
        ("invt", 2),
        ("fltt", 1),
        ("cb", "jQuery3510768790004533975_1671331577142"),
        ("fields", "f58,f734,f107,f57,f43,f59,f169,f170,f152,f177,f111,f46,f60,f44,f45,f47,f260,f48,f261,f279,f277,f278,f288,f19,f17,f531,f15,f13,f11,f20,f18,f16,f14,f12,f39,f37,f35,f33,f31,f40,f38,f36,f34,f32,f211,f212,f213,f214,f215,f210,f209,f208,f207,f206,f161,f49,f171,f50,f86,f84,f85,f168,f108,f116,f167,f164,f162,f163,f92,f71,f117,f292,f51,f52,f191,f192,f262"),
        ("secid", secid),
        ("ut", "fa5fd1943c7b386f172d6893dbfba10b"),
        ("wbp2u", "|0|0|0|web"),
        ("_", "1671331577143"),
    )

    url = base_url + '?' + urlencode(parameters)

    resp = requests.get(url, headers=headers)
    if resp.status_code == requests.codes.ok:
        try:
            jq = resp.content.decode('utf-8')
            p = re.compile("jQuery[0-9_(]+(.*)\);")
            m = p.match(jq)
            js = json.loads(m.group(1))
            close_price_int = int(js["data"]["f43"])
            precision = int(js["data"]["f59"])
            close_price = close_price_int / pow(10, precision)
            return close_price
        except:
            print(f"url = {url}")
            print(f"resp = {resp.content}")
    else:
        print(f"url = {url}")
        print(f"status = {resp.status_code}")

