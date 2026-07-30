#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import traceback

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from download import DownloadManager  # noqa: E402
from storage import get_storage  # noqa: E402


def download_stock_general_info(manager):
    """下载股票基本信息"""
    logger.info("开始下载A股股票基本信息...")
    success = manager.download_general_info_stock()

    if success:
        logger.info("✅ A股股票基本信息下载成功！")

        # 加载并显示下载结果
        logger.info("正在加载下载结果...")
        df_stock = get_storage().load_general_info_stock()

        if df_stock is not None and not df_stock.empty:
            total_stocks = len(df_stock)
            logger.info(f"成功获取 {total_stocks} 只A股股票")
            logger.info("A股股票统计信息:")
            logger.info(f"  总数量: {total_stocks}")
        else:
            logger.warning("⚠ 未获取到A股股票数据")
    else:
        logger.error("❌ A股股票基本信息下载失败")

    return success


def download_hk_ggt_general_info(manager):
    """下载港股通成分股基本信息"""
    logger.info("开始下载港股通成分股基本信息...")
    success = manager.download_general_info_hk_ggt()

    if success:
        logger.info("✅ 港股通成分股基本信息下载成功！")

        # 加载并显示下载结果
        logger.info("正在加载下载结果...")
        df_hk_ggt = get_storage().load_general_info_hk_ggt()

        if df_hk_ggt is not None and not df_hk_ggt.empty:
            total_stocks = len(df_hk_ggt)
            logger.info(f"成功获取 {total_stocks} 只港股通成分股")

            logger.info("港股通成分股统计信息:")
            logger.info(f"  总数量: {total_stocks}")
        else:
            logger.warning("⚠ 未获取到港股通成分股数据")
    else:
        logger.error("❌ 港股通成分股基本信息下载失败")

    return success


def download_etf_general_info(manager):
    """下载ETF基本信息"""
    logger.info("开始下载ETF基本信息...")
    success = manager.download_general_info_etf()

    if success:
        logger.info("✅ ETF基本信息下载成功！")

        # 加载并显示下载结果
        logger.info("正在加载下载结果...")
        df_etf = get_storage().load_general_info_etf()

        if df_etf is not None and not df_etf.empty:
            total_etfs = len(df_etf)
            logger.info(f"成功获取 {total_etfs} 只ETF")

            logger.info("ETF统计信息:")
            logger.info(f"  总数量: {total_etfs}")
        else:
            logger.warning("⚠ 未获取到ETF数据")
    else:
        logger.error("❌ ETF基本信息下载失败")

    return success


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="下载股票、港股通、ETF基本信息")
    parser.add_argument(
        "--type",
        "-t",
        choices=["stock", "hk_ggt", "etf", "all"],
        default="all",
        help="要下载的类型: stock(A股), hk_ggt(港股通), etf(ETF), all(全部)",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("开始手动运行下载基本信息任务")
    logger.info(f"下载类型: {args.type}")
    logger.info("=" * 80)

    try:
        manager = DownloadManager()

        success = True

        if args.type == "stock":
            success = download_stock_general_info(manager)
        elif args.type == "hk_ggt":
            success = download_hk_ggt_general_info(manager)
        elif args.type == "etf":
            success = download_etf_general_info(manager)
        elif args.type == "all":
            # 下载所有类型
            stock_success = download_stock_general_info(manager)
            hk_ggt_success = download_hk_ggt_general_info(manager)
            etf_success = download_etf_general_info(manager)

            success = stock_success and hk_ggt_success and etf_success

            if success:
                logger.info("🎉 所有类型基本信息下载成功！")
            else:
                logger.error("❌ 部分类型基本信息下载失败")

        return success

    except KeyboardInterrupt:
        logger.info("用户中断任务")
        return False
    except Exception as e:
        logger.error(f"任务执行失败: {str(e)}")
        traceback.print_exc()
        return False

    finally:
        logger.info("=" * 80)
        logger.info("基本信息下载任务执行结束")
        logger.info("=" * 80)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
