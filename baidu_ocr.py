# -*- coding: utf-8 -*-

import base64
import requests
import json
import configparser
import logging
import pandas as pd
import os
from fund_common import *


config_file_name = 'config.ini'
token = None
proxies = None


def get_token():
    if not os.path.exists(config_file_name):
        logging.error(f"{config_file_name} does not exist!")
        exit()

    config = configparser.ConfigParser()
    config.read(config_file_name)
    client_id = config['baidu_ocr']['client_id']
    client_secret = config['baidu_ocr']['client_secret']
    logging.info(f"client_id: {client_id}, client_secret: {client_secret}")
    token_url = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials'
    token_url += f"&client_id={client_id}&client_secret={client_secret}"
    response = requests.get(token_url, proxies=proxies)
    if response.status_code == requests.codes.ok:
        return response.json().get("access_token")
    else:
        logging.warning(f"status: {response.status_code}")
        return None


# 调用通用文字识别（高精度含位置版）接口
# 以二进制方式打开图文件
# 参数image：图像base64编码
def get_ocr(image_name: str):
    global token
    with open(image_name, "rb") as f:
        if token is None:
            token = get_token()
            if token is None:
                return None

        image = base64.b64encode(f.read())

        body = {
            "image": image,
            "language_type": "auto_detect",
            "recognize_granularity": "small",
            "detect_direction": "true",
            "vertexes_location": "true",
            "paragraph": "true",
            "probability": "true",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        ocr_url = 'https://aip.baidubce.com/rest/2.0/ocr/v1/accurate'
        ocr_url += f"?access_token={token}"
        response = requests.post(ocr_url, headers=headers, data=body, proxies=proxies)
        if response.status_code == requests.codes.ok:
            content = json.loads(response.content.decode("UTF-8"))
            words = []
            try:
                for x in content['words_result']:
                    for k, v in x.items():
                        if k == 'words':
                            words.append(v.replace(' ', ''))
                return words
            except KeyError:
                logging.error(content['error_msg'])
        else:
            logging.warning(f"status: {response.status_code}")
    return None


# 天天基金app仓位
def get_funds_position_ttjj_app(image: str, funds: tuple):
    words = get_ocr(image)
    print(words)
    if words is not None:
        data = {col_fund_id: [],
                col_fund_name: [],
                col_asset: [],
                col_yesterday_earning: [],
                col_position_income: [],
                col_position_yield: []}
        i = 0
        while i + 7 < len(words):
            if words[i] in funds:
                try:
                    asset = float(words[i + 4].replace(',', ''))
                    yesterday_earning = float(words[i + 5].replace(',', ''))
                    position_income = float(words[i + 6].replace(',', ''))
                    position_yield = float(words[i + 7].strip('%').replace(',', ''))
                except ValueError:
                    logging.warning(f"{image}: {words}")
                    i += 1
                    continue

                data[col_fund_id].append(words[i])
                data[col_fund_name].append(words[i - 1])
                data[col_asset].append(asset)
                data[col_yesterday_earning].append(yesterday_earning)
                data[col_position_income].append(position_income)
                data[col_position_yield].append(position_yield)
                i += 8
            else:
                i += 1

        if len(data[col_fund_id]) != 0:
            df = pd.DataFrame(data)
            return df

    return None

