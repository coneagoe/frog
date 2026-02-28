import os

from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = redis_url
result_backend = redis_url

# 定义定时任务
beat_schedule = {
    #     "trend_follow_etf": {
    # "task": "task.trend_follow_etf.trend_follow_etf",
    # "schedule": crontab(hour=15, minute=5, day_of_week="mon-fri"),
    #     },
    "obos_hk": {
        "task": "task.obos_hk.obos_hk",
        "schedule": crontab(hour=18, minute=0, day_of_week="mon-fri"),
    },
    #     "monitor_fallback_stock": {
    # "task": "task.monitor_fallback_stock.monitor_fallback_stock",
    # "schedule": crontab(minute="*/5", hour="9-14", day_of_week="mon-fri"),
    #     },
}
