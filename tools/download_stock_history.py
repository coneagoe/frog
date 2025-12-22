#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.const import AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="下载股票、ETF或港股通历史数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python download_stock_history.py --type stock    # 下载A股历史数据
  python download_stock_history.py --type etf     # 下载ETF历史数据
  python download_stock_history.py --type hk_ggt  # 下载港股通历史数据
        """,
    )

    parser.add_argument(
        "--type",
        type=str,
        choices=["stock", "etf", "hk_ggt"],
        required=True,
        help="下载的数据类型: stock(A股), etf(ETF), hk_ggt(港股通)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        default="2000-01-01",
        help="开始日期，格式: YYYY-MM-DD，默认: 2000-01-01",
    )

    parser.add_argument(
        "--end-date", type=str, help="结束日期，格式: YYYY-MM-DD，默认: 当天"
    )

    parser.add_argument(
        "--period",
        type=str,
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="数据周期: daily(日线), weekly(周线), monthly(月线)，默认: daily",
    )

    parser.add_argument(
        "--adjust",
        type=str,
        choices=["qfq", "hfq", "none"],
        default="qfq",
        help="复权方式: qfq(前复权), hfq(后复权), none(不复权)，默认: qfq",
    )

    return parser.parse_args()


def get_period_type(period_str):
    """将字符串周期转换为PeriodType枚举"""
    period_map = {
        "daily": PeriodType.DAILY,
        "weekly": PeriodType.WEEKLY,
        "monthly": PeriodType.MONTHLY,
    }
    return period_map.get(period_str, PeriodType.DAILY)


def get_adjust_type(adjust_str):
    """将字符串复权方式转换为AdjustType枚举"""
    adjust_map = {"qfq": AdjustType.QFQ, "hfq": AdjustType.HFQ, "none": AdjustType.BFQ}
    return adjust_map.get(adjust_str, AdjustType.QFQ)


def main():
    """主函数 - 支持多种数据类型下载"""
    args = parse_arguments()

    # 获取结束日期（默认为当天）
    end_date = args.end_date or datetime.today().strftime("%Y-%m-%d")

    # 转换参数
    period = get_period_type(args.period)
    adjust = get_adjust_type(args.adjust)

    # 类型映射
    type_names = {"stock": "A股", "etf": "ETF", "hk_ggt": "港股通"}

    logger.info("=" * 60)
    logger.info(f"开始手动运行下载{type_names[args.type]}历史数据任务")
    logger.info("=" * 60)
    logger.info(f"数据类型: {type_names[args.type]}")
    logger.info(f"日期范围: {args.start_date} 到 {end_date}")
    logger.info(f"数据周期: {args.period}")
    logger.info(f"复权方式: {args.adjust}")

    try:
        manager = DownloadManager()

        # 根据类型调用相应的下载方法
        if args.type == "stock":
            success = manager.download_all_stock_history(
                period=period,
                adjust=adjust,
                start_date=args.start_date,
                end_date=end_date,
            )
        elif args.type == "etf":
            success = manager.download_all_etf_history(
                period=period,
                adjust=adjust,
                start_date=args.start_date,
                end_date=end_date,
            )
        elif args.type == "hk_ggt":
            success = manager.download_all_hk_stock_history(
                period=period,
                adjust=adjust,
                start_date=args.start_date,
                end_date=end_date,
            )
        else:
            logger.error(f"不支持的数据类型: {args.type}")
            return False

        if success:
            logger.info(f"✅ 所有{type_names[args.type]}历史数据下载成功完成！")
        else:
            logger.warning(
                f"⚠ 部分{type_names[args.type]}历史数据下载失败，请查看日志了解详情"
            )

    except Exception as e:
        logger.error(f"任务执行失败: {str(e)}")
        import traceback

        traceback.print_exc()
        return False

    logger.info("=" * 60)
    logger.info("下载任务执行结束")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    main()
