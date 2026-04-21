from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from typing import Callable

import redis

from common.const import DEFAULT_REDIS_URL, REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY
from common.stock_market import is_hk_market_open_today
from utility import send_email as default_send_email

DEFAULT_START_DATE = "2024-11-01"
DEFAULT_STOCK_LIST = "02362 02981 00168 01211 09997 01558"


class ObosHkSkip(Exception):
    pass


@dataclass(frozen=True)
class ObosHkRunResult:
    status: str
    email_subject: str
    email_body: str
    command: list[str]
    stdout: str = ""
    stderr: str = ""


def get_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


def build_obos_hk_command(
    start_date_str: str,
    end_date_str: str,
    stock_list: str = DEFAULT_STOCK_LIST,
    *,
    executable: str | None = None,
    script_path: str = "backtest/obos_hk_9.py",
) -> list[str]:
    return [
        executable or sys.executable,
        script_path,
        "-s",
        start_date_str,
        "-e",
        end_date_str,
        "-f",
        stock_list,
    ]


def run_obos_hk_backtest(
    *,
    redis_get: Callable[[str], str | None] | None = None,
    is_market_open: Callable[[], bool] | None = None,
    run_subprocess: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    send_email: Callable[[str, str], object] | None = None,
    executable: str | None = None,
    start_date_str: str = DEFAULT_START_DATE,
    stock_list: str = DEFAULT_STOCK_LIST,
    end_date_str: str | None = None,
    redis_key: str = REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY,
    require_download_result: bool = False,
) -> ObosHkRunResult:
    redis_get = redis_get or get_redis_client().get
    is_market_open = is_market_open or is_hk_market_open_today
    run_subprocess = run_subprocess or subprocess.run
    send_email = send_email or default_send_email
    end_date_str = end_date_str or date.today().strftime("%Y-%m-%d")

    try:
        result = redis_get(redis_key)
    except Exception as exc:
        raise RuntimeError(f"failed to read Redis: {exc}") from exc

    if result:
        try:
            data = json.loads(result)
            if not isinstance(data, dict):
                raise TypeError("download result payload must be a JSON object")
            download_result = data.get("result")
            if not isinstance(download_result, str) or not download_result.strip():
                raise TypeError("download result payload must contain a usable result field")
        except Exception as exc:
            raise RuntimeError(f"invalid download result: {exc}") from exc

        if download_result != "success":
            raise ObosHkSkip(f"download result is {download_result}")
    elif require_download_result:
        raise ObosHkSkip("download result missing")

    if not is_market_open():
        raise ObosHkSkip("Market is closed today.")

    command = build_obos_hk_command(
        start_date_str,
        end_date_str,
        stock_list,
        executable=executable,
    )
    process = run_subprocess(command, capture_output=True, text=True)
    subject = f"obos_hk_{start_date_str}_{end_date_str}"

    if process.returncode == 0:
        body = process.stdout or ""
        send_email(subject, body)
        return ObosHkRunResult(
            status="success",
            email_subject=subject,
            email_body=body,
            command=command,
            stdout=process.stdout or "",
            stderr=process.stderr or "",
        )

    error_message = (process.stderr or "").strip()
    body = f"Backtest failed with error: {error_message}"
    send_email(subject, body)
    raise RuntimeError(error_message)
