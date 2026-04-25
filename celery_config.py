import os
from typing import Any

from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = redis_url
result_backend = redis_url

# 定义定时任务
beat_schedule: dict[str, dict[str, Any]] = {
    "small_market_capital_2_daily": {
        "task": "task.small_market_capital_2.small_market_capital_2",
        "schedule": crontab(hour=17, minute=30),
    },
}
