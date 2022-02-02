# -*- coding: utf-8 -*-

import base64
import requests
import json
import configparser


token = None


def get_token():
    config = configparser.ConfigParser()
    config.read('config.ini')
    client_id = config['baidu_ocr']['client_id']
    client_secret = config['baidu_ocr']['client_secret']
    print(f"client_id: {client_id}, client_secret: {client_secret}")
    token_prefix = "https://aip.baidubce.com/oauth/2.0/token"
    token_url = f"{token_prefix}?grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"
    response = requests.get(token_url)
    if response.status_code == requests.codes.ok:
        return response.json().get("access_token")
    else:
        print(f"status: {response.status_code}")
        return None


# 调用通用文字识别（高精度含位置版）接口
# 以二进制方式打开图文件
# 参数image：图像base64编码
def get_ocr(image_name):
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
        ocr_prefix = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"
        ocr_url = f"{ocr_prefix}?access_token={token}"
        response = requests.post(ocr_url, headers=headers, data=body)
        if response.status_code == requests.codes.ok:
            return json.loads(response.content.decode("UTF-8"))
        else:
            print(f"status: {response.status_code}")
            return None


# 天天基金app仓位
def get_funds_position_ttjj_app(image):
    content = get_ocr(image)
    if content is not None:
        return [[v for k, v in x.items() if k == 'words'] for x in content['words_result']]
    else:
        return None

