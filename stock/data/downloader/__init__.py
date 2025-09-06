from enum import Enum
from .base import DataDownloader
from .akshare_downloader import AkshareDownloader


class AdjustType(Enum):
    BFQ = '',  # 不复权 (no adjustment)
    QFQ = 'qfq',  # 前复权 (forward adjustment)
    HFQ = 'hfq'   # 后复权 (backward adjustment)


__all__ = [
    'DataDownloader',
    'AkshareDownloader',
    'PriceType'
]
