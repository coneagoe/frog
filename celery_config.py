import os
from typing import Any

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = redis_url
result_backend = redis_url

# 定义定时任务
beat_schedule: dict[str, dict[str, Any]] = {}
