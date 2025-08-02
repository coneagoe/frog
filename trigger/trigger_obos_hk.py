import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from task import obos_hk  # noqa: E402

if __name__ == "__main__":
    result = obos_hk()
    print(f"result = {result}")
