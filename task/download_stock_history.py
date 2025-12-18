import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from celery_app import app  # noqa: E402
from common.const import AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402
from stock import is_a_market_open_today  # noqa: E402
from utility import send_email  # noqa: E402


@app.task
def download_stock_history():
    if not is_a_market_open_today():
        return "A股 market is closed today."

    try:
        manager = DownloadManager()

        start_date = "2000-01-01"
        end_date = datetime.today().strftime("%Y-%m-%d")

        logging.info(
            f"开始批量下载所有股票历史数据，日期范围: {start_date} 到 {end_date}"
        )

        success = manager.download_all_stock_history(
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )

        if success:
            result_message = "✅ 所有股票历史数据下载成功完成！"
            logging.info(result_message)
        else:
            result_message = "⚠ 部分股票历史数据下载失败，请查看日志了解详情"
            logging.warning(result_message)
            send_email(subject="股票历史数据下载部分失败", body=result_message)

        return result_message

    except Exception as e:
        error_message = f"股票历史数据下载任务执行失败: {str(e)}"
        logging.error(error_message)
        send_email(subject="股票历史数据下载任务失败", body=error_message)
        return error_message
