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
    return config
