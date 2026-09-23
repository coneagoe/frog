import os
from typing import Any


def create_tushare_client() -> Any:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        try:
            raise ValueError("TUSHARE_TOKEN is not configured.")
        except ValueError as exc:
            raise ConnectionError("Tushare token is missing. Please set env var TUSHARE_TOKEN.") from exc

    try:
        import tushare as ts

        return ts.pro_api(token=token)
    except Exception as exc:
        raise ConnectionError("Unable to create Tushare client.") from exc
