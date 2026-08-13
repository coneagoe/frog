"""18:00 daily refresh of recent forecast announcement dates."""

import logging
import os
import sys
from datetime import date, timedelta
from typing import Any, cast

from airflow import DAG
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import LOCAL_TZ, get_default_args  # noqa: E402, I001
from download import DownloadManager  # noqa: E402


def _announcement_dates(context: dict[str, Any]) -> list[date]:
    end_date = cast(date, context["data_interval_end"].in_timezone(LOCAL_TZ).date())
    return [end_date - timedelta(days=offset) for offset in range(29, -1, -1)]


def download_forecast(**context: Any) -> dict[str, Any]:
    announcement_dates = _announcement_dates(context)
    manager = DownloadManager()
    summary: dict[str, Any] = {
        "announcement_dates": [item.strftime("%Y%m%d") for item in announcement_dates],
        "requested_dates": len(announcement_dates),
        "successful_dates": 0,
        "empty_dates": 0,
        "failed_dates": 0,
        "source_rows": 0,
        "a_share_rows": 0,
    }

    for announcement_date in announcement_dates:
        result = manager.download_forecast(ann_date=announcement_date.strftime("%Y%m%d"))
        if not result.saved:
            summary["failed_dates"] += 1
            logging.error("Daily forecast download failed: summary=%s", summary)
            raise RuntimeError(f"forecast download failed for {result.announcement_date}")

        summary["successful_dates"] += 1
        summary["source_rows"] += result.source_rows
        summary["a_share_rows"] += result.a_share_rows
        if result.source_rows == 0 or result.a_share_rows == 0:
            summary["empty_dates"] += 1

    logging.info("Daily forecast download completed: summary=%s", summary)
    return summary


dag = DAG(
    "download_forecast_daily",
    default_args=get_default_args(),
    description="每日刷新最近30天业绩预告数据",
    schedule="0 18 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["forecast"],
)

PythonOperator(
    task_id="download_forecast",
    python_callable=download_forecast,
    dag=dag,
)
