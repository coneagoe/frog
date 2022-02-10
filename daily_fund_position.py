# -*- coding: utf-8 -*-
import logging
import os
import sys
import datetime
import baidu_ocr
from cv2 import imread, imwrite
from tqdm import tqdm
from pathlib import Path


funds = ('002943', '000297', '001718', '001532', '000991', '004685', '006102',
         '000014', '161222', '005136', '161834', '360013', '001182', '110012',
         '519704', '519003', '004958', '005265', '001887', '007835', '001667',
         '001980', '550015', '002258', '001694', '005794', '005821', '001487',
         '006299', '006313', '161039', '001856', '003378', '040046', '000547',
         '001811', '005940', '005939', '006002')


daily_fund_position_path = 'data/fund/position/summary'


def usage():
    print(f"{os.path.basename(__file__)} <image>")


def crop_image(image_file_name):
    if not os.path.exists(image_file_name):
        logging.error(f"image {image_file_name} does not exist!")
        exit()

    image = imread(image_file_name)
    width, height = image.shape[1::-1]
    x0, x1 = 0, width
    y0, y1 = 0, 0
    end = False
    i = 0
    images = []
    while True:
        y1 += 2000
        if y1 >= height:
            y1 = height
            end = True

        cropped = image[y0:y1, x0:x1]  # 裁剪坐标为[y0:y1, x0:x1]
        imwrite(f"{i}.jpg", cropped)
        images.append(f"{i}.jpg")

        if end:
            break

        y0 = y1 - 100
        i += 1

    return images


def update_fund_position(timestamp, images):
    df = None
    for image in tqdm(images):
        df0 = baidu_ocr.get_funds_position_ttjj_app(image, funds)
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

    images = crop_image(sys.argv[1])

    today = datetime.date.today()
    update_fund_position("{:04d}-{:02d}-{:02d}".format(today.year, today.month, today.day),
                         images)
