import os
import sys

import redis

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from celery import Celery  # noqa: E402

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client = redis.Redis.from_url(redis_url)

app = Celery("frog", broker=redis_url, backend=redis_url)

app.conf.timezone = "Asia/Shanghai"

app.config_from_object("celery_config")

app.autodiscover_tasks(["task"])
