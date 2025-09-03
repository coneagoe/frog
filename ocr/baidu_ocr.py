import base64
import json
import logging
import os
from enum import Enum

import requests  # type: ignore[import-untyped]
from PIL import Image


class OcrType(Enum):
    OCR_GENERAL_BASIC = 1
    OCR_ACCURATE = 2
    OCR_ACCURATE_BASIC = 3


image_length_limits = {
    OcrType.OCR_GENERAL_BASIC: 4000,
    OcrType.OCR_ACCURATE_BASIC: 8000,
    OcrType.OCR_ACCURATE: 8000,
}

token = None


def crop_image(image_file_name: str, ocr_type: OcrType, image_length: int) -> list:
    """
    Because the baidu ocr has the limits on the image size,
    we have to crap it first. See https://cloud.baidu.com/doc/OCR/s/Ck3h7y2ia
    :param image_file_name:
    :param ocr_type: OCR_GENERAL_BASIC, OCR_ACCURATE, OCR_ACCURATE_BASIC
    :param image_length:
    :return: image list
    """
    if not os.path.exists(image_file_name):
        logging.error(f"image {image_file_name} does not exist!")
        exit()

    image = Image.open(image_file_name)
    width, height = image.size
    x0, x1 = 0, width
    y0, y1 = 0, 0
    end = False
    i = 0
    images = []
    image_length_limit = min(image_length_limits[ocr_type], image_length)
    while True:
        y1 += image_length_limit
        if y1 >= height:
            y1 = height
            end = True

        cropped = image.crop((x0, y0, x1, y1))
        cropped.save(f"{i}.jpg")
        images.append(f"{i}.jpg")

        if end:
            break

        y0 = y1 - 100
        i += 1

    return images


def get_token():
    client_id = os.environ["baidu_ocr_client_id"]
    client_secret = os.environ["baidu_ocr_client_secret"]
    logging.info(f"client_id: {client_id}, client_secret: {client_secret}")

    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = requests.get(token_url, params=params)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logging.error(f"HTTP error occurred: {err}")
        return None
    except requests.exceptions.RequestException as err:
        logging.error(f"Error occurred: {err}")
        return None

    return response.json().get("access_token")


def get_parameter_ocr_accurate(image, token: str):
    """
    通用文字识别（高精度含位置版）接口
    :param image: 15px < length < 8192px and image size < 10MB.
            See https://cloud.baidu.com/doc/OCR/s/tk3h7y2aq
    :param token:
    :return:
            success: list
            fail: None
    """
    ocr_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"
    ocr_url += f"?access_token={token}"
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
    return body, headers, ocr_url


def get_parameter_ocr_accurate_basic(image, token: str):
    """
    通用文字识别（高精度版）接口
    :param image: 15px < length < 8192px and image size < 10MB.
            See https://cloud.baidu.com/doc/OCR/s/1k3h7y3db
    :param token:
    :return:
            success: list
            fail: None
    """
    ocr_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    ocr_url += f"?access_token={token}"
    body = {
        "image": image,
        "language_type": "auto_detect",
        "detect_direction": "true",
        "paragraph": "true",
        "probability": "true",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    return body, headers, ocr_url


def get_parameter_ocr_general_basic(image, token):
    """
    通用文字识别（标准版）接口
    :param image: 15px < length < 4096px and image size < 4MB.
            See https://cloud.baidu.com/doc/OCR/s/zk3h7xz52
    :param token:
    :return:
            success: list
            fail: None
    """
    ocr_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
    ocr_url += f"?access_token={token}"
    body = {
        "image": image,
        "detect_direction": "true",
        "paragraph": "true",
        "probability": "true",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    return body, headers, ocr_url


ocr_parameter_table = {
    OcrType.OCR_GENERAL_BASIC: get_parameter_ocr_general_basic,
    OcrType.OCR_ACCURATE_BASIC: get_parameter_ocr_accurate_basic,
    OcrType.OCR_ACCURATE: get_parameter_ocr_accurate,
}


def get_ocr(image_file_name: str, ocr_type: OcrType):
    """
    :param image_file_name:
    :param ocr_type: OCR_GENERAL_BASIC, OCR_ACCURATE, OCR_ACCURATE_BASIC
    :return:
            success: words list
            fail: None
    """
    global token
    with open(image_file_name, "rb") as f:
        if token is None:
            token = get_token()
            if token is None:
                return None

        image = base64.b64encode(f.read())

        body, headers, ocr_url = ocr_parameter_table[ocr_type](image, token)
        response = requests.post(ocr_url, headers=headers, data=body)
        if response.status_code == requests.codes.ok:
            content = json.loads(response.content.decode("UTF-8"))
            words = []
            try:
                for x in content["words_result"]:
                    for k, v in x.items():
                        if k == "words":
                            words.append(v.replace(" ", ""))
                return words
            except KeyError:
                logging.error(f'{content["error_msg"]}, {image_file_name}')
        else:
            logging.warning(f"status: {response.status_code}")
    return None
