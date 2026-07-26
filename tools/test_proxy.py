import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from requests.exceptions import ProxyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import proxy as proxy_module  # noqa: E402

BAIDU_URL = "https://www.baidu.com"
REQUEST_TIMEOUT = 10


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            os.environ.setdefault(name, value.strip().strip('"').strip("'"))


def _proxy_server(proxy_url: str) -> str:
    parsed = urlsplit(proxy_url)
    if not parsed.hostname or parsed.port is None:
        raise ValueError("Proxy URL does not contain a server address")
    return f"{parsed.hostname}:{parsed.port}"


def _requires_qingguo_credentials() -> bool:
    return os.getenv("PROXY_PROVIDER", "auto").lower() == "qingguo"


def main() -> int:
    try:
        _load_dotenv(ROOT / ".env")
        if _requires_qingguo_credentials() and (
            not os.getenv("QG_PROXY_KEY") or not os.getenv("QG_PROXY_PWD")
        ):
            raise RuntimeError("QG_PROXY_KEY and QG_PROXY_PWD must be configured in .env")
        started = time.monotonic()
        proxies = proxy_module.get_proxy()
        response = requests.get(BAIDU_URL, proxies=proxies, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        print(f"proxy server: {_proxy_server(proxies['https'])}")
        print(f"elapsed ms: {round((time.monotonic() - started) * 1000)}")
        return 0
    except (FileNotFoundError, ProxyError, requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"proxy test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
