"""Backfill forecast records across an inclusive announcement-date range."""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conf import parse_config  # noqa: E402
from download import DownloadManager  # noqa: E402


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def resolve_dates(
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    today: date | None = None,
) -> list[date]:
    if (start_date is None) != (end_date is None):
        raise ValueError("--start-date and --end-date must be supplied together")
    if start_date is None:
        start_date = date(2026, 1, 1)
        end_date = (today or date.today()) - timedelta(days=7)
    assert end_date is not None
    if start_date > end_date:
        raise ValueError("--start-date must not be later than --end-date")
    return [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]


def backfill_forecast(announcement_dates: list[date], manager: DownloadManager) -> tuple[dict[str, int], list[str]]:
    summary = {
        "requested_dates": len(announcement_dates),
        "successful_dates": 0,
        "empty_dates": 0,
        "failed_dates": 0,
        "source_rows": 0,
        "a_share_rows": 0,
    }
    failed_announcement_dates: list[str] = []
    for announcement_date in announcement_dates:
        result = manager.download_forecast(ann_date=announcement_date.strftime("%Y%m%d"))
        summary["source_rows"] += result.source_rows
        summary["a_share_rows"] += result.a_share_rows
        if result.saved:
            summary["successful_dates"] += 1
            if result.source_rows == 0 or result.a_share_rows == 0:
                summary["empty_dates"] += 1
        else:
            summary["failed_dates"] += 1
            failed_announcement_dates.append(result.announcement_date)
    return summary, failed_announcement_dates


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill forecast records by announcement date")
    parser.add_argument("--start-date", type=_parse_date)
    parser.add_argument("--end-date", type=_parse_date)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        announcement_dates = resolve_dates(args.start_date, args.end_date)
    except ValueError as exc:
        parser.error(str(exc))

    parse_config()
    summary, failed_announcement_dates = backfill_forecast(announcement_dates, DownloadManager())
    print(
        " ".join(
            f"{name}={summary[name]}"
            for name in (
                "requested_dates",
                "successful_dates",
                "empty_dates",
                "failed_dates",
                "source_rows",
                "a_share_rows",
            )
        )
    )
    if failed_announcement_dates:
        print(f"failed_announcement_dates={','.join(failed_announcement_dates)}")
    return 1 if summary["failed_dates"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
