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

    try:
        os.environ['frog_server_ip'] = config['frog_server']['ip']
    except KeyError:
        pass

    try:
        os.environ['frog_server_port'] = config['frog_server']['port']
    except KeyError:
        pass

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


def get_smtp_server() -> str:
    global config
    return config['email']['smtp_server']


def get_smtp_port() -> int:
    global config
    return config['email']['smtp_port']


def get_sender_email() -> str:
    global config
    return config['email']['sender_email']


def get_sender_user() -> str:
    global config
    return config['email']['sender_user']


def get_sender_password() -> str:
    global config
    return config['email']['sender_password']


def get_receiver_email() -> str:
    global config
    return config['email']['receiver_email']
