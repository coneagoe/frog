import conf
from stock import download_etf_general_info


conf.config = conf.parse_config()

download_etf_general_info()