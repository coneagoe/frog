import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf
from send_email import send_email
# from .send_email import send_email


conf.parse_config()


if __name__ == "__main__":
    send_email("test", "test")
