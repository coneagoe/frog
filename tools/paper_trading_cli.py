"""CLI wrapper for the paper trading API.

Usage:
  paper_trading_cli.py [--base-url URL] [--token TOKEN] [--json] <command> ...

Global flags:
  --base-url URL     API base URL (default: $PAPER_TRADING_API_BASE_URL or http://localhost:8000)
  --token TOKEN      API bearer token (default: $PAPER_TRADING_API_TOKEN)
  --json             Output raw JSON instead of human-readable text

Commands:
  account create --name NAME --initial-cash AMOUNT
  account list
  account get --account-id ID
  account delete --account-id ID
  account positions --account-id ID
  account cash-ledger --account-id ID
  order create --account-id ID --symbol SYMBOL --side buy|sell --quantity N
               --limit-price PRICE --trade-date YYYY-MM-DD [--idempotency-key KEY] [--comment TEXT]
  order update-comment --order-id ID --comment TEXT
  order list --account-id ID
  order get --order-id ID
  order cancel --order-id ID
  order validity-checks --account-id ID --order-id ID
  trade list --account-id ID
  matching run --trade-date YYYY-MM-DD [--account-id ID]
  matching list
  matching get --run-id ID
  snapshot list --account-id ID

Exit codes:
  0  success
  2  validation / configuration error
  3  HTTP / API error
  1  unexpected internal error
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

EXIT_CODES: dict[str, int] = {
    "OK": 0,
    "VALIDATION_ERROR": 2,
    "CONFIG_ERROR": 2,
    "API_ERROR": 3,
    "INTERNAL_ERROR": 1,
}


class _ParserError(Exception):
    """Raised by _SafeParser instead of calling sys.exit(2)."""


class _SafeParser(argparse.ArgumentParser):
    """ArgumentParser that raises _ParserError on bad/missing args."""

    def error(self, message: str) -> None:
        raise _ParserError(message)


class PaperTradingApiClient:
    """Lightweight HTTP client for the paper trading FastAPI backend."""

    TIMEOUT: float = 30.0

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        raw = base_url or os.environ.get("PAPER_TRADING_API_BASE_URL") or "http://localhost:8000"
        self.base_url = raw.rstrip("/")
        token = token or os.environ.get("PAPER_TRADING_API_TOKEN")
        if not token:
            raise ValueError("PAPER_TRADING_API_TOKEN is not set and no --token flag provided")
        self.token = token
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.token}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.TIMEOUT)
        resp = self._session.request(method, url, **kwargs)
        if resp.status_code == 204:
            return {"success": True, "message": "Deleted successfully"}
        resp.raise_for_status()
        return resp.json()

    def create_account(
        self,
        name: str,
        initial_cash: Decimal,
        fee_preset: str | None = None,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "initial_cash": str(initial_cash)}
        if fee_preset is not None:
            body["fee_preset"] = fee_preset
        if commission_rate is not None:
            body["commission_rate"] = str(commission_rate)
        if min_commission is not None:
            body["min_commission"] = str(min_commission)
        if stamp_duty_rate is not None:
            body["stamp_duty_rate"] = str(stamp_duty_rate)
        if transfer_fee_rate is not None:
            body["transfer_fee_rate"] = str(transfer_fee_rate)
        return self._request("POST", "/paper/accounts", json=body)

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/paper/accounts")

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/paper/accounts/{account_id}")

    def delete_account(self, account_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/paper/accounts/{account_id}")

    def update_account_fees(
        self,
        account_id: int,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if commission_rate is not None:
            body["commission_rate"] = str(commission_rate)
        if min_commission is not None:
            body["min_commission"] = str(min_commission)
        if stamp_duty_rate is not None:
            body["stamp_duty_rate"] = str(stamp_duty_rate)
        if transfer_fee_rate is not None:
            body["transfer_fee_rate"] = str(transfer_fee_rate)
        return self._request("PATCH", f"/paper/accounts/{account_id}", json=body)

    def list_positions(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/positions")

    def list_cash_ledger(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/cash-ledger")

    def create_order(
        self,
        account_id: int,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: str,
        idempotency_key: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "limit_price": str(limit_price),
            "trade_date": trade_date,
        }
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if comment is not None:
            body["comment"] = comment
        return self._request("POST", f"/paper/accounts/{account_id}/orders", json=body)

    def list_orders(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/orders")

    def get_order(self, order_id: int) -> dict[str, Any]:
        return self._request("GET", f"/paper/orders/{order_id}")

    def cancel_order(self, order_id: int) -> dict[str, Any]:
        return self._request("POST", f"/paper/orders/{order_id}/cancel")

    def delete_order(self, order_id: int) -> None:
        self._request("DELETE", f"/paper/orders/{order_id}")

    def update_order_comment(self, order_id: int, comment: str | None) -> dict[str, Any]:
        return self._request("PATCH", f"/paper/orders/{order_id}/comment", json={"comment": comment})

    def list_order_validity_checks(self, account_id: int, order_id: int) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/paper/accounts/{account_id}/orders/{order_id}/validity-checks",
        )

    def list_trades(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/trades")

    def run_matching(self, trade_date: str, account_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"trade_date": trade_date}
        if account_id is not None:
            body["account_id"] = account_id
        return self._request("POST", "/paper/matching/runs", json=body)

    def list_matching_runs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/paper/matching/runs")

    def get_matching_run(self, run_id: int) -> dict[str, Any]:
        return self._request("GET", f"/paper/matching/runs/{run_id}")

    def list_snapshots(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/snapshots")

    def deposit_cash(
        self, account_id: int, amount: Decimal, trade_date: str, note: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"amount": str(amount), "trade_date": trade_date}
        if note is not None:
            body["note"] = note
        return self._request("POST", f"/paper/accounts/{account_id}/cash/deposit", json=body)

    def withdraw_cash(
        self, account_id: int, amount: Decimal, trade_date: str, note: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"amount": str(amount), "trade_date": trade_date}
        if note is not None:
            body["note"] = note
        return self._request("POST", f"/paper/accounts/{account_id}/cash/withdraw", json=body)

    def import_positions(self, account_id: int, positions: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/paper/accounts/{account_id}/positions/import",
            json={"positions": positions},
        )


def run_paper_trading_matching(
    trade_date: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    _validate_trade_date(trade_date)
    client = PaperTradingApiClient(base_url=base_url, token=token)
    return client.run_matching(trade_date=trade_date, account_id=account_id)


def _add_account_subparsers(subparsers: Any) -> None:
    acct = subparsers.add_parser("account", help="Manage paper trading accounts")
    acct_sub = acct.add_subparsers(dest="account_command", required=True, parser_class=_SafeParser)
    p_create = acct_sub.add_parser("create", help="Create a new account")
    p_create.add_argument("--name", required=True, help="Account name")
    p_create.add_argument("--initial-cash", required=True, help="Initial cash amount")
    p_create.add_argument("--fee-preset", default=None, help="Fee preset name (default: a_share)")
    p_create.add_argument("--commission-rate", default=None, help="Commission rate override")
    p_create.add_argument("--min-commission", default=None, help="Minimum commission override")
    p_create.add_argument("--stamp-duty-rate", default=None, help="Stamp duty rate override")
    p_create.add_argument("--transfer-fee-rate", default=None, help="Transfer fee rate override")
    acct_sub.add_parser("list", help="List all accounts")
    p_get = acct_sub.add_parser("get", help="Get account details")
    p_get.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_delete = acct_sub.add_parser("delete", help="Delete an account")
    p_delete.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_pos = acct_sub.add_parser("positions", help="List account positions")
    p_pos.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_cl = acct_sub.add_parser("cash-ledger", help="List cash ledger entries")
    p_cl.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_import = acct_sub.add_parser("import-positions", help="Import existing holdings from CSV")
    p_import.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_import.add_argument(
        "--file", required=True, help="Path to CSV (columns: symbol,quantity,cost_price,buy_trade_date)"
    )
    p_deposit = acct_sub.add_parser("deposit", help="Deposit cash into an account")
    p_deposit.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_deposit.add_argument("--amount", required=True, help="Positive cash amount")
    p_deposit.add_argument("--trade-date", required=True, help="Effective date YYYY-MM-DD")
    p_deposit.add_argument("--note", default=None, help="Optional note")
    p_withdraw = acct_sub.add_parser("withdraw", help="Withdraw available cash from an account")
    p_withdraw.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_withdraw.add_argument("--amount", required=True, help="Positive cash amount")
    p_withdraw.add_argument("--trade-date", required=True, help="Effective date YYYY-MM-DD")
    p_withdraw.add_argument("--note", default=None, help="Optional note")
    p_update = acct_sub.add_parser("update-fee", help="Update account fee fields")
    p_update.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_update.add_argument("--commission-rate", default=None, help="Commission rate override")
    p_update.add_argument("--min-commission", default=None, help="Minimum commission override")
    p_update.add_argument("--stamp-duty-rate", default=None, help="Stamp duty rate override")
    p_update.add_argument("--transfer-fee-rate", default=None, help="Transfer fee rate override")


def _add_order_subparsers(subparsers: Any) -> None:
    order = subparsers.add_parser("order", help="Manage paper trading orders")
    order_sub = order.add_subparsers(dest="order_command", required=True, parser_class=_SafeParser)
    p_create = order_sub.add_parser("create", help="Place a new order")
    p_create.add_argument("--account-id", type=int, required=True)
    p_create.add_argument("--symbol", required=True)
    p_create.add_argument("--side", required=True, choices=["buy", "sell"])
    p_create.add_argument("--quantity", type=int, required=True)
    p_create.add_argument("--limit-price", required=True)
    p_create.add_argument("--trade-date", required=True)
    p_create.add_argument("--idempotency-key", default=None)
    p_create.add_argument("--comment", default=None)
    p_list = order_sub.add_parser("list", help="List orders for an account")
    p_list.add_argument("--account-id", type=int, required=True)
    p_get = order_sub.add_parser("get", help="Get order details")
    p_get.add_argument("--order-id", type=int, required=True)
    p_cancel = order_sub.add_parser("cancel", help="Cancel an order")
    p_cancel.add_argument("--order-id", type=int, required=True)
    p_vc = order_sub.add_parser("validity-checks", help="List order validity checks")
    p_vc.add_argument("--account-id", type=int, required=True)
    p_vc.add_argument("--order-id", type=int, required=True)
    p_uc = order_sub.add_parser("update-comment", help="Update order comment")
    p_uc.add_argument("--order-id", type=int, required=True)
    p_uc.add_argument("--comment", required=True)
    p_delete = order_sub.add_parser("delete", help="Delete an order and rebuild account history")
    p_delete.add_argument("--order-id", type=int, required=True)


def _add_trade_subparsers(subparsers: Any) -> None:
    trade = subparsers.add_parser("trade", help="List trades")
    trade_sub = trade.add_subparsers(dest="trade_command", required=True, parser_class=_SafeParser)
    p_list = trade_sub.add_parser("list", help="List trades for an account")
    p_list.add_argument("--account-id", type=int, required=True)


def _add_matching_subparsers(subparsers: Any) -> None:
    match = subparsers.add_parser("matching", help="Manage matching runs")
    match_sub = match.add_subparsers(dest="matching_command", required=True, parser_class=_SafeParser)
    p_run = match_sub.add_parser("run", help="Run matching")
    p_run.add_argument("--trade-date", required=True)
    p_run.add_argument("--account-id", type=int, default=None)
    match_sub.add_parser("list", help="List matching runs")
    p_get = match_sub.add_parser("get", help="Get matching run details")
    p_get.add_argument("--run-id", type=int, required=True)


def _add_snapshot_subparsers(subparsers: Any) -> None:
    snap = subparsers.add_parser("snapshot", help="List account snapshots")
    snap_sub = snap.add_subparsers(dest="snapshot_command", required=True, parser_class=_SafeParser)
    p_list = snap_sub.add_parser("list", help="List snapshots for an account")
    p_list.add_argument("--account-id", type=int, required=True)


def build_parser() -> _SafeParser:
    parser = _SafeParser(
        description="Paper trading API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--token", default=None, help="API bearer token")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_SafeParser)
    _add_account_subparsers(subparsers)
    _add_order_subparsers(subparsers)
    _add_trade_subparsers(subparsers)
    _add_matching_subparsers(subparsers)
    _add_snapshot_subparsers(subparsers)
    return parser


def _emit_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, default=str))


def _emit_text(data: Any, command: str | None, subcommand: str | None) -> None:
    if data is None:
        print("(no data)")
        return
    if isinstance(data, dict):
        _print_dict(data)
        return
    if isinstance(data, list):
        if not data:
            print("(empty)")
            return
        for item in data:
            if isinstance(item, dict):
                _print_dict(item)
            else:
                print(item)
            print("---")
        return
    print(data)


def _print_dict(d: dict[str, Any]) -> None:
    for key, value in d.items():
        if value is None:
            continue
        label = key.replace("_", " ").title()
        print(f"  {label}: {value}")


def _parse_decimal(value: str, label: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise _ParserError(f"invalid {label}: {value!r} is not a valid decimal number") from None


def _parse_non_negative_decimal(value: str, label: str) -> Decimal:
    parsed = _parse_decimal(value, label)
    if parsed < 0:
        raise _ParserError(f"invalid {label}: must be non-negative")
    return parsed


def _validate_trade_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise _ParserError(f"invalid --trade-date: {value!r} is not a valid YYYY-MM-DD date")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise _ParserError(f"invalid --trade-date: {value!r} is not a valid calendar date") from None
    return value


def _handle_account(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    cmd = args.account_command
    if cmd == "create":
        kwargs: dict[str, Any] = {
            "name": args.name,
            "initial_cash": _parse_decimal(args.initial_cash, "--initial-cash"),
        }
        if args.fee_preset is not None:
            kwargs["fee_preset"] = args.fee_preset
        if args.commission_rate is not None:
            kwargs["commission_rate"] = _parse_decimal(args.commission_rate, "--commission-rate")
        if args.min_commission is not None:
            kwargs["min_commission"] = _parse_decimal(args.min_commission, "--min-commission")
        if args.stamp_duty_rate is not None:
            kwargs["stamp_duty_rate"] = _parse_decimal(args.stamp_duty_rate, "--stamp-duty-rate")
        if args.transfer_fee_rate is not None:
            kwargs["transfer_fee_rate"] = _parse_decimal(args.transfer_fee_rate, "--transfer-fee-rate")
        return client.create_account(**kwargs)
    if cmd == "list":
        return client.list_accounts()
    if cmd == "get":
        return client.get_account(account_id=args.account_id)
    if cmd == "delete":
        return client.delete_account(account_id=args.account_id)
    if cmd == "positions":
        return client.list_positions(account_id=args.account_id)
    if cmd == "cash-ledger":
        return client.list_cash_ledger(account_id=args.account_id)
    if cmd == "deposit":
        _validate_trade_date(args.trade_date)
        return client.deposit_cash(args.account_id, _parse_decimal(args.amount, "amount"), args.trade_date, args.note)
    if cmd == "withdraw":
        _validate_trade_date(args.trade_date)
        return client.withdraw_cash(args.account_id, _parse_decimal(args.amount, "amount"), args.trade_date, args.note)
    if cmd == "import-positions":
        return _handle_import_positions(client, args)
    if cmd == "update-fee":
        kwargs: dict[str, Any] = {}
        if args.commission_rate is not None:
            kwargs["commission_rate"] = _parse_non_negative_decimal(args.commission_rate, "--commission-rate")
        if args.min_commission is not None:
            kwargs["min_commission"] = _parse_non_negative_decimal(args.min_commission, "--min-commission")
        if args.stamp_duty_rate is not None:
            kwargs["stamp_duty_rate"] = _parse_non_negative_decimal(args.stamp_duty_rate, "--stamp-duty-rate")
        if args.transfer_fee_rate is not None:
            kwargs["transfer_fee_rate"] = _parse_non_negative_decimal(
                args.transfer_fee_rate,
                "--transfer-fee-rate",
            )
        if not kwargs:
            raise _ParserError("at least one fee field is required")
        return client.update_account_fees(account_id=args.account_id, **kwargs)
    raise _ParserError(f"unknown account command: {cmd}")


def _validate_buy_trade_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise _ParserError(f"invalid buy_trade_date: {value!r} is not a valid YYYY-MM-DD date")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise _ParserError(f"invalid buy_trade_date: {value!r} is not a valid calendar date") from None
    return value


def _handle_import_positions(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    import csv

    try:
        with open(args.file, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        raise _ParserError(f"file not found: {args.file}") from None

    required = {"symbol", "quantity", "cost_price", "buy_trade_date"}
    if not rows:
        raise _ParserError("CSV file is empty (no data rows)")
    missing = required - set(rows[0].keys())
    if missing:
        raise _ParserError(f"CSV missing required columns: {', '.join(sorted(missing))}")

    positions: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):
        symbol = row.get("symbol", "").strip()
        if not symbol:
            raise _ParserError(f"row {i}: symbol is required")
        try:
            quantity = int(row["quantity"])
        except (ValueError, TypeError):
            raise _ParserError(f"row {i}: quantity must be an integer")
        if quantity <= 0:
            raise _ParserError(f"row {i}: quantity must be positive")
        try:
            cost_price = str(Decimal(row["cost_price"]))
        except Exception:
            raise _ParserError(f"row {i}: cost_price is not a valid decimal")
        if Decimal(row["cost_price"]) < 0:
            raise _ParserError(f"row {i}: cost_price must be non-negative")
        buy_trade_date = _validate_buy_trade_date(row.get("buy_trade_date", ""))
        positions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "cost_price": cost_price,
                "buy_trade_date": buy_trade_date,
            }
        )

    return client.import_positions(account_id=args.account_id, positions=positions)


def _handle_order(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    cmd = args.order_command
    if cmd == "create":
        return client.create_order(
            account_id=args.account_id,
            symbol=args.symbol,
            side=args.side,
            quantity=args.quantity,
            limit_price=_parse_decimal(args.limit_price, "--limit-price"),
            trade_date=_validate_trade_date(args.trade_date),
            idempotency_key=args.idempotency_key,
            comment=args.comment,
        )
    if cmd == "list":
        return client.list_orders(account_id=args.account_id)
    if cmd == "get":
        return client.get_order(order_id=args.order_id)
    if cmd == "cancel":
        return client.cancel_order(order_id=args.order_id)
    if cmd == "validity-checks":
        return client.list_order_validity_checks(account_id=args.account_id, order_id=args.order_id)
    if cmd == "update-comment":
        return client.update_order_comment(order_id=args.order_id, comment=args.comment)
    if cmd == "delete":
        client.delete_order(order_id=args.order_id)
        return {"deleted": True, "order_id": args.order_id}
    raise _ParserError(f"unknown order command: {cmd}")


def _handle_trade(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    cmd = args.trade_command
    if cmd == "list":
        return client.list_trades(account_id=args.account_id)
    raise _ParserError(f"unknown trade command: {cmd}")


def _handle_matching(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    cmd = args.matching_command
    if cmd == "run":
        return client.run_matching(trade_date=_validate_trade_date(args.trade_date), account_id=args.account_id)
    if cmd == "list":
        return client.list_matching_runs()
    if cmd == "get":
        return client.get_matching_run(run_id=args.run_id)
    raise _ParserError(f"unknown matching command: {cmd}")


def _handle_snapshot(client: PaperTradingApiClient, args: argparse.Namespace) -> Any:
    cmd = args.snapshot_command
    if cmd == "list":
        return client.list_snapshots(account_id=args.account_id)
    raise _ParserError(f"unknown snapshot command: {cmd}")


_HANDLERS: dict[str, Any] = {
    "account": _handle_account,
    "order": _handle_order,
    "trade": _handle_trade,
    "matching": _handle_matching,
    "snapshot": _handle_snapshot,
}


def main(argv: list[str] | None = None, client: PaperTradingApiClient | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _ParserError as exc:
        _emit({"success": False, "error": str(exc)}, json_output="--json" in (argv or []))
        return EXIT_CODES["VALIDATION_ERROR"]

    try:
        if client is None:
            client = PaperTradingApiClient(base_url=args.base_url, token=args.token)
        else:
            if args.base_url is not None:
                client.base_url = args.base_url.rstrip("/")
                client._session.headers.pop("Host", None)  # noqa: SLF001
            if args.token is not None:
                client.token = args.token
                client._session.headers["Authorization"] = f"Bearer {args.token}"

        handler = _HANDLERS.get(args.command)
        if handler is None:
            raise _ParserError(f"unknown command: {args.command}")

        data = handler(client, args)
        if args.json_output:
            _emit_json(data)
        else:
            _emit_text(data, args.command, _get_subcommand(args))
        return EXIT_CODES["OK"]

    except _ParserError as exc:
        _emit({"success": False, "error": str(exc)}, json_output=args.json_output)
        return EXIT_CODES["VALIDATION_ERROR"]
    except ValueError as exc:
        msg = str(exc)
        _emit({"success": False, "error": msg}, json_output=args.json_output)
        if "token" in msg.lower():
            return EXIT_CODES["CONFIG_ERROR"]
        return EXIT_CODES["VALIDATION_ERROR"]
    except requests.RequestException as exc:
        _emit({"success": False, "error": f"API error: {exc}"}, json_output=args.json_output)
        return EXIT_CODES["API_ERROR"]
    except Exception as exc:
        _emit({"success": False, "error": f"Internal error: {exc}"}, json_output=getattr(args, "json_output", False))
        return EXIT_CODES["INTERNAL_ERROR"]


def _get_subcommand(args: argparse.Namespace) -> str | None:
    for attr in ("account_command", "order_command", "trade_command", "matching_command", "snapshot_command"):
        val = getattr(args, attr, None)
        if val is not None:
            return val
    return None


def _emit(data: Any, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(data, ensure_ascii=False, default=str))
    else:
        if isinstance(data, dict):
            for key, value in data.items():
                if value is not None:
                    print(f"{key}: {value}")
        else:
            print(data)


if __name__ == "__main__":
    raise SystemExit(main())
