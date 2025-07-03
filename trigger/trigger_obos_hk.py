import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from celery_app import app
from task import obos_hk


if __name__ == '__main__':
    result = obos_hk()
    print(f"result = {result}")
