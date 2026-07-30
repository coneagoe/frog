"""Fetch and display one Qingguo short-lived proxy IP."""

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utility import proxy as proxy_module  # noqa: E402


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def main() -> int:
    try:
        _load_dotenv(ROOT / ".env")

        key = os.getenv("QG_PROXY_KEY")
        if not key:
            raise RuntimeError("QG_PROXY_KEY must be configured in .env")

        params = {
            "key": key,
            "num": 1,
            "distinct": True,
        }
        response = requests.get(proxy_module.proxy_api_url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Qingguo API returned an invalid response")

        code = payload.get("code")
        if code != "SUCCESS":
            raise RuntimeError(
                f"Qingguo proxy extraction failed: {code} (request_id={payload.get('request_id', '<unknown>')})"
            )

        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise RuntimeError("Qingguo API returned no usable proxy")

        proxy = data[0]
        proxy_ip = proxy.get("proxy_ip")
        server = proxy.get("server")
        if not isinstance(proxy_ip, str) or not isinstance(server, str):
            raise RuntimeError("Qingguo API response is missing proxy_ip or server")

        print(f"proxy ip: {proxy_ip}")
        print(f"proxy server: {server}")
        if isinstance(proxy.get("deadline"), str):
            print(f"deadline: {proxy['deadline']}")
        return 0
    except (FileNotFoundError, RuntimeError, requests.RequestException, ValueError) as exc:
        print(f"proxy demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
