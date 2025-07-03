import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from celery_app import app
from task import trend_follow_etf


if __name__ == '__main__':
    result = trend_follow_etf()
    print(f"result = {result}")
