import argparse
import base64
import logging
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests    # noqa: E402
import conf        # noqa: E402


def monitor_stock_upload(csv_path: str, ip: str, port: int):
    if not os.path.exists(csv_path):
        logging.error(f"{csv_path} not exists!")
        return

    with open(csv_path, 'rb') as f:
        stocks_base64 = base64.b64encode(f.read())
        r = requests.post(f"http://{ip}:{port}/monitor_stock/upload", files={'file': stocks_base64})
        print(r.text)


def monitor_stock_download(csv_path: str, ip: str, port: int):
    r = requests.get(f"http://{ip}:{port}/monitor_stock/download")
    if r.status_code == 200:
        with open(csv_path, 'wb') as f:
            f.write(base64.b64decode(r.content))
    else:
        logging.error(f"status: {r.status_code}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', type=str, help='upload stocks.csv')
    parser.add_argument('-d', type=str, help='download stocks.csv')
    parser.add_argument('-i', type=str, help='frog app ip', default='localhost')
    parser.add_argument('-p', type=int, help='port', default=5000)
    parser.add_argument('-P', action='store_true', help='use proxy')
    args = parser.parse_args()

    if args.P:
        conf.parse_config()

    if args.u:
        monitor_stock_upload(args.u, args.i, args.p)
    elif args.d:
        monitor_stock_download(args.d, args.i, args.p)
