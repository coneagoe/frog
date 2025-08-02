import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from task import trend_follow_etf  # noqa: E402

if __name__ == "__main__":
    result = trend_follow_etf()
    print(f"result = {result}")
