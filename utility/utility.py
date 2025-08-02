import asyncio
import functools
import logging
import os
import time
from datetime import datetime


def is_older_than_n_days(filename: str, n: int) -> bool:
    dt = datetime.now() - datetime.fromtimestamp(os.path.getmtime(filename))
    return dt.days > n


def is_older_than_a_week(filename: str) -> bool:
    return is_older_than_n_days(filename, 7)


def is_older_than_a_month(filename: str) -> bool:
    return is_older_than_n_days(filename, 30)


def is_older_than_a_quarter(filename: str) -> bool:
    return is_older_than_n_days(filename, 90)


def retry_async(times: int, seconds: int):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            for i in range(times):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if str(e) != "":
                        logging.error(e)
                await asyncio.sleep(seconds)
            return None

        return wrapped

    return wrapper


def retry_sync(times: int, seconds: int):
    def wrapper(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if str(e) != "":
                        logging.error(e)
                time.sleep(seconds)
            return None

        return wrapped

    return wrapper
