#!/usr/bin/env python3
"""
手动运行下载港股历史数据任务的脚本
Manual script to run the download Hong Kong stock history task
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description="手动下载港股历史数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 下载所有港股日线历史数据（默认）
  python download_hk_stock_history.py

  # 下载所有港股周线历史数据
  python download_hk_stock_history.py --period weekly

  # 下载所有港股月线历史数据，指定日期范围
  python download_hk_stock_history.py --period monthly --start-date 2023-01-01 --end-date 2023-12-31

  # 下载单个港股的历史数据
  python download_hk_stock_history.py --stock-id 00700 --start-date 2023-01-01
        """,
    )

    parser.add_argument(
        "--stock-id",
        type=str,
        help="港股代码 (5位数字，如 00700)，不指定则下载所有港股",
    )

    parser.add_argument(
        "--period",
        type=str,
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="数据周期 (默认: daily)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        default="2000-01-01",
        help="开始日期 (格式: YYYY-MM-DD，默认: 2000-01-01)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="结束日期 (格式: YYYY-MM-DD，默认: 当天)",
    )

    parser.add_argument(
        "--adjust",
        type=str,
        choices=["hfq", "qfq"],
        default="hfq",
        help="复权类型 (默认: hfq 后复权)",
    )

    args = parser.parse_args()

    # 如果未指定结束日期，使用当天
    if args.end_date is None:
        args.end_date = datetime.today().strftime("%Y-%m-%d")

    logger.info("=" * 80)
    logger.info("开始手动运行下载港股历史数据任务")
    logger.info("=" * 80)
    logger.info("参数配置:")
    logger.info(f"  股票代码: {args.stock_id if args.stock_id else '所有港股'}")
    logger.info(f"  数据周期: {args.period}")
    logger.info(f"  复权类型: {args.adjust}")
    logger.info(f"  日期范围: {args.start_date} 到 {args.end_date}")
    logger.info("=" * 80)

    try:
        # 导入核心模块
        from common.const import AdjustType, PeriodType
        from download import DownloadManager

        # 创建下载管理器
        manager = DownloadManager()

        # 映射字符串到枚举类型
        period_map = {
            "daily": PeriodType.DAILY,
            "weekly": PeriodType.WEEKLY,
            "monthly": PeriodType.MONTHLY,
        }

        adjust_map = {"hfq": AdjustType.HFQ, "qfq": AdjustType.QFQ}

        period = period_map[args.period]
        adjust = adjust_map[args.adjust]

        # 首先加载港股基本信息
        logger.info("正在加载港股基本信息...")
        df_hk_stocks = manager.storage.load_general_info_hk_ggt()

        if df_hk_stocks is None or df_hk_stocks.empty:
            logger.error("无法获取港股基本信息数据")
            return False

        total_hk_stocks = len(df_hk_stocks)
        logger.info(f"成功加载 {total_hk_stocks} 只港股基本信息")

        # 显示前几个港股作为示例
        logger.info("前5只港股示例:")
        for i, row in df_hk_stocks.head().iterrows():
            logger.info(f"  {row['股票代码']} - {row['股票名称']}")

        success = False

        if args.stock_id:
            # 下载单个港股
            logger.info(f"开始下载港股 {args.stock_id} 的历史数据...")

            # 验证股票代码格式
            if not args.stock_id.isdigit() or len(args.stock_id) != 5:
                logger.error(f"港股代码格式错误: {args.stock_id} (应为5位数字)")
                return False

            success = manager.download_hk_stock_history(
                stock_id=args.stock_id,
                period=period,
                start_date=args.start_date,
                end_date=args.end_date,
                adjust=adjust,
            )

            if success:
                logger.info(f"✅ 港股 {args.stock_id} 历史数据下载成功！")
            else:
                logger.warning(f"⚠ 港股 {args.stock_id} 历史数据下载失败")

        else:
            # 下载所有港股
            logger.info("开始下载所有港股的历史数据...")
            success = manager.download_all_hk_stock_history(
                period=period,
                adjust=adjust,
                start_date=args.start_date,
                end_date=args.end_date,
            )

            if success:
                logger.info("✅ 所有港股历史数据下载成功完成！")
            else:
                logger.warning("⚠ 部分港股历史数据下载失败，请查看日志了解详情")

        return success

    except KeyboardInterrupt:
        logger.info("用户中断任务")
        return False
    except Exception as e:
        logger.error(f"任务执行失败: {str(e)}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        logger.info("=" * 80)
        logger.info("港股下载任务执行结束")
        logger.info("=" * 80)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
