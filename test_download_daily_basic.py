#!/usr/bin/env python3
"""
测试脚本：下载 20260203~20260204 的 daily_basic 数据并存入数据库
使用 downloader_tushare 和 storage_db 模块
参考 download_manager.py 的 download_daily_basic_a_stock 方法生成交易日期
"""
import argparse
import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd
import pandas_market_calendars as mcal

from download.dl.downloader_tushare import download_daily_basic_a_stock_ts
from storage import StorageDb, get_storage, tb_name_daily_basic_a_stock
from common.const import COL_DATE

# 设置 TUSHARE_TOKEN 环境变量（用于 downloader_tushare.py）
os.environ["TUSHARE_TOKEN"] = "7933eb2c5a72e13006a1f6cdabeb0e6dc2826dc69919d17a51b42faf"

# 优化 pandas 显示设置
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_rows", 10)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_daily_basic_date_range(
    start_date: str, end_date: str, storage: StorageDb
) -> int:
    """
    从 Tushare 下载指定日期范围的 daily_basic 数据
    参考 download_manager.py 的 download_daily_basic_a_stock 方法

    Args:
        start_date: 开始日期 (YYYY-MM-DD 或 YYYYMMDD)
        end_date: 结束日期 (YYYY-MM-DD 或 YYYYMMDD)
        storage: 存储实例

    Returns:
        下载并保存的总记录数
    """
    market_calendar = mcal.get_calendar("XSHG")
    trade_days = market_calendar.schedule(start_date=start_date, end_date=end_date)

    total_records = 0

    try:
        total_days = len(trade_days)
        logger.info(f"需要下载 {total_days} 个交易日的每日基本面数据")

        for i, date in enumerate(trade_days.index, 1):
            trade_date = date.strftime("%Y-%m-%d")

            logger.info(f"[{i}/{total_days}] 下载日期: {trade_date}")

            df = download_daily_basic_a_stock_ts(trade_date=trade_date)

            if df is None or df.empty:
                logger.warning(f"日期 {trade_date} 无数据，跳过")
                continue

            logger.info(f"成功下载 {len(df)} 条记录")
            # 立即保存到数据库
            storage.save_daily_basic_a_stock(df)
            total_records += len(df)
            logger.info(f"已保存到数据库")

        logger.info(f"每日基本面数据下载完成，共处理 {total_days} 个交易日，总记录数: {total_records}")
        return total_records

    except Exception as e:
        logger.error(f"下载A股每日基本面数据时出错: {e}")
        return total_records


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="下载指定日期范围的 daily_basic 数据并存入数据库"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2026-02-03",
        help="开始日期 (YYYY-MM-DD 或 YYYYMMDD)，默认: 2026-02-03",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-02-04",
        help="结束日期 (YYYY-MM-DD 或 YYYYMMDD)，默认: 2026-02-04",
    )

    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date

    # 获取存储实例
    storage = get_storage()

    # 下载数据并保存（每下载一个交易日立即保存）
    total_records = download_daily_basic_date_range(start_date, end_date, storage)

    if total_records > 0:
        logger.info(f"下载完成，共保存 {total_records} 条记录到数据库")
    else:
        logger.warning("没有下载到任何数据")


if __name__ == "__main__":
    main()
