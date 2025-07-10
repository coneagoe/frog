#!/bin/bash

# 激活 Python 虚拟环境
source env/bin/activate

# 以后台方式启动 Celery worker
celery -A celery_app worker --loglevel=info &

# 启动 Celery beat
celery -A celery_app beat --loglevel=info
