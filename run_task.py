import sys
import os
import conf
from task import (trend_follow_etf, )


conf.parse_config()


if __name__ == "__main__":
    result = trend_follow_etf.delay()
    print(f"Task started with ID: {result.id}")
    print("Waiting for results...")
    result_key = result.get()  # Wait for the task result
    print(f"Task completed with result: {result_key}")
