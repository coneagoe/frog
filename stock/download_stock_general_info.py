import akshare as ak
import os
from stock import *


pattern_stock_id = r'60|00|30|68'


def download_stock_general_info():
    df = ak.stock_info_a_code_name()
    df = df.loc[df['code'].str.match(pattern_stock_id)]
    df = df.rename(columns={'code': col_stock_id, 'name': col_stock_name})
    output_file_name = os.path.join(get_stock_general_info_path(), general_info_file_name)
    df.to_csv(output_file_name, encoding='utf_8_sig', index=False)
