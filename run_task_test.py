import conf
#from task.download_hk_stock_data import download_hk_stock_data
from task.trend_follow_etf import trend_follow_etf


conf.parse_config()


if __name__ == "__main__":
    # download_hk_stock_data.delay()
    trend_follow_etf.delay()
