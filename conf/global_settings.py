from pathlib import Path
import os
import logging
import configparser


config_file_name = 'config.ini'


def parse_email_config(config: dict):
    try:
        os.environ['MAIL_SERVER'] = config['email']['smtp_server']
    except KeyError:
        logging.warning("email app is not configured")

    try:
        os.environ['MAIL_PORT'] = config['email']['smtp_port']
    except KeyError:
        logging.warning("email app port is not configured")

    try:
        os.environ['MAIL_SENDER'] = config['email']['sender_email']
    except KeyError:
        logging.warning("email sender is not configured")

    try:
        os.environ['MAIL_USERNAME'] = config['email']['sender_username']
    except KeyError:
        logging.warning("email user is not configured")

    try:
        os.environ['MAIL_PASSWORD'] = config['email']['sender_password']
    except KeyError:
        logging.warning("email password is not configured")

    try:
        os.environ['MAIL_RECEIVERS'] = config['email']['email_receivers']
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

    try:
        os.environ['TEST'] = config['common']['test']
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


def create_dir_if_not_exist(path: str):
    if not os.path.exists(path):
        Path(path).mkdir(parents=True)


def parse_stock_config(config: dict):
    try:
        stock_data_path = config['stock']['data_path']
        stock_data_path_1d = os.path.join(stock_data_path, '1d')
        stock_data_path_1w = os.path.join(stock_data_path, '1w')
        stock_data_path_1M = os.path.join(stock_data_path, '1M')
        stock_data_path_position = os.path.join(stock_data_path, 'position')
        stock_data_path_info = os.path.join(stock_data_path, 'info')

        create_dir_if_not_exist(stock_data_path)
        create_dir_if_not_exist(stock_data_path_1d)
        create_dir_if_not_exist(stock_data_path_1w)
        create_dir_if_not_exist(stock_data_path_1M)
        create_dir_if_not_exist(stock_data_path_position)
        create_dir_if_not_exist(stock_data_path_info)

        os.environ['stock_data_path'] = stock_data_path
        os.environ['stock_data_path_1d'] = stock_data_path_1d
        os.environ['stock_data_path_1w'] = stock_data_path_1w
        os.environ['stock_data_path_1M'] = stock_data_path_1M
        os.environ['stock_data_path_position'] = stock_data_path_position
        os.environ['stock_data_path_info'] = stock_data_path_info
    except KeyError:
        logging.warning("stock data path is not configured")


def parse_account_config(config: dict):
    try:
        os.environ['account_data_path'] = config['account']['data_path']
    except KeyError:
        pass


def parse_frog_server(config: dict):
    try:
        os.environ['FROG_SERVER'] = config['frog_server']['ip']
    except KeyError:
        os.environ['FROG_SERVER'] = 'localhost'

    try:
        os.environ['FROG_PORT'] = config['frog_server']['port']
    except KeyError:
        os.environ['FROG_PORT'] = '5000'

    try:
        os.environ['FROG_SERVER_CONFIG'] = config['frog_server']['config']
    except KeyError:
        os.environ['FROG_SERVER_CONFIG'] = 'default'


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
    parse_account_config(config)
    parse_frog_server(config)
