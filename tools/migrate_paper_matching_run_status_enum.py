"""Run the paper matching run status enum migration explicitly."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from conf import parse_config
from paper_trading.storage.matching_status_migration import (
    MatchingStatusEnumMigrationResult,
    migrate_paper_matching_status_enum,
)
from storage import get_storage

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate paper matching run statuses to an enum")
    parser.add_argument("--dry-run", action="store_true", help="Validate the migration without changing the database")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    return parser


def _payload(result: MatchingStatusEnumMigrationResult) -> dict[str, object]:
    return asdict(result)


def _print_result(result: MatchingStatusEnumMigrationResult, *, json_output: bool) -> None:
    payload = _payload(result)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    labels = ",".join(result.labels)
    print(
        f"dry_run={str(result.dry_run).lower()} "
        f"converted={str(result.converted).lower()} "
        f"index_verified={str(result.index_verified).lower()} labels={labels}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        parse_config()
        storage = get_storage()
        with storage.engine.begin() as connection:
            result = migrate_paper_matching_status_enum(connection, dry_run=args.dry_run)
        _print_result(result, json_output=args.json_output)
        return 0
    except Exception as exc:
        logger.exception("Paper matching status enum migration failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
