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
               --limit-price PRICE --trade-date YYYY-MM-DD [--idempotency-key KEY]
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

    def create_account(self, name: str, initial_cash: Decimal) -> dict[str, Any]:
        return self._request(
            "POST",
            "/paper/accounts",
            json={"name": name, "initial_cash": str(initial_cash)},
        )

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/paper/accounts")

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/paper/accounts/{account_id}")

    def delete_account(self, account_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/paper/accounts/{account_id}")

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
        return self._request("POST", f"/paper/accounts/{account_id}/orders", json=body)

    def list_orders(self, account_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/paper/accounts/{account_id}/orders")

    def get_order(self, order_id: int) -> dict[str, Any]:
        return self._request("GET", f"/paper/orders/{order_id}")

    def cancel_order(self, order_id: int) -> dict[str, Any]:
        return self._request("POST", f"/paper/orders/{order_id}/cancel")

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


def _add_account_subparsers(subparsers: Any) -> None:
    acct = subparsers.add_parser("account", help="Manage paper trading accounts")
    acct_sub = acct.add_subparsers(dest="account_command", required=True, parser_class=_SafeParser)
    p_create = acct_sub.add_parser("create", help="Create a new account")
    p_create.add_argument("--name", required=True, help="Account name")
    p_create.add_argument("--initial-cash", required=True, help="Initial cash amount")
    acct_sub.add_parser("list", help="List all accounts")
    p_get = acct_sub.add_parser("get", help="Get account details")
    p_get.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_delete = acct_sub.add_parser("delete", help="Delete an account")
    p_delete.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_pos = acct_sub.add_parser("positions", help="List account positions")
    p_pos.add_argument("--account-id", type=int, required=True, help="Account ID")
    p_cl = acct_sub.add_parser("cash-ledger", help="List cash ledger entries")
    p_cl.add_argument("--account-id", type=int, required=True, help="Account ID")


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
    p_list = order_sub.add_parser("list", help="List orders for an account")
    p_list.add_argument("--account-id", type=int, required=True)
    p_get = order_sub.add_parser("get", help="Get order details")
    p_get.add_argument("--order-id", type=int, required=True)
    p_cancel = order_sub.add_parser("cancel", help="Cancel an order")
    p_cancel.add_argument("--order-id", type=int, required=True)
    p_vc = order_sub.add_parser("validity-checks", help="List order validity checks")
    p_vc.add_argument("--account-id", type=int, required=True)
    p_vc.add_argument("--order-id", type=int, required=True)


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
        return client.create_account(name=args.name, initial_cash=_parse_decimal(args.initial_cash, "--initial-cash"))
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
    raise _ParserError(f"unknown account command: {cmd}")


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
        )
    if cmd == "list":
        return client.list_orders(account_id=args.account_id)
    if cmd == "get":
        return client.get_order(order_id=args.order_id)
    if cmd == "cancel":
        return client.cancel_order(order_id=args.order_id)
    if cmd == "validity-checks":
        return client.list_order_validity_checks(account_id=args.account_id, order_id=args.order_id)
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
