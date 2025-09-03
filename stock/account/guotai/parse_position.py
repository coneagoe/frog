# -*- coding: utf-8 -*-

import logging
import re

import pandas as pd

from ocr import get_ocr
from stock.const import (
    COL_COST,
    COL_CURRENT_PRICE,
    COL_MARKET_VALUE,
    COL_POSITION,
    COL_POSITION_AVAILABLE,
    COL_PROFIT,
    COL_PROFIT_RATE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)

pattern_stick = re.compile(r"(\D+)(\d{6})$")
pattern_tailing_number = re.compile(r"\d+$")
pattern_float = re.compile(r"^\s*([-+.,\d%]+)\s*$")
pattern_int = re.compile(r"^(\d+)$")

g_stocks = {
    "当升科技": "300073",
    "兆易创新": "603986",
    "华润微": "688396",
    "北京君正": "300223",
    "电池ETF": "159755",
    "新能车": "515700",
    "稀土基金": "516150",
    "创业板成长E": "159967",
    "中国A50": "563000",
    "恒生科技": "513130",
    "恒生医疗": "513060",
    "易方达科润LOF": "161131",
    "H股LOF": "160717",
    "恒生国企ETF": "159850",
    "广发创业板定开": "162720",
    "南方瑞合": "501062",
    "港股通综": "513990",
    "科创华泰": "501202",
    "富国科创": "506003",
    "中欧远见定开": "166025",
    "H股消费": "513230",
    "万家科创": "506001",
    "创业板2年定开": "161914",
    "HK消费50": "513070",
}


def is_valid_stock_name(stock_name: str):
    return stock_name in g_stocks


def get_next_float(words: list, i: int):
    while i < len(words):
        logging.debug(f"{i}: {words[i]}")
        tmp = pattern_float.match(words[i])
        i += 1
        if tmp:
            return float(tmp.group(1).strip("%")), i
    logging.error(f"get_next_float: {i}, {words}")


def get_next_int(words: list, i: int):
    while i < len(words):
        logging.debug(f"{i}: {words[i]}")
        tmp = pattern_int.match(words[i])
        i += 1
        if tmp:
            return int(tmp.group(1)), i
    logging.error(f"get_next_float: {i}, {words}")


class GuotaiParser:
    stock_id, stock_name = (None, None)
    (
        position,
        position_available,
        position_market_value,
        current_price,
        cost,
        profit_loss,
        profit_loss_percent,
    ) = (0, 0, 0, 0, 0, 0, 0)
    data = None

    def __init__(self):
        self.reset()

    def reset(self):
        self.stock_id, self.stock_name = (None, None)
        (
            self.position,
            self.position_available,
            self.position_market_value,
            self.current_price,
            self.cost,
            self.profit_loss,
            self.profit_loss_percent,
        ) = (None, None, None, None, None, None, None)
        self.data = {
            COL_STOCK_ID: [],
            COL_STOCK_NAME: [],
            COL_MARKET_VALUE: [],
            COL_POSITION: [],
            COL_POSITION_AVAILABLE: [],
            COL_CURRENT_PRICE: [],
            COL_COST: [],
            COL_PROFIT: [],
            COL_PROFIT_RATE: [],
        }

    def save_data(self):
        self.data[COL_STOCK_ID].append(self.stock_id)
        self.data[COL_STOCK_NAME].append(
            pattern_tailing_number.sub("", self.stock_name)
        )
        self.data[COL_MARKET_VALUE].append(self.position_market_value)
        self.data[COL_POSITION].append(self.position)
        self.data[COL_POSITION_AVAILABLE].append(self.position_available)
        self.data[COL_CURRENT_PRICE].append(self.current_price)
        self.data[COL_COST].append(self.cost)
        self.data[COL_PROFIT].append(self.profit_loss)
        self.data[COL_PROFIT_RATE].append(self.profit_loss_percent)

        self.stock_id, self.stock_name = (None, None)
        (
            self.position,
            self.position_available,
            self.position_market_value,
            self.current_price,
            self.cost,
            self.profit_loss,
            self.profit_loss_percent,
        ) = (None, None, None, None, None, None, None)

    def parse_position(self, image_file_name: str, ocr_type):
        # parse fund positions according to the screenshot
        words = get_ocr(image_file_name, ocr_type)
        logging.debug(f"{image_file_name}: {words}")

        if words is not None:
            i = 0
            while i < len(words):
                logging.debug(f"{i}: {words[i]}")
                if self.stock_name is None:
                    if is_valid_stock_name(words[i]):
                        self.stock_name = words[i]
                        self.stock_id = g_stocks[self.stock_name]
                        pass
                    else:
                        i += 1
                        continue

                i += 1

                try:
                    if self.position is None:
                        self.position, i = get_next_int(words, i)

                    if self.current_price is None:
                        self.current_price, i = get_next_float(words, i)

                    if self.profit_loss is None:
                        self.profit_loss, i = get_next_float(words, i)

                    if self.position_market_value is None:
                        self.position_market_value, i = get_next_float(words, i)

                    if self.position_available is None:
                        self.position_available, i = get_next_int(words, i)

                    if self.cost is None:
                        self.cost, i = get_next_float(words, i)

                    if self.profit_loss_percent is None:
                        self.profit_loss_percent, i = get_next_float(words, i)

                except TypeError:
                    return None

                self.save_data()
                # # TODO get_possible_fund_id,
                # # 不如通过fund_name反查，等fund db建立起来
                # i += 1

            if len(self.data[COL_STOCK_ID]) != 0:
                df = pd.DataFrame(self.data)
                self.reset()
                return df

        return None
