"""Apply or roll back the Paper Trading PostgreSQL enum migration."""

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
from paper_trading.storage.enum_migration import (  # noqa: E402
    PaperTradingEnumMigrationResult,
    migrate_paper_trading_enums,
)
from storage import get_storage  # noqa: E402

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate Paper Trading values to PostgreSQL enums", allow_abbrev=False)
    parser.add_argument("--dry-run", action="store_true", help="Validate migration without changing the database")
    parser.add_argument("--rollback", action="store_true", help="Restore the legacy string columns")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    return parser


def _print_result(result: PaperTradingEnumMigrationResult, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        return
    groups = ",".join(
        f"{group.type_name}:{','.join(f'{column.table_name}.{column.column_name}' for column in group.columns)}"
        for group in result.groups
    )
    print(
        f"dry_run={str(result.dry_run).lower()} "
        f"rollback={str(result.rollback).lower()} "
        f"converted={str(result.converted).lower()} "
        f"rolled_back={str(result.rolled_back).lower()} "
        f"groups={groups}"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        parse_config()
        with get_storage().engine.begin() as connection:
            result = migrate_paper_trading_enums(connection, dry_run=args.dry_run, rollback=args.rollback)
        _print_result(result, json_output=args.json_output)
        return 0
    except Exception as exc:
        logger.exception("Paper Trading enum migration failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
