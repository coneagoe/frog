from celery.schedules import crontab

broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'

# 定义定时任务
beat_schedule = {
    'run-backtest-daily': {
        'task': 'task.trend_follow_etf.trend_follow_etf',
        'schedule': crontab(hour=15, minute=5),
    },

#     'run-monitor-hourly': {
#         'task': 'task.foo.run_monitor',
#         'schedule': crontab(minute=0),
#     },
}