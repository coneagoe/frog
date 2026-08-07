"""Explicitly bootstrap paper matching-run status storage."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conf import parse_config  # noqa: E402
from paper_trading.storage.matching_status_migration import (  # noqa: E402
    MatchingStatusBootstrapResult,
    bootstrap_paper_matching_run_status,
)
from storage import get_storage  # noqa: E402

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap paper matching run status storage")
    parser.add_argument("--dry-run", action="store_true", help="Validate bootstrap without changing the database")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    return parser


def _print_result(result: MatchingStatusBootstrapResult, *, json_output: bool) -> None:
    payload = asdict(result)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    print(
        f"dry_run={str(result.dry_run).lower()} "
        f"table_exists={str(result.table_exists).lower()} "
        f"table_created={str(result.table_created).lower()} "
        f"converted={str(result.converted).lower()} "
        f"index_verified={str(result.index_verified).lower()} "
        f"labels={','.join(result.labels)} "
        f"observed_legacy_values={','.join(value or 'NULL' for value in result.observed_legacy_values)}"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        parse_config()
        with get_storage().engine.begin() as connection:
            result = bootstrap_paper_matching_run_status(connection, dry_run=args.dry_run)
        _print_result(result, json_output=args.json_output)
        return 0
    except Exception as exc:
        logger.exception("Paper matching run bootstrap failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
