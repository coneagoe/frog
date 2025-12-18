import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.const import AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402
from stock import is_a_market_open_today  # noqa: E402

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# 创建 DAG
dag = DAG(
    "download_stock_history_daily",
    default_args=default_args,
    description="Daily stock history data download using download_stock_history",
    schedule="0 16 * * 1-5",  # 每个工作日下午4点执行
    catchup=False,
    max_active_runs=1,
)


def download_stock_history_task(**context):
    """下载股票历史数据任务"""
    if not is_a_market_open_today():
        print("A股市场今日休市，跳过下载任务")
        return "Market is closed today, task skipped."

    try:
        # 创建下载管理器
        manager = DownloadManager()

        # 获取日期范围 - 下载最近30天的数据
        end_date = datetime.today().strftime("%Y%m%d")
        start_date = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")

        # 股票列表 - 可以根据需要扩展
        stock_ids = [
            "000001",  # 平安银行
            "000002",  # 万科A
            "000858",  # 五粮液
            "600000",  # 浦发银行
            "600036",  # 招商银行
            "600519",  # 贵州茅台
            "002415",  # 海康威视
            "300014",  # 亿纬锂能
            "688981",  # 中芯国际
        ]

        success_count = 0
        failed_stocks = []

        print(f"开始下载 {len(stock_ids)} 只股票的历史数据...")
        print(f"日期范围: {start_date} 到 {end_date}")

        for stock_id in stock_ids:
            try:
                # 使用download_stock_history方法下载日线历史数据，使用前复权
                result = manager.download_stock_history(
                    stock_id=stock_id,
                    period=PeriodType.DAILY,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=AdjustType.QFQ,
                )

                if result:
                    success_count += 1
                    print(f"✅ 股票 {stock_id} 历史数据下载成功")
                else:
                    failed_stocks.append(stock_id)
                    print(f"❌ 股票 {stock_id} 历史数据下载失败")

            except Exception as e:
                failed_stocks.append(stock_id)
                print(f"❌ 股票 {stock_id} 下载异常: {str(e)}")

        # 生成结果报告
        result_message = f"""
        股票历史数据下载完成报告

        总股票数: {len(stock_ids)}
        成功: {success_count}
        失败: {len(failed_stocks)}

        失败的股票: {', '.join(failed_stocks) if failed_stocks else '无'}
        """

        print(result_message)

        # 如果有失败的股票，抛出异常以便Airflow标记任务为失败
        if failed_stocks:
            raise Exception(f"部分股票下载失败: {', '.join(failed_stocks)}")

        return (
            f"股票历史数据下载完成，成功: {success_count}, 失败: {len(failed_stocks)}"
        )

    except Exception as e:
        error_message = f"股票历史数据下载任务执行失败: {str(e)}"
        print(f"❌ {error_message}")
        raise Exception(error_message)


# 定义任务
task_download_stock_history = PythonOperator(
    task_id="download_stock_history",
    python_callable=download_stock_history_task,
    dag=dag,
)
