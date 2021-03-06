# -*- coding: utf-8 -*-

import base64
import requests
import json
import configparser
import logging
import pandas as pd
import os
import re
from fund_common import *


config_file_name = 'config.ini'
token = None
proxies = None


pattern_stick = re.compile(r'.*(\d{6})$')
pattern_tailing_number = re.compile(r'\d+$')
pattern_valid_fund_id = re.compile(r'^\d{6}$')
pattern_float = re.compile(r'^\s*([-+\.,\d%]+)\s*$')


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
    def is_valid_fund_id(fund_id: str):
        return pattern_valid_fund_id.match(fund_id)

    def save_data():
        data[col_fund_id].append(fund_id)
        data[col_fund_name].append(pattern_tailing_number.sub('', fund_name))
        data[col_asset].append(float(asset.replace(',', '')))
        data[col_yesterday_earning].append(float(yesterday_earning.replace(',', '')))
        data[col_position_income].append(float(position_income.replace(',', '')))
        data[col_position_yield].append(float(position_yield.strip('%').replace(',', '')))

    def is_stick(input):
        m = pattern_stick.match(input)
        if m is None:
            return None

        return (input, m.group(1))

    def get_next_float(i: int, words: list):
        while i < len(words):
            tmp = pattern_float.match(words[i])
            if tmp:
                i += 1
                return (tmp.group(1), i)
            i += 1

    def get_possible_fund_id(input):
        pass

    words = get_ocr(image)
    # print(words)
    if words is not None:
        data = {col_fund_id: [],
                col_fund_name: [],
                col_asset: [],
                col_yesterday_earning: [],
                col_position_income: [],
                col_position_yield: []}
        i = 0
        while i < len(words):
            # print(f"{i}: {words[i]}")
            if words[i] == '资产':
                if is_valid_fund_id(words[i - 1]):
                    # fund_id doesn't stick to fund_name
                    fund_id = words[i - 1]
                    fund_name = words[i - 2]
                    i += 1
                    asset, i = get_next_float(i, words)
                    yesterday_earning, i = get_next_float(i, words)
                    position_income, i = get_next_float(i, words)
                    position_yield, i = get_next_float(i, words)
                    save_data()
                else:
                    output = is_stick(words[i - 1])
                    if output:
                        # fund_id sticks to fund_name
                        fund_id = output[1]
                        fund_name = output[0]
                        i += 1
                        asset, i = get_next_float(i, words)
                        yesterday_earning, i = get_next_float(i, words)
                        position_income, i = get_next_float(i, words)
                        position_yield, i = get_next_float(i, words)
                        save_data()
#                     else:
                        # pass
                        # # TODO get_possible_fund_id,
                        # # 不如通过fund_name反查，等fund db建立起来
#                         i += 1
            i += 1

        if len(data[col_fund_id]) != 0:
            df = pd.DataFrame(data)
            return df

    return None


