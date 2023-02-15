# -*- coding: utf-8 -*-
import logging
import os
import sys
import datetime
from tqdm import tqdm
from pathlib import Path
import conf
from ocr import *
from fund import TiantianParser


config_file_name = 'config.ini'


funds = ('002943', '000297', '001718', '001532', '000991', '004685', '006102',
         '000014', '161222', '005136', '161834', '360013', '001182', '110012',
         '519704', '519003', '004958', '005265', '001887', '007835', '001667',
         '001980', '550015', '002258', '001694', '005794', '005821', '001487',
         '006299', '006313', '161039', '001856', '003378', '040046', '000547',
         '001811', '005940', '005939', '006002')


daily_fund_position_path = 'data/fund/position/summary'

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
                df = df.append(df0, ignore_index=True)

    if df is not None:
        print(df)
        path = Path(daily_fund_position_path)
        if not path.exists():
            path.mkdir(parents=True)

        output_file_name = os.path.join(path, f"{timestamp}.csv")
        df.to_csv(output_file_name, encoding='utf_8_sig', index=False)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        exit()

    # logging.getLogger().setLevel(logging.DEBUG)
    conf.config = conf.parse_config(config_file_name)

    images = crop_image(sys.argv[1], OCR_ACCURATE_BASIC, 6000)

    today = datetime.date.today()
    update_fund_position("{:04d}-{:02d}-{:02d}".format(today.year, today.month, today.day),
                         images, OCR_ACCURATE_BASIC)
