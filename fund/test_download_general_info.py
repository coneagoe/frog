# -*- coding: utf-8 -*-

from tiantian_crawler import TianTianCrawler


fund_ids = ['000001']


if __name__ == '__main__':
    ttc = TianTianCrawler()
    ttc.download_general_info(fund_ids)
