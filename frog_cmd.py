import argparse
import base64
import logging
import os
import requests


def upload_stocks(csv_path: str, port: int):
    if not os.path.exists(csv_path):
        logging.error(f"{csv_path} not exists!")
        return

    with open(csv_path, 'rb') as f:
        stocks_base64 = base64.b64encode(f.read())
        r = requests.post(f"http://localhost:{port}/upload_stocks", files={'file': stocks_base64})
        print(r.text)


def download_stocks(csv_path: str, port: int):
    r = requests.get(f"http://localhost:{port}/download_stocks")
    if r.status_code == 200:
        with open(csv_path, 'wb') as f:
            f.write(base64.b64decode(r.content))
    else:
        logging.error(f"status: {r.status_code}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', type=str, help='upload stocks.csv')
    parser.add_argument('-d', type=str, help='download stocks.csv')
    parser.add_argument('-p', type=int, help='port', default=5000)
    args = parser.parse_args()

    if args.u:
        upload_stocks(args.u, args.p)
    elif args.d:
        download_stocks(args.d, args.p)
