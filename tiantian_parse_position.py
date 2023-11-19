# -*- coding: utf-8 -*-
import os
import sys
from datetime import date
import re
import pandas as pd
from tqdm import tqdm
from ocr import *
from fund import *
import conf

# import logging
# logging.getLogger().setLevel(logging.DEBUG)

conf.parse_config()

parser = TiantianParser()


def usage():
    print(f"{os.path.basename(__file__)} <image>")


def update_fund_position(timestamp, images, ocr_type: OcrType):
    """
    parse fund positions according to screenshots, save the results in csv
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
                df = pd.concat([df, df0], ignore_index=True)

    if df is not None:
        # df[col_fund_id] = df[col_fund_id].astype('str')
        print(df)

        output_file_name = os.path.join(get_fund_position_path(), f"{timestamp}.csv")
        df.to_csv(output_file_name, encoding='utf_8_sig', index=False)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        exit()

    image_file_name = sys.argv[1]
    images = crop_image(image_file_name, OcrType.OCR_ACCURATE_BASIC, 6000)

    m = re.match(r'Screenshot_(\d{4})-(\d{2})-(\d{2}).*', image_file_name)
    if m:
        timestamp = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        today = date.today()
        timestamp = "{:04d}-{:02d}-{:02d}".format(today.year, today.month, today.day)

    update_fund_position(timestamp, images, OcrType.OCR_ACCURATE_BASIC)
