# -*- coding: utf-8 -*-
import datetime
import os
import sys
from os.path import basename, join

import pandas as pd
from tqdm import tqdm

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from ocr import OcrType, crop_image  # noqa: E402
from stock import get_stock_position_path  # noqa: E402
from stock.account.guotai import GuotaiParser  # noqa: E402

conf.parse_config()

parser = GuotaiParser()


def usage():
    print(f"{basename(__file__)} <image>")


def update_stock_position(timestamp, images, ocr_type):
    """
    parse stock positions according to screenshots, save the results in csv
    :param timestamp: csv file name
    :param images:
    :param ocr_type:
    :return: None
    """
    global parser
    df = None
    for image in tqdm(images):
        df0 = parser.parse_position(image, ocr_type)
        if df0 is not None:
            if df is None:
                df = df0
            else:
                df = pd.concat(df, df0, ignore_index=True)
                # df = df.append(df0, ignore_index=True)

    if df is not None:
        # df[col_fund_id] = df[col_fund_id].astype('str')
        print(df)

        output_file_name = join(get_stock_position_path(), f"{timestamp}.csv")
        df.to_csv(output_file_name, encoding="utf_8_sig", index=False)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        usage()
        exit()

    images = crop_image(sys.argv[1], OcrType.OCR_ACCURATE_BASIC, 6000)

    today = datetime.date.today()
    update_stock_position(
        "{:04d}-{:02d}-{:02d}".format(today.year, today.month, today.day),
        images,
        OcrType.OCR_ACCURATE_BASIC,
    )
