import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import conf  # noqa: E402
from utility import send_email  # noqa: E402

conf.parse_config()


if __name__ == "__main__":
    send_email("test", "test")
