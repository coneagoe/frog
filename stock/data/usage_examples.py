"""
使用新架构的示例代码
"""
import logging
from .factory import create_download_manager, download_stock_data_with_timescale, download_stock_data_with_csv


def example_timescale_usage():
    """TimescaleDB使用示例"""
    print("=== TimescaleDB 使用示例 ===")
    
    # 方式1: 使用便捷函数
    success = download_stock_data_with_timescale(
        stock_id="000001",
        period="daily",
        start_date="20200101",
        end_date="20231231",
        adjust="qfq",
        connection_string="postgresql://quant:quant@db:5432/quant"
    )
    print(f"使用便捷函数下载股票数据: {'成功' if success else '失败'}")
    
    # 方式2: 使用工厂函数创建管理器
    manager = create_download_manager(
        storage_type="timescale",
        connection_string="postgresql://quant:quant@db:5432/quant"
    )
    
    # 下载股票数据
    success = manager.download_and_save_stock_data(
        stock_id="000002",
        period="daily",
        start_date="20200101",
        end_date="20231231",
        adjust="qfq"
    )
    print(f"使用管理器下载股票数据: {'成功' if success else '失败'}")
    
    # 下载ETF数据
    success = manager.download_and_save_etf_data(
        etf_id="510300",
        period="daily",
        start_date="20200101",
        end_date="20231231",
        adjust="qfq"
    )
    print(f"下载ETF数据: {'成功' if success else '失败'}")
    
    # 下载港股数据
    success = manager.download_and_save_hk_stock_data(
        stock_id="00700",
        period="daily",
        start_date="2020-01-01",
        end_date="2023-12-31",
        adjust="hfq"
    )
    print(f"下载港股数据: {'成功' if success else '失败'}")
    
    # 下载基本信息
    success = manager.download_and_save_general_info("stock")
    print(f"下载股票基本信息: {'成功' if success else '失败'}")


def example_csv_usage():
    """CSV使用示例"""
    print("\n=== CSV 使用示例 ===")
    
    # 方式1: 使用便捷函数
    success = download_stock_data_with_csv(
        stock_id="000001",
        period="daily",
        start_date="20200101",
        end_date="20231231",
        adjust="qfq"
    )
    print(f"使用便捷函数下载股票数据到CSV: {'成功' if success else '失败'}")
    
    # 方式2: 使用工厂函数创建管理器
    manager = create_download_manager(storage_type="csv")
    
    success = manager.download_and_save_stock_data(
        stock_id="000002",
        period="daily",
        start_date="20200101",
        end_date="20231231",
        adjust="qfq"
    )
    print(f"使用管理器下载股票数据到CSV: {'成功' if success else '失败'}")


def example_mixed_usage():
    """混合使用示例"""
    print("\n=== 混合使用示例 ===")
    
    # 创建TimescaleDB管理器
    timescale_manager = create_download_manager(
        storage_type="timescale",
        connection_string="postgresql://quant:quant@db:5432/quant"
    )
    
    # 创建CSV管理器
    csv_manager = create_download_manager(storage_type="csv")
    
    stock_list = ["000001", "000002", "600000"]
    
    for stock_id in stock_list:
        # 同时保存到TimescaleDB和CSV
        timescale_success = timescale_manager.download_and_save_stock_data(
            stock_id=stock_id,
            period="daily",
            start_date="20200101",
            end_date="20231231",
            adjust="qfq"
        )
        
        csv_success = csv_manager.download_and_save_stock_data(
            stock_id=stock_id,
            period="daily",
            start_date="20200101",
            end_date="20231231",
            adjust="qfq"
        )
        
        print(f"股票 {stock_id}: TimescaleDB {'✓' if timescale_success else '✗'}, CSV {'✓' if csv_success else '✗'}")


def example_backward_compatibility():
    """向后兼容性示例"""
    print("\n=== 向后兼容性示例 ===")
    
    # 原有的函数仍然可以使用
    from .download_data import (
        download_general_info_stock,
        download_history_data_stock,
        download_stock_with_timescale,  # 新的便捷函数
    )
    
    # 使用原有的CSV方式
    try:
        download_general_info_stock()
        print("原有CSV方式下载股票基本信息: 成功")
    except Exception as e:
        print(f"原有CSV方式下载股票基本信息: 失败 - {e}")
    
    # 使用新的TimescaleDB方式
    try:
        success = download_stock_with_timescale("000001")
        print(f"新的TimescaleDB方式下载股票数据: {'成功' if success else '失败'}")
    except Exception as e:
        print(f"新的TimescaleDB方式下载股票数据: 失败 - {e}")


if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        example_csv_usage()
        example_timescale_usage()
        example_mixed_usage()
        example_backward_compatibility()
    except Exception as e:
        print(f"示例运行失败: {e}")
        logging.error(f"Example failed: {e}")
