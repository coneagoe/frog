import sys
import os
import re
from tqdm import tqdm
import pandas as pd
from ocr import *
import conf
from stock import *


pattern_stock_id = re.compile(r'^(\d{6})$')

conf.config = conf.parse_config()


def usage():
    print(f"{os.path.basename(__file__)} <image>")


def import_stocks(images: list, ocr_type):
    """
    parse interested stocks according to screenshots, save the results in csv
    :param timestamp: csv file name
    :param images:
    :param ocr_type:
    :return: None
    """
    stock_ids = []
    stock_names = []

    for image in tqdm(images):
        words = get_ocr(image, ocr_type)
        if words is not None:
            for word in words:
                m = pattern_stock_id.match(word)
                if m is None:
                    continue

                stock_id = m.group(1)
                stock_ids.append(stock_id)

                stock_name = get_stock_name(stock_id)
                if stock_name is None:
                    stock_name = get_etf_name(stock_id)
                stock_names.append(stock_name)

    df = pd.DataFrame({col_stock_id: stock_ids, col_stock_name: stock_names})

    if df is not None:
        # df[col_fund_id] = df[col_fund_id].astype('str')
        print(df)
        df.to_csv('tmp.csv', encoding='utf_8_sig', index=False)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        exit()

    image_file_name = sys.argv[1]
    images = crop_image(image_file_name, OCR_ACCURATE_BASIC, 6000)
    import_stocks(images, OCR_ACCURATE_BASIC)
