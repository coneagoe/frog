import unittest

import tiantian_fund as ttf

fund_id = "000001"
start_date = "2021-11-01"
end_date = "2022-01-01"
netvalues = None
TTF = ttf.TianTianFund(fund_id)


class MyTestCase(unittest.TestCase):
    #     def test_download_history_netvalues(self):
    # global netvalues, TTF
    # netvalues = TTF.download_history_netvalues(start_date, end_date)
    # print(netvalues)
    # #self.assertEqual(True, False)  # add assertion here

    # def test_save_history_netvalues(self):
    #         TTF.save_history_netvalues(netvalues)

    def test_download_all_fund_general_info(self):
        TTF.download_all_fund_general_info()


if __name__ == "__main__":
    unittest.main()
