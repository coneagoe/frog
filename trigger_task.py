from celery_app import app
from task import trend_follow_etf


if __name__ == '__main__':
    result = trend_follow_etf.apply_async()
    print(f"Task sent. Task ID: {result.id}")
