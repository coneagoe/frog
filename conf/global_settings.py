import os
import logging
import configparser


config = None
config_file_name = 'config.ini'


def parse_config():
    global config
    if not os.path.exists(config_file_name):
        logging.error(f"{config_file_name} does not exist!")
        exit()

    config = configparser.ConfigParser()
    config.read(config_file_name)

    if get_http_proxy():
        os.environ['http_proxy'] = get_http_proxy()

    if get_https_proxy():
        os.environ['https_proxy'] = get_https_proxy()

    return config


def get_http_proxy():
    global config
    try:
        return config['common']['http_proxy']
    except KeyError:
        return None


def get_https_proxy():
    global config
    try:
        return config['common']['https_proxy']
    except KeyError:
        return None
