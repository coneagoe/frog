"""Create an immutable forecast snapshot for an explicit announcement-date range."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conf import parse_config  # noqa: E402
from forecast_snapshot import ForecastSnapshotRequest  # noqa: E402
from forecast_snapshot import create_forecast_snapshot_service as ForecastSnapshotService  # noqa: E402


def _parse_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an immutable forecast snapshot")
    parser.add_argument("--report-end-date", type=_parse_date, required=True)
    parser.add_argument("--announcement-start-date", type=_parse_date, required=True)
    parser.add_argument("--announcement-end-date", type=_parse_date, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        request = ForecastSnapshotRequest(
            args.report_end_date,
            args.announcement_start_date,
            args.announcement_end_date,
        )
    except ValueError as exc:
        parser.error(str(exc))

    parse_config()
    summary = ForecastSnapshotService().create_snapshot(request)
    print(
        " ".join(
            (
                f"run_id={summary.run_id}",
                f"attempt={summary.attempt}",
                f"status={summary.status}",
                f"requested_date_count={summary.requested_date_count}",
                f"covered_date_count={summary.covered_date_count}",
                f"source_row_count={summary.source_row_count}",
                f"record_count={summary.record_count}",
                f"duplicate_record_count={summary.duplicate_record_count}",
                f"same_day_conflict_count={summary.same_day_conflict_count}",
                f"failure_detail={summary.failure_detail or ''}",
            )
        )
    )
    return 0 if summary.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
