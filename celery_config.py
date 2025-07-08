from celery.schedules import crontab

broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'

# 定义定时任务
beat_schedule = {
    'trend_follow_etf': {
        'task': 'task.trend_follow_etf.trend_follow_etf',
        'schedule': crontab(hour=15, minute=5, day_of_week='mon-fri'),
    },

    'obos_hk': {
        'task': 'task.download_hk_stock_data.download_hk_stock_data',
        'schedule': crontab(hour=15, minute=0, day_of_week='mon-fri'),
    },

    'monitor_fallback_stock': {
        'task': 'task.monitor_fallback_stock.monitor_fallback_stock',
        'schedule': crontab(minute='*/5', hour='9-15', day_of_week='mon-fri'),
    },
}