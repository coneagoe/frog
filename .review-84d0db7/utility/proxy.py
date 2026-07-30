import functools
import logging
import os
import time

import requests
from requests.exceptions import ConnectionError, ProxyError, RequestException

proxy_api_url = "https://share.proxy.qg.net/get"
default_proxy_params: dict[str, str | int | float | bytes | None] = {
    "key": "XRA39BMP",
    "num": 1,
    "area": "",
    "isp": 0,
    "format": "json",
    "distinct": "true",
}


def _build_proxy_from_response(proxy_json: object) -> dict[str, str]:
    if not isinstance(proxy_json, dict):
        raise ValueError(f"Expected dict response, got {type(proxy_json).__name__}")

    proxy_data = proxy_json.get("data")
    if not isinstance(proxy_data, list) or not proxy_data:
        raise ValueError(f"Missing usable 'data' field: {proxy_json}")

    first_proxy = proxy_data[0]
    if not isinstance(first_proxy, dict):
        raise ValueError(f"Expected proxy item dict, got {type(first_proxy).__name__}")

    server = first_proxy.get("server")
    if not isinstance(server, str) or ":" not in server:
        raise ValueError(f"Missing usable 'server' field: {first_proxy}")

    ip, port = server.split(":", 1)
    return {"http": f"http://{ip}:{port}", "https": f"http://{ip}:{port}"}


def get_proxy(max_attempts: int = 3) -> dict[str, str]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    for attempt in range(1, max_attempts + 1):
        try:
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)

            resp = requests.get(proxy_api_url, params=default_proxy_params, timeout=5)
            proxy = _build_proxy_from_response(resp.json())

            test_url = "http://www.baidu.com"
            test = requests.get(test_url, proxies=proxy, timeout=10)
            if test.status_code == requests.codes.ok:
                os.environ["http_proxy"] = proxy["http"]
                os.environ["https_proxy"] = proxy["https"]
                return proxy
            logging.warning(
                "Proxy test failed with status %s on attempt %d/%d",
                test.status_code,
                attempt,
                max_attempts,
            )
        except RequestException as exc:
            logging.warning(
                "Proxy fetch/test failed on attempt %d/%d: %s",
                attempt,
                max_attempts,
                exc,
            )
        except ValueError as exc:
            logging.warning(
                "Malformed proxy response on attempt %d/%d: %s",
                attempt,
                max_attempts,
                exc,
            )

        if attempt < max_attempts:
            time.sleep(1)

    raise ProxyError(f"Failed to get working proxy after {max_attempts} attempts")


def change_proxy(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        max_proxy_retries = 3
        proxy_retry_count = 0

        while proxy_retry_count < max_proxy_retries:
            try:
                return func(*args, **kwargs)
            except (ConnectionError, ProxyError) as proxy_exc:
                logging.warning(
                    "Proxy error detected: %s. Attempting to get new proxy (attempt %d/%d)",
                    proxy_exc,
                    proxy_retry_count + 1,
                    max_proxy_retries,
                )

                # Clear existing proxy environment variables
                os.environ.pop("http_proxy", None)
                os.environ.pop("https_proxy", None)

                proxy = get_proxy()
                if not proxy:
                    proxy_retry_count += 1
                    if proxy_retry_count >= max_proxy_retries:
                        logging.error(
                            "Failed to get working proxy after %d attempts",
                            max_proxy_retries,
                        )
                        raise proxy_exc
                    continue

                # Wait a bit before retrying with new proxy
                time.sleep(2)
                proxy_retry_count += 1

            except Exception as exc:
                # For non-proxy errors, don't retry
                logging.error("Non-proxy error occurred: %s", exc)
                raise exc

        # If we've exhausted all proxy retries, raise the last error
        raise ProxyError("Maximum proxy retry attempts exceeded")

    return wrapped
