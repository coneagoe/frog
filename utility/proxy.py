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


def get_proxy() -> dict[str, str]:
    while True:
        try:
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)

            resp = requests.get(proxy_api_url, params=default_proxy_params, timeout=5)
            proxy_json = resp.json()
            proxy_data = proxy_json["data"][0]
            server = proxy_data["server"]
            ip, port = server.split(":")
            proxy = {"http": f"http://{ip}:{port}", "https": f"http://{ip}:{port}"}

            test_url = "http://www.baidu.com"
            test = requests.get(test_url, proxies=proxy, timeout=10)
            if test.status_code == requests.codes.ok:
                os.environ["http_proxy"] = proxy["http"]
                os.environ["https_proxy"] = proxy["https"]
                return proxy
        except RequestException as exc:
            logging.warning("Proxy fetch/test failed: %s", exc)
        except Exception as exc:
            logging.warning("Unexpected proxy error: %s", exc)
        time.sleep(1)


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
