from datetime import datetime
import os


def is_older_than_n_days(filename: str, n: int) -> bool:
    dt = datetime.now() - datetime.fromtimestamp(os.path.getmtime(filename))
    return dt.days > n


def is_older_than_a_week(filename: str) -> bool:
    return is_older_than_n_days(filename, 7)


def is_older_than_a_month(filename: str) -> bool:
    return is_older_than_n_days(filename, 30)


def is_older_than_a_quarter(filename: str) -> bool:
    return is_older_than_n_days(filename, 90)
