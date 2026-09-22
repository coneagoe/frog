import functools
import logging
import os
import re
import time
from urllib.parse import quote

import requests
from requests.exceptions import ConnectionError, ProxyError, RequestException

proxy_api_url = "https://share.proxy.qg.net/get"
PROXY_POOL_URL = "http://proxy_pool:5010"
PROXY_POOL_GET_PATH = "/get/"
PROXY_POOL_DELETE_PATH = "/delete/"
_PROXY_USERINFO_PATTERN = re.compile(r"(https?://)([^/@]+)@")
PROXY_HEALTHCHECK_URL = "https://www.baidu.com"


def _proxy_provider() -> str:
    provider = os.getenv("PROXY_PROVIDER", "auto").lower()
    if provider not in {"auto", "proxy_pool", "qingguo"}:
        raise ProxyError("PROXY_PROVIDER must be auto, proxy_pool, or qingguo")
    return provider


def _proxy_pool_url(path: str) -> str:
    return f"{os.getenv('PROXY_POOL_URL', PROXY_POOL_URL).rstrip('/')}{path}"


def _is_proxy_server(server: str) -> bool:
    host, separator, port = server.rpartition(":")
    return bool(separator and host and port.isdigit() and 0 < int(port) < 65536)


def _get_proxy_from_proxy_pool() -> tuple[str, dict[str, str]]:
    response = requests.get(
        _proxy_pool_url(PROXY_POOL_GET_PATH),
        params={"type": "http"},
        timeout=5,
    )
    payload = response.json()
    server = payload.get("proxy") if isinstance(payload, dict) else None
    if not isinstance(server, str) or not _is_proxy_server(server):
        raise ValueError(f"ProxyPool returned no usable proxy: {payload}")
    proxy_url = f"http://{server}"
    return server, {"http": proxy_url, "https": proxy_url}


def _delete_proxy_from_pool(proxy_server: str) -> None:
    try:
        requests.get(
            _proxy_pool_url(PROXY_POOL_DELETE_PATH),
            params={"proxy": proxy_server},
            timeout=5,
        ).raise_for_status()
    except RequestException as exc:
        logging.warning(
            "Could not evict failed ProxyPool endpoint %s: %s",
            proxy_server,
            _exception_diagnostic(exc),
        )


def _validate_proxy(proxies: dict[str, str]) -> None:
    response = requests.get(PROXY_HEALTHCHECK_URL, proxies=proxies, timeout=10)
    response.raise_for_status()


def _build_proxy_params() -> dict[str, str | int | float | bytes | None]:
    key = os.getenv("QG_PROXY_KEY")
    pwd = os.getenv("QG_PROXY_PWD")
    if not key or not pwd:
        raise ProxyError("QG_PROXY_KEY and QG_PROXY_PWD must be configured")

    return {
        "key": key,
        "num": 1,
        "distinct": True,
    }


def _build_proxy_from_response(proxy_json: object) -> dict[str, str]:
    if not isinstance(proxy_json, dict):
        raise ValueError(f"Expected dict response, got {type(proxy_json).__name__}")

    if proxy_json.get("code") != "SUCCESS":
        raise ValueError(f"Proxy provider returned non-success response: {proxy_json}")

    proxy_data = proxy_json.get("data")
    if not isinstance(proxy_data, list) or not proxy_data:
        raise ValueError(f"Missing usable 'data' field: {proxy_json}")

    first_proxy = proxy_data[0]
    if not isinstance(first_proxy, dict):
        raise ValueError(f"Expected proxy item dict, got {type(first_proxy).__name__}")

    server = first_proxy.get("server")
    if not isinstance(server, str) or ":" not in server:
        raise ValueError(f"Missing usable 'server' field: {first_proxy}")

    key = os.getenv("QG_PROXY_KEY")
    pwd = os.getenv("QG_PROXY_PWD")
    if not key or not pwd:
        raise ProxyError("QG_PROXY_KEY and QG_PROXY_PWD must be configured")

    proxy_url = f"http://{quote(key, safe='')}:{quote(pwd, safe='')}@{server}"
    return {"http": proxy_url, "https": proxy_url}


def _get_proxy_from_qingguo() -> dict[str, str]:
    proxy_params = _build_proxy_params()
    resp = requests.get(proxy_api_url, params=proxy_params, timeout=5)
    return _build_proxy_from_response(resp.json())


def _exception_diagnostic(exc: Exception) -> str:
    return _PROXY_USERINFO_PATTERN.sub(r"\1[REDACTED]@", str(exc))


def get_proxy(max_attempts: int = 3) -> dict[str, str]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    provider = _proxy_provider()
    if provider == "qingguo":
        _build_proxy_params()

    for attempt in range(1, max_attempts + 1):
        pool_error: Exception | None = None
        proxy_server: str | None = None
        try:
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)

            if provider in {"auto", "proxy_pool"}:
                try:
                    proxy_server, proxy = _get_proxy_from_proxy_pool()
                    _validate_proxy(proxy)
                except (RequestException, ProxyError, ValueError) as exc:
                    pool_error = exc
                    if proxy_server is not None:
                        try:
                            _delete_proxy_from_pool(proxy_server)
                        except RequestException as eviction_exc:
                            logging.warning(
                                "Could not evict failed ProxyPool endpoint %s: %s",
                                proxy_server,
                                _exception_diagnostic(eviction_exc),
                            )
                    if provider == "proxy_pool":
                        raise
                    proxy_server = None
                    proxy = _get_proxy_from_qingguo()
            else:
                proxy = _get_proxy_from_qingguo()

            if proxy_server is None:
                _validate_proxy(proxy)
            os.environ["http_proxy"] = proxy["http"]
            os.environ["https_proxy"] = proxy["https"]
            return proxy
        except RequestException as exc:
            logging.warning(
                "Proxy fetch/test failed on attempt %d/%d%s: %s",
                attempt,
                max_attempts,
                (f" after ProxyPool error: {_exception_diagnostic(pool_error)}" if pool_error else ""),
                _exception_diagnostic(exc),
            )
        except ValueError as exc:
            logging.warning(
                "Malformed proxy response on attempt %d/%d%s: %s",
                attempt,
                max_attempts,
                (f" after ProxyPool error: {_exception_diagnostic(pool_error)}" if pool_error else ""),
                _exception_diagnostic(exc),
            )
        except Exception as exc:
            logging.warning(
                "Proxy provider failed on attempt %d/%d%s: %s",
                attempt,
                max_attempts,
                (f" after ProxyPool error: {_exception_diagnostic(pool_error)}" if pool_error else ""),
                _exception_diagnostic(exc),
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
