from celery import Celery
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)  # Adjust host/port if needed

app = Celery('frog', broker='redis://localhost:6379/0')

app.conf.timezone = 'Asia/Shanghai'  # Set the timezone to your local time

app.config_from_object('celery_config')

app.autodiscover_tasks(['task'])
