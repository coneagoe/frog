import os
import logging
import configparser


config_file_name = 'config.ini'


def parse_email_config(config: dict):
    try:
        os.environ['email_server'] = config['email']['smtp_server']
    except KeyError:
        logging.warning("email server is not configured")

    try:
        os.environ['email_server_port'] = config['email']['smtp_port']
    except KeyError:
        logging.warning("email server port is not configured")

    try:
        os.environ['email_sender'] = config['email']['sender_email']
    except KeyError:
        logging.warning("email sender is not configured")

    try:
        os.environ['email_user'] = config['email']['sender_user']
    except KeyError:
        logging.warning("email user is not configured")

    try:
        os.environ['email_password'] = config['email']['sender_password']
    except KeyError:
        logging.warning("email password is not configured")

    try:
        os.environ['email_receiver'] = config['email']['receiver_email']
    except KeyError:
        logging.warning("email receiver is not configured")


def parse_common_config(config: dict):
    try:
        os.environ['http_proxy'] = config['common']['http_proxy']
    except KeyError:
        pass

    try:
        os.environ['https_proxy'] = config['common']['https_proxy']
    except KeyError:
        pass


def parse_ocr_config(config: dict):
    try:
        os.environ['baidu_ocr_client_id'] = config['baidu_ocr']['client_id']
    except KeyError:
        logging.warning("baidu ocr client id is not configured")

    try:
        os.environ['baidu_ocr_client_secret'] = config['baidu_ocr']['client_secret']
    except KeyError:
        logging.warning("baidu ocr client secret is not configured")


def parse_fund_config(config: dict):
    try:
        os.environ['fund_data_path'] = config['fund']['data_path']
    except KeyError:
        logging.warning("fund data path is not configured")


def parse_stock_config(config: dict):
    try:
        os.environ['stock_data_path'] = config['stock']['data_path']
    except KeyError:
        logging.warning("stock data path is not configured")


def parse_account_config(config: dict):
    try:
        os.environ['account_data_path'] = config['account']['data_path']
    except KeyError:
        logging.warning("account data path is not configured")


def parse_config():
    if not os.path.exists(config_file_name):
        logging.error(f"{config_file_name} does not exist!")
        exit()

    config = configparser.ConfigParser()
    config.read(config_file_name)

    parse_common_config(config)
    parse_email_config(config)
    parse_ocr_config(config)
    parse_fund_config(config)
    parse_stock_config(config)
