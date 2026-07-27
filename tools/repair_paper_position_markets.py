"""Explicit administrative repair for imported paper-position markets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from conf import parse_config
from paper_trading.domain.enums import Market
from paper_trading.storage.models import PaperPosition, PaperPositionLot
from storage import get_storage


@dataclass(frozen=True)
class MarketRepairMapping:
    account_id: int
    symbol: str
    market: Market


@dataclass(frozen=True)
class MarketRepairResult:
    account_id: int
    symbol: str
    market: Market
    position_rows_changed: int
    lot_rows_changed: int


def parse_mapping(value: str) -> MarketRepairMapping:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError("mapping must be ACCOUNT_ID:SYMBOL:MARKET")
    account_text, symbol, market_text = (part.strip() for part in parts)
    if not account_text or not symbol or not market_text:
        raise ValueError("mapping must be ACCOUNT_ID:SYMBOL:MARKET")
    try:
        account_id = int(account_text)
    except ValueError:
        raise ValueError(f"invalid account ID in mapping: {value!r}") from None
    if account_id <= 0:
        raise ValueError("account ID must be positive")
    try:
        market = Market(market_text)
    except ValueError:
        supported = ", ".join(item.value for item in Market)
        raise ValueError(f"unsupported market {market_text!r}; supported markets: {supported}") from None
    return MarketRepairMapping(account_id, symbol, market)


def _validate_mappings(mappings: Sequence[MarketRepairMapping]) -> list[MarketRepairMapping]:
    if not mappings:
        raise ValueError("at least one mapping is required")
    unique: dict[tuple[int, str], MarketRepairMapping] = {}
    for mapping in mappings:
        key = (mapping.account_id, mapping.symbol)
        previous = unique.get(key)
        if previous is not None and previous.market != mapping.market:
            raise ValueError(f"conflicting mappings for account {mapping.account_id}, symbol {mapping.symbol}")
        unique[key] = mapping
    return list(unique.values())


def repair_position_markets(session: Session, mappings: Sequence[MarketRepairMapping]) -> list[MarketRepairResult]:
    """Repair explicitly requested aggregate positions and imported lots atomically."""
    requested = _validate_mappings(mappings)
    try:
        positions: dict[tuple[int, str], PaperPosition] = {}
        for mapping in requested:
            position = (
                session.query(PaperPosition)
                .filter(
                    PaperPosition.account_id == mapping.account_id,
                    PaperPosition.symbol == mapping.symbol,
                )
                .one_or_none()
            )
            if position is None:
                raise ValueError(f"position does not exist for account {mapping.account_id}, symbol {mapping.symbol}")
            positions[(mapping.account_id, mapping.symbol)] = position

        results: list[MarketRepairResult] = []
        for mapping in requested:
            position = positions[(mapping.account_id, mapping.symbol)]
            position_rows_changed = (
                session.query(PaperPosition)
                .filter(
                    PaperPosition.account_id == mapping.account_id,
                    PaperPosition.symbol == mapping.symbol,
                    PaperPosition.market != mapping.market.value,
                )
                .update({PaperPosition.market: mapping.market.value}, synchronize_session=False)
            )
            lot_rows_changed = (
                session.query(PaperPositionLot)
                .filter(
                    PaperPositionLot.account_id == mapping.account_id,
                    PaperPositionLot.symbol == mapping.symbol,
                    PaperPositionLot.source == "imported",
                    PaperPositionLot.market != mapping.market.value,
                )
                .update({PaperPositionLot.market: mapping.market.value}, synchronize_session=False)
            )
            results.append(
                MarketRepairResult(
                    mapping.account_id,
                    mapping.symbol,
                    mapping.market,
                    position_rows_changed,
                    lot_rows_changed,
                )
            )
        session.commit()
        return results
    except Exception:
        session.rollback()
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair explicitly named imported paper-position markets")
    parser.add_argument("--mapping", action="append", required=True, metavar="ACCOUNT_ID:SYMBOL:MARKET")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        mappings = [parse_mapping(value) for value in args.mapping]
        parse_config()
        storage = get_storage()
        assert storage.Session is not None
        with storage.Session() as session:
            results = repair_position_markets(session, mappings)
        payload = [asdict(result) for result in results]
        for item in payload:
            item["market"] = item["market"].value
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            for item in payload:
                print(
                    f"{item['account_id']}:{item['symbol']}:{item['market']} "
                    f"position_rows_changed={item['position_rows_changed']} "
                    f"lot_rows_changed={item['lot_rows_changed']}"
                )
        return 0
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
