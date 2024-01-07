import conf
from stock import download_general_info_etf


conf.config = conf.parse_config()

download_general_info_etf()