import os

from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = redis_url
result_backend = redis_url

# 定义定时任务
beat_schedule = {
    "trend_follow_etf": {
        "task": "task.trend_follow_etf.trend_follow_etf",
        "schedule": crontab(hour=15, minute=5, day_of_week="mon-fri"),
    },
    "obos_hk": {
        "task": "task.download_hk_stock_data.download_hk_stock_data",
        "schedule": crontab(hour=15, minute=0, day_of_week="mon-fri"),
    },
    "monitor_fallback_stock": {
        "task": "task.monitor_fallback_stock.monitor_fallback_stock",
        "schedule": crontab(minute="*/5", hour="9-14", day_of_week="mon-fri"),
    },
    "download_stock_history": {
        "task": "task.download_stock_history.download_stock_history",
        "schedule": crontab(
            hour=16, minute=0, day_of_week="mon-fri"
        ),  # 工作日下午4点执行
    },
}
