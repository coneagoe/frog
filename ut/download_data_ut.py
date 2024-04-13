import os
import sys
import unittest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf                 # noqa: E402
from stock import (
    # download_general_info_index,
    download_history_data_a_index,
    get_stock_data_path_1d,
)   # noqa: E402


conf.parse_config()


class MyTestCase(unittest.TestCase):
    # def test_download_general_info_index(self):
    #     download_general_info_index()
        # self.assertEqual(True, False)  # add assertion here

    def test_download_a_index(self):
        download_history_data_a_index('sh000813', 'daily', '2021-01-01', '2024-04-01')
        path = os.path.join(get_stock_data_path_1d(), 'sh000813.csv')
        self.assertTrue(os.path.exists(path))


if __name__ == '__main__':
    unittest.main()
