from datetime import datetime
import os


def is_older_than_n_days(filename: str, n: int):
    dt = datetime.now() - datetime.fromtimestamp(os.path.getmtime(filename))
    return dt.days > n
