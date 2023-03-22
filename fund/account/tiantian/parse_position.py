# -*- coding: utf-8 -*-

import logging
import re
import pandas as pd
from ocr import get_ocr
from fund.common import *
from fund.data.general_info import get_fund_name, load_all_fund_general_info


pattern_stick = re.compile(r'(\D+)(\d{6})$')
pattern_tailing_number = re.compile(r'\d+$')
pattern_valid_fund_id = re.compile(r'^\d{6}$')
pattern_float = re.compile(r'^\s*([-+.,\d%]+)\s*$')


def is_valid_fund_id(fund_id: str) -> bool:
    df = load_all_fund_general_info()
    return pattern_valid_fund_id.match(fund_id) and \
            fund_id in df[col_fund_id].values


def is_fund_name_stick_with_fund_id(word):
    m = pattern_stick.match(word)
    if m is None:
        return None, None

    return m.group(1), m.group(2)


def get_next_float(words: list, i: int):
    while i < len(words):
        logging.debug(f'{i}: {words[i]}')
        tmp = pattern_float.match(words[i])
        i += 1
        if tmp:
            tmp0 = tmp.group(1).strip('%')
            # ocr may recognize ',' as '.' by mistake
            tmp1, tmp2 = tmp0[:-3], tmp0[-3:]
            tmp3 = re.sub(r'[,.]', '', tmp1)
            logging.debug(f'tmp0: {tmp0}, tmp1: {tmp1}, tmp2: {tmp2}, tmp3: {tmp3}')
            return float(tmp3 + tmp2), i
    logging.error(f'get_next_float: {i}, {words}')


class TiantianParser:
    fund_id, fund_name = (None, None)
    asset, yesterday_earning, position_income, position_yield =\
        (0, 0, 0, 0)
    data = None

    def __init__(self):
        self.reset()

    def reset(self):
        self.fund_id, self.fund_name = (None, None)
        self.asset, self.yesterday_earning,\
            self.position_income, self.position_yield = \
            (0, 0, 0, 0)
        self.data = {col_fund_id: [],
                     col_fund_name: [],
                     col_asset: [],
                     col_yesterday_earning: [],
                     col_profit: [],
                     col_profit_rate: []}

    def save_data(self):
        self.data[col_fund_id].append(self.fund_id)
        self.data[col_fund_name].append(pattern_tailing_number.sub('', self.fund_name))
        self.data[col_asset].append(self.asset)
        self.data[col_yesterday_earning].append(self.yesterday_earning)
        self.data[col_profit].append(self.position_income)
        self.data[col_profit_rate].append(self.position_yield)
        self.fund_id, self.fund_name = (None, None)
        self.asset, self.yesterday_earning, \
            self.position_income, self.position_yield = \
            (0, 0, 0, 0)

    def parse_position(self, image_file_name: str, ocr_type):
        # parse fund positions according to the screenshot
        words = get_ocr(image_file_name, ocr_type)
        logging.debug(f'{image_file_name}: {words}')
        if words is not None:
            i = 0
            while i < len(words):
                logging.debug(f"{i}: {words[i]}")
                if self.fund_name is None and self.fund_id is None:
                    self.fund_name, self.fund_id = is_fund_name_stick_with_fund_id(words[i])
                    if self.fund_name and self.fund_id:
                        self.fund_name = get_fund_name(self.fund_id)
                    elif is_valid_fund_id(words[i]):
                        # fund_id doesn't stick to fund_name
                        self.fund_id = words[i]
                        self.fund_name = get_fund_name(self.fund_id)
                    else:
                        i += 1
                        continue

                i += 1

                try:
                    if self.asset == 0:
                        self.asset, i = get_next_float(words, i)

                    if self.yesterday_earning == 0:
                        self.yesterday_earning, i = get_next_float(words, i)

                    if self.position_income == 0:
                        self.position_income, i = get_next_float(words, i)

                    if self.position_income and self.position_yield == 0:
                        self.position_yield, i = get_next_float(words, i)
                    else:
                        self.position_yield = 0
                        i += 1
                except TypeError:
                    return None

                self.save_data()

            if len(self.data[col_fund_id]) != 0:
                df = pd.DataFrame(self.data)
                self.reset()
                return df

        return None
