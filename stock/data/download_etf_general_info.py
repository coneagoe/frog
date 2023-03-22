import akshare as ak
from stock.common import get_etf_general_info_path


def download_etf_general_info():
    df = ak.fund_name_em()
    df.to_csv(get_etf_general_info_path(), encoding='utf_8_sig', index=False)
