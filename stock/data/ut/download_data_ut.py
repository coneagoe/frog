import os
import sys
import unittest

# from unittest.mock import patch
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
import conf  # noqa: E402
from stock.common import (  # noqa: E402
    get_stock_300_ingredients_path,
    get_stock_500_ingredients_path,
)
from stock.data.download_data import (  # noqa: E402
    download_300_ingredients,
    download_500_ingredients,
    download_history_data_a_index,
    get_stock_data_path_1d,
)

conf.parse_config()


class TestDownloadData(unittest.TestCase):
    def test_download_a_index(self):
        file_path = os.path.join(get_stock_data_path_1d(), "sh000813.csv")
        if os.path.exists(file_path):
            os.remove(file_path)

        download_history_data_a_index("sh000813", "daily", "2021-01-01", "2024-04-01")
        self.assertTrue(os.path.exists(file_path))

    def test_download_300_ingredients(self):
        file_path = os.path.join(get_stock_300_ingredients_path(), "2010-01-01.csv")
        if os.path.exists(file_path):
            os.remove(file_path)

        download_300_ingredients()
        self.assertTrue(os.path.exists(file_path))

    def test_download_500_ingredients(self):
        file_path = os.path.join(get_stock_500_ingredients_path(), "2010-01-01.csv")
        if os.path.exists(file_path):
            os.remove(file_path)

        download_500_ingredients()
        self.assertTrue(os.path.exists(file_path))


if __name__ == "__main__":
    unittest.main()
