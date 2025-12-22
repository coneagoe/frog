#!/usr/bin/env python3

import argparse
import logging
import os
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from storage import get_storage  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="手动下载港股通成分股基本信息",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--force", action="store_true", help="强制重新下载，覆盖现有数据"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("开始手动运行下载港股通成分股基本信息任务")
    logger.info("=" * 80)
    logger.info("参数配置:")
    logger.info(f"  强制覆盖: {'是' if args.force else '否'}")
    logger.info("=" * 80)

    try:
        # 导入核心模块
        from download import DownloadManager

        # 创建下载管理器
        manager = DownloadManager()

        logger.info("开始下载港股通成分股基本信息...")

        # 执行下载
        success = manager.download_general_info_hk_ggt(force=args.force)

        if success:
            logger.info("✅ 港股通成分股基本信息下载成功！")

            # 加载并显示下载结果
            logger.info("正在加载下载结果...")
            df_hk_ggt = get_storage().load_general_info_hk_ggt()

            if df_hk_ggt is not None and not df_hk_ggt.empty:
                total_stocks = len(df_hk_ggt)
                logger.info(f"成功获取 {total_stocks} 只港股通成分股")

                # 显示前10只股票作为示例
                logger.info("前10只港股通成分股示例:")
                for i, row in df_hk_ggt.head(10).iterrows():
                    logger.info(f"  {row['股票代码']} - {row['股票名称']}")

                if total_stocks > 10:
                    logger.info(f"  ... 还有 {total_stocks - 10} 只股票")

                # 显示统计信息
                logger.info("港股通成分股统计信息:")
                logger.info(f"  总数量: {total_stocks}")

            else:
                logger.warning("⚠ 未获取到港股通成分股数据")

        else:
            logger.error("❌ 港股通成分股基本信息下载失败")
            return False

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
        logger.info("港股通成分股基本信息下载任务执行结束")
        logger.info("=" * 80)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
