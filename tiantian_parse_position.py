# -*- coding: utf-8 -*-
# import csv
# import logging
import sys
from datetime import date
import pandas as pd
from tqdm import tqdm
import conf
from ocr import *
from fund import *


conf.config = conf.parse_config()

parser = TiantianParser()


def usage():
    print(f"{os.path.basename(__file__)} <image>")


def update_fund_position(timestamp, images, ocr_type):
    '''
    parse fund positions according to screenshots, save the results in csv
    :param timestamp: csv file name
    :param images:
    :param ocr_type:
    :return: None
    '''
    global parser
    df = None
    for image in tqdm(images):
        df0 = parser.parse_position(image, ocr_type)
        if df0 is not None:
            if df is None:
                df = df0
            else:
                # df = df.append(df0, ignore_index=True)
                df = pd.concat(df, df0, ignore_index=True)

    if df is not None:
        # df[col_fund_id] = df[col_fund_id].astype('str')
        print(df)

        output_file_name = os.path.join(get_fund_position_path(), f"{timestamp}.csv")
        df.to_csv(output_file_name, encoding='utf_8_sig', index=False)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        exit()

    # logging.getLogger().setLevel(logging.DEBUG)

    images = crop_image(sys.argv[1], OCR_ACCURATE_BASIC, 6000)

    today = date.today()
    update_fund_position("{:04d}-{:02d}-{:02d}".format(today.year, today.month, today.day),
                         images, OCR_ACCURATE_BASIC)
