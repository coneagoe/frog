# -*- coding: utf-8 -*-

import requests

def get_https_proxies():
    return [f"https://{x['proxy']}" for x in requests.get("http://127.0.0.1:5010/all?type=https").json()]
