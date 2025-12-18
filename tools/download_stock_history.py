#!/usr/bin/env python3
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.const import AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 直接运行核心下载逻辑"""
    logger.info("=" * 60)
    logger.info("开始手动运行下载股票历史数据任务")
    logger.info("=" * 60)

    try:
        manager = DownloadManager()

        # 获取当前日期
        end_date = datetime.today().strftime("%Y-%m-%d")
        start_date = "2000-01-01"

        logger.info("开始批量下载所有股票历史数据")
        logger.info(f"日期范围: {start_date} 到 {end_date}")
        logger.info("数据周期: 日线")
        logger.info("复权方式: 前复权")

        # 首先测试加载股票基本信息
        logger.info("正在加载股票基本信息...")
        df_stocks = manager.storage.load_general_info_stock()
        total_stocks = len(df_stocks)
        logger.info(f"成功加载 {total_stocks} 只股票基本信息")

        # 显示前几个股票作为示例
        logger.info("前5只股票示例:")
        for i, row in df_stocks.head().iterrows():
            logger.info(f"  {row['股票代码']} - {row['股票名称']}")

        # 使用新的批量下载方法
        logger.info("开始下载所有股票的历史数据...")
        success = manager.download_all_stock_history(
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )

        if success:
            logger.info("✅ 所有股票历史数据下载成功完成！")
        else:
            logger.warning("⚠ 部分股票历史数据下载失败，请查看日志了解详情")

    except Exception as e:
        logger.error(f"任务执行失败: {str(e)}")
        import traceback

        traceback.print_exc()

    logger.info("=" * 60)
    logger.info("下载任务执行结束")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
