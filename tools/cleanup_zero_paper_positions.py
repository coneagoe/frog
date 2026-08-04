"""One-off cleanup for aggregate paper positions that are no longer held."""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conf import parse_config  # noqa: E402
from paper_trading.storage.models import PaperAccount, PaperPosition  # noqa: E402
from storage import get_storage  # noqa: E402

logger = logging.getLogger(__name__)


class CleanupBlockedError(RuntimeError):
    pass


def cleanup_zero_paper_positions(session: Session, *, dry_run: bool = False) -> dict[str, int]:
    candidates = list(
        session.query(PaperPosition)
        .filter(PaperPosition.total_quantity <= 0)
        .order_by(PaperPosition.account_id.asc(), PaperPosition.symbol.asc())
        .all()
    )
    frozen = [position for position in candidates if int(position.frozen_quantity or 0) != 0]
    if frozen:
        details = ", ".join(f"{position.account_id}:{position.symbol}" for position in frozen)
        raise CleanupBlockedError(f"closed positions have frozen quantity: {details}")

    accounts = list(session.query(PaperAccount).order_by(PaperAccount.id.asc()).all())
    migrated = [account for account in accounts if Decimal(account.realized_pnl or 0) != 0]
    if migrated:
        details = ", ".join(str(account.id) for account in migrated)
        raise CleanupBlockedError(f"accounts already have non-zero realized PnL: {details}")

    result = {"accounts": len(accounts), "positions": len(candidates)}
    if dry_run:
        return result

    for account in accounts:
        total = sum(
            (
                Decimal(position.realized_pnl or 0)
                for position in session.query(PaperPosition).filter(PaperPosition.account_id == account.id).all()
            ),
            Decimal("0"),
        )
        account.realized_pnl = total.quantize(Decimal("0.0001"))

    for position in candidates:
        session.delete(position)
    session.flush()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove zero-quantity paper positions")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report changes without writing")
    args = parser.parse_args(argv)
    try:
        parse_config()
        storage = get_storage()
        with storage.engine.begin() as connection:
            session = Session(connection)
            try:
                result = cleanup_zero_paper_positions(session, dry_run=args.dry_run)
            finally:
                session.close()
        print(f"dry_run={str(args.dry_run).lower()} accounts={result['accounts']} positions={result['positions']}")
        return 0
    except Exception as exc:
        logger.exception("Zero-quantity paper position cleanup failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
