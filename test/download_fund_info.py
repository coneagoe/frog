# -*- coding: utf-8 -*-
import logging
from fund import TianTianCrawler
import conf


conf.config = conf.parse_config()

fund_ids = ['000001', '000002']


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    ttc = TianTianCrawler()
    ttc.download_fund_info(fund_ids)
