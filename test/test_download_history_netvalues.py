# -*- coding: utf-8 -*-

from timeit import Timer

from tiantian_crawler import TianTianCrawler

# async def foo():
# df = await ttc.download_history_netvalues('000001', '2022-01-01', '2022-02-01')
#     await ttc.save_history_netvalues('tmp.csv', df)


if __name__ == "__main__":
    t = Timer()
    ttc = TianTianCrawler()
    ttc.download_history_netvalues("000001", "2021-01-01", "2022-01-01")
    print(t.timeit())
