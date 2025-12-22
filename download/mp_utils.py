import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Dict, Iterable, List, Optional

import pandas as pd

from common.const import COL_DATE, AdjustType, PeriodType, SecurityType
from storage import get_storage, get_table_name

from .dl import Downloader


@dataclass(frozen=True)
class BatchResult:
    total: int
    success: int
    failed: int
    failed_ids: List[str]
    errors: Dict[str, str]


_DEFAULT_DOWNLOAD_PROCESS_COUNT = 4


def get_download_process_count() -> int:
    value = os.getenv("DOWNLOAD_PROCESS_COUNT")
    if not value:
        return _DEFAULT_DOWNLOAD_PROCESS_COUNT
    try:
        parsed = int(value)
    except ValueError:
        return _DEFAULT_DOWNLOAD_PROCESS_COUNT
    return max(1, parsed)


def _chunked(items: List[str], chunk_size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]  # noqa: E203


def _history_batch_worker(
    security_type: SecurityType,
    ids: List[str],
    period_value: str,
    adjust_value: str,
    start_date: str,
    end_date: str,
) -> BatchResult:
    """Module-level worker for ProcessPoolExecutor (spawn-safe)."""

    period = PeriodType(period_value)
    adjust = AdjustType(adjust_value)

    if security_type == SecurityType.STOCK:
        downloader_attr = "dl_history_data_stock"
        saver_attr = "save_history_data_stock"
    elif security_type == SecurityType.HK_GGT_STOCK:
        downloader_attr = "dl_history_data_stock_hk"
        saver_attr = "save_history_data_hk_stock"
    elif security_type == SecurityType.ETF:
        downloader_attr = "dl_history_data_etf"
        saver_attr = "save_history_data_etf"
    else:
        raise ValueError(f"Unsupported security_type: {security_type}")

    table_name = get_table_name(security_type, period, adjust)

    downloader = Downloader()
    storage = get_storage()
    downloader_func = getattr(downloader, downloader_attr)
    save_func = getattr(storage, saver_attr)

    end_ts = pd.to_datetime(end_date)

    success = 0
    failed = 0
    failed_ids: List[str] = []
    errors: Dict[str, str] = {}

    for security_id in ids:
        try:
            last_record = storage.get_last_record(table_name, security_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_ts = latest_date + pd.Timedelta(days=1)
                actual_start_date = actual_start_ts.strftime("%Y%m%d")

                if actual_start_ts > end_ts:
                    success += 1
                    continue
            else:
                actual_start_date = start_date

            df = downloader_func(
                security_id, actual_start_date, end_date, period, adjust
            )

            if df is None or df.empty:
                success += 1
                continue

            ok = bool(save_func(df, period, adjust))
            if ok:
                success += 1
            else:
                failed += 1
                failed_ids.append(security_id)
                errors[security_id] = "save returned False"

        except Exception as e:  # noqa: BLE001
            failed += 1
            failed_ids.append(security_id)
            errors[security_id] = str(e)

    return BatchResult(
        total=len(ids),
        success=success,
        failed=failed,
        failed_ids=failed_ids,
        errors=errors,
    )


def run_history_download_mp(
    *,
    security_type: SecurityType,
    ids: List[str],
    period_value: str,
    adjust_value: str,
    start_date: str,
    end_date: str,
    process_count: Optional[int] = None,
    chunk_size: int = 50,
    log_prefix: str = "",
) -> BatchResult:
    total = len(ids)
    if total == 0:
        return BatchResult(total=0, success=0, failed=0, failed_ids=[], errors={})

    if process_count is None:
        process_count = get_download_process_count()

    process_count = max(1, int(process_count))
    chunk_size = max(1, int(chunk_size))
    tasks = list(_chunked(ids, chunk_size))

    start_time = time.time()
    success = 0
    failed = 0
    failed_ids: List[str] = []
    errors: Dict[str, str] = {}

    # Spawn everywhere for Linux/Windows consistency and to avoid fork
    # inheriting DB connections.
    ctx = get_context("spawn")
    try:
        executor = ProcessPoolExecutor(max_workers=process_count, mp_context=ctx)
    except TypeError:
        executor = ProcessPoolExecutor(max_workers=process_count)

    with executor:
        futures = [
            executor.submit(
                _history_batch_worker,
                security_type,
                batch,
                period_value,
                adjust_value,
                start_date,
                end_date,
            )
            for batch in tasks
        ]

        completed = 0
        for fut in as_completed(futures):
            res: BatchResult = fut.result()
            completed += res.total
            success += res.success
            failed += res.failed
            failed_ids.extend(res.failed_ids)
            errors.update(res.errors)

            logging.info(
                f"{log_prefix}进度: {min(completed, total)}/{total} "
                f"(success={success}, failed={failed})"
            )

    elapsed = time.time() - start_time
    logging.info(
        f"{log_prefix}完成: total={total}, success={success}, failed={failed}, "
        f"elapsed={elapsed:.1f}s, processes={process_count}"
    )

    return BatchResult(
        total=total,
        success=success,
        failed=failed,
        failed_ids=failed_ids,
        errors=errors,
    )
