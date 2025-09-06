import logging
from .download_manager import DownloadManager
from .storage.csv_storage import CSVStorage
from .storage.timescale_storage import TimescaleDBStorage
from .downloader.akshare_downloader import AkshareDownloader


def create_download_manager(storage_type: str = "csv", **kwargs) -> DownloadManager:
    """创建下载管理器工厂函数"""
    
    # 创建下载器
    downloader = AkshareDownloader()
    
    # 创建存储器
    if storage_type == "csv":
        storage = CSVStorage()
    elif storage_type == "timescale":
        connection_string = kwargs.get("connection_string", "postgresql://quant:quant@localhost:5432/quant")
        storage = TimescaleDBStorage(connection_string)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")
    
    return DownloadManager(downloader, storage)


# 便捷函数，用于向后兼容
def download_stock_data_with_timescale(
    stock_id: str, 
    period: str = "daily", 
    start_date: str = "20200101", 
    end_date: str = "20231231", 
    adjust: str = "qfq",
    connection_string: str = "postgresql://quant:quant@db:5432/quant"
) -> bool:
    """使用TimescaleDB下载股票数据"""
    manager = create_download_manager(
        storage_type="timescale",
        connection_string=connection_string
    )
    
    success = manager.download_and_save_stock_data(
        stock_id=stock_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust
    )
    
    if success:
        logging.info(f"Stock data for {stock_id} downloaded and saved successfully to TimescaleDB")
    else:
        logging.error(f"Failed to download and save stock data for {stock_id} to TimescaleDB")
    
    return success


def download_stock_data_with_csv(
    stock_id: str, 
    period: str = "daily", 
    start_date: str = "20200101", 
    end_date: str = "20231231", 
    adjust: str = "qfq"
) -> bool:
    """使用CSV下载股票数据"""
    manager = create_download_manager(storage_type="csv")
    
    success = manager.download_and_save_stock_data(
        stock_id=stock_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust
    )
    
    if success:
        logging.info(f"Stock data for {stock_id} downloaded and saved successfully to CSV")
    else:
        logging.error(f"Failed to download and save stock data for {stock_id} to CSV")
    
    return success


def download_general_info_with_timescale(
    info_type: str,
    connection_string: str = "postgresql://quant:quant@db:5432/quant"
) -> bool:
    """使用TimescaleDB下载基本信息"""
    manager = create_download_manager(
        storage_type="timescale",
        connection_string=connection_string
    )
    
    success = manager.download_and_save_general_info(info_type)
    
    if success:
        logging.info(f"General info {info_type} downloaded and saved successfully to TimescaleDB")
    else:
        logging.error(f"Failed to download and save general info {info_type} to TimescaleDB")
    
    return success


def download_general_info_with_csv(info_type: str) -> bool:
    """使用CSV下载基本信息"""
    manager = create_download_manager(storage_type="csv")
    
    success = manager.download_and_save_general_info(info_type)
    
    if success:
        logging.info(f"General info {info_type} downloaded and saved successfully to CSV")
    else:
        logging.error(f"Failed to download and save general info {info_type} to CSV")
    
    return success
