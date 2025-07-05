import os
import sys
import redis
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from celery import Celery

redis_client = redis.Redis(host='localhost', port=6379, db=0)

app = Celery('frog', broker='redis://localhost:6379/0')

app.conf.timezone = 'Asia/Shanghai'

app.config_from_object('celery_config')

app.autodiscover_tasks(['task'])
