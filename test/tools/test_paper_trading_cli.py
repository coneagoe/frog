"""Tests for tools.paper_trading_cli — paper trading API CLI wrapper."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from tools.paper_trading_cli import EXIT_CODES, main, run_paper_trading_matching

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(**kwargs) -> MagicMock:
    """Build a minimal PaperTradingApiClient mock with success returns."""
    client = MagicMock(**kwargs)
    client.base_url = "http://localhost:8000"
    client.token = "test-token"
    if not kwargs:
        # Default success payloads
        client.create_account.return_value = {
            "id": 1,
            "name": "Test",
            "initial_cash": "10000.00",
            "status": "active",
            "base_currency": "CNY",
        }
        client.list_accounts.return_value = [
            {
                "id": 1,
                "name": "Test",
                "initial_cash": "10000.00",
                "status": "active",
                "base_currency": "CNY",
            }
        ]
        client.get_account.return_value = {
            "id": 1,
            "name": "Test",
            "initial_cash": "10000.00",
            "status": "active",
            "base_currency": "CNY",
        }
        client.delete_account.return_value = {"success": True, "message": "Account deleted"}
        client.list_positions.return_value = [
            {
                "symbol": "AAPL",
                "total_quantity": 100,
                "frozen_quantity": 0,
                "cost_amount": "15000.00",
                "realized_pnl": "500.00",
            }
        ]
        client.list_cash_ledger.return_value = [
            {
                "id": 1,
                "account_id": 1,
                "event_type": "deposit",
                "amount": "10000.00",
                "note": "initial deposit",
            }
        ]
        client.create_order.return_value = {
            "id": 10,
            "account_id": 1,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "limit_price": "150.00",
            "trade_date": "2024-01-15",
            "status": "pending",
            "filled_quantity": 0,
            "frozen_cash": "15000.00",
            "frozen_quantity": 0,
            "rejection_code": None,
            "rejection_reason": None,
            "validity_status": None,
            "validity_reason": None,
            "validity_checked_at": None,
        }
        client.list_orders.return_value = [
            {
                "id": 10,
                "account_id": 1,
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 100,
                "limit_price": "150.00",
                "trade_date": "2024-01-15",
                "status": "pending",
                "filled_quantity": 0,
                "frozen_cash": "15000.00",
                "frozen_quantity": 0,
                "rejection_code": None,
                "rejection_reason": None,
                "validity_status": None,
                "validity_reason": None,
                "validity_checked_at": None,
            }
        ]
        client.get_order.return_value = {
            "id": 10,
            "account_id": 1,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "limit_price": "150.00",
            "trade_date": "2024-01-15",
            "status": "filled",
            "filled_quantity": 100,
            "frozen_cash": "0.00",
            "frozen_quantity": 0,
            "rejection_code": None,
            "rejection_reason": None,
            "validity_status": None,
            "validity_reason": None,
            "validity_checked_at": None,
        }
        client.cancel_order.return_value = {
            "id": 10,
            "account_id": 1,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "limit_price": "150.00",
            "trade_date": "2024-01-15",
            "status": "cancelled",
            "filled_quantity": 0,
            "frozen_cash": "0.00",
            "frozen_quantity": 0,
            "rejection_code": None,
            "rejection_reason": None,
            "validity_status": None,
            "validity_reason": None,
            "validity_checked_at": None,
        }
        client.list_order_validity_checks.return_value = [
            {
                "id": 1,
                "order_id": 10,
                "account_id": 1,
                "symbol": "AAPL",
                "trade_date": "2024-01-15",
                "side": "buy",
                "input_price": "150.00",
                "daily_low": "148.00",
                "daily_high": "152.00",
                "limit_up_price": "165.00",
                "limit_down_price": "135.00",
                "touched_limit_up": False,
                "touched_limit_down": False,
                "price_in_range": True,
                "status": "passed",
                "reason_code": "OK",
                "reason_detail": None,
                "data_granularity": "daily",
                "created_at": "2024-01-15T10:00:00",
            }
        ]
        client.list_trades.return_value = [
            {
                "id": 100,
                "order_id": 10,
                "account_id": 1,
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 100,
                "price": "150.00",
                "amount": "15000.00",
                "fees": "15.00",
                "trade_date": "2024-01-15",
            }
        ]
        client.run_matching.return_value = {
            "id": 1,
            "trade_date": "2024-01-15",
            "account_id": None,
            "status": "completed",
            "processed_count": 10,
            "filled_count": 5,
            "skipped_count": 3,
            "rejected_count": 1,
            "failed_count": 1,
        }
        client.list_matching_runs.return_value = [
            {
                "id": 1,
                "trade_date": "2024-01-15",
                "account_id": None,
                "status": "completed",
                "processed_count": 10,
                "filled_count": 5,
                "skipped_count": 3,
                "rejected_count": 1,
                "failed_count": 1,
            }
        ]
        client.get_matching_run.return_value = {
            "id": 1,
            "trade_date": "2024-01-15",
            "account_id": None,
            "status": "completed",
            "processed_count": 10,
            "filled_count": 5,
            "skipped_count": 3,
            "rejected_count": 1,
            "failed_count": 1,
        }
        client.list_snapshots.return_value = [
            {
                "id": 1,
                "account_id": 1,
                "trade_date": "2024-01-15",
                "cash_available": "5000.00",
                "cash_frozen": "15000.00",
                "market_value": "15000.00",
                "total_assets": "35000.00",
                "realized_pnl": "500.00",
                "unrealized_pnl": "0.00",
                "position_count": 1,
                "order_count": 1,
                "trade_count": 1,
            }
        ]
    return client


# ---------------------------------------------------------------------------
# Account commands
# ---------------------------------------------------------------------------


class TestAccountCreate:
    def test_create_account_calls_client(self):
        client = _mock_client()
        exit_code = main(
            ["account", "create", "--name", "MyAccount", "--initial-cash", "50000"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        client.create_account.assert_called_once_with(name="MyAccount", initial_cash=Decimal("50000"))

    def test_create_account_json_output(self, capsys):
        client = _mock_client()
        exit_code = main(
            [
                "--json",
                "account",
                "create",
                "--name",
                "MyAccount",
                "--initial-cash",
                "50000",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == 1
        assert payload["name"] == "Test"

    def test_create_account_text_output(self, capsys):
        client = _mock_client()
        exit_code = main(
            ["account", "create", "--name", "MyAccount", "--initial-cash", "50000"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        out = capsys.readouterr().out
        # The mock returns name "Test" regardless of the arg we pass
        assert "Test" in out
        assert "1" in out
        assert "active" in out
        assert "1" in out

    def test_create_missing_name_is_validation_error(self):
        exit_code = main(["account", "create", "--initial-cash", "50000"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_missing_initial_cash_is_validation_error(self):
        exit_code = main(["account", "create", "--name", "X"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_bad_initial_cash_is_validation_error(self):
        """Malformed --initial-cash must not produce Internal Error."""
        exit_code = main(["account", "create", "--name", "X", "--initial-cash", "not-a-number"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_account_passes_fee_config(self):
        client = _mock_client()
        with patch("tools.paper_trading_cli.PaperTradingApiClient", return_value=client):
            rc = main(
                [
                    "--base-url",
                    "http://localhost:8000",
                    "--token",
                    "token",
                    "account",
                    "create",
                    "--name",
                    "custom-fee",
                    "--initial-cash",
                    "100000.00",
                    "--fee-preset",
                    "a_share",
                    "--commission-rate",
                    "0.00025",
                    "--min-commission",
                    "3.00",
                    "--stamp-duty-rate",
                    "0.0004",
                    "--transfer-fee-rate",
                    "0.00002",
                ]
            )

        assert rc == EXIT_CODES["OK"]
        client.create_account.assert_called_once_with(
            name="custom-fee",
            initial_cash=Decimal("100000.00"),
            fee_preset="a_share",
            commission_rate=Decimal("0.00025"),
            min_commission=Decimal("3.00"),
            stamp_duty_rate=Decimal("0.0004"),
            transfer_fee_rate=Decimal("0.00002"),
        )


class TestAccountList:
    def test_list_accounts_calls_client(self):
        client = _mock_client()
        exit_code = main(["account", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_accounts.assert_called_once_with()

    def test_list_accounts_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "account", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert len(payload) == 1

    def test_list_accounts_text(self, capsys):
        client = _mock_client()
        exit_code = main(["account", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        out = capsys.readouterr().out
        assert "Test" in out
        assert "1" in out


class TestAccountGet:
    def test_get_account_calls_client(self):
        client = _mock_client()
        exit_code = main(["account", "get", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.get_account.assert_called_once_with(account_id=1)

    def test_get_account_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "account", "get", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == 1

    def test_get_account_missing_id_is_validation_error(self):
        exit_code = main(["account", "get"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestAccountDelete:
    def test_delete_account_calls_client(self):
        client = _mock_client()
        exit_code = main(["account", "delete", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.delete_account.assert_called_once_with(account_id=1)

    def test_delete_account_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "account", "delete", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True

    def test_delete_account_text(self, capsys):
        client = _mock_client()
        exit_code = main(["account", "delete", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "deleted" in capsys.readouterr().out.lower()

    def test_delete_missing_id_is_validation_error(self):
        exit_code = main(["account", "delete"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestAccountPositions:
    def test_positions_calls_client(self):
        client = _mock_client()
        exit_code = main(["account", "positions", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_positions.assert_called_once_with(account_id=1)

    def test_positions_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "account", "positions", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["symbol"] == "AAPL"

    def test_positions_text(self, capsys):
        client = _mock_client()
        exit_code = main(["account", "positions", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "AAPL" in capsys.readouterr().out


class TestAccountCashLedger:
    def test_cash_ledger_calls_client(self):
        client = _mock_client()
        exit_code = main(["account", "cash-ledger", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_cash_ledger.assert_called_once_with(account_id=1)

    def test_cash_ledger_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "account", "cash-ledger", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["event_type"] == "deposit"

    def test_cash_ledger_text(self, capsys):
        client = _mock_client()
        exit_code = main(["account", "cash-ledger", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "deposit" in capsys.readouterr().out


class TestAccountImportPositions:
    def test_import_positions_calls_client(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text(
            "symbol,quantity,cost_price,buy_trade_date\n000001,100,10.50,2026-01-15\n000002,200,20.00,2026-02-01\n"
        )
        client = _mock_client()
        client.import_positions.return_value = {"imported_count": 2, "positions": []}

        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )

        assert exit_code == EXIT_CODES["OK"]
        client.import_positions.assert_called_once_with(
            account_id=1,
            positions=[
                {"symbol": "000001", "quantity": 100, "cost_price": "10.50", "buy_trade_date": "2026-01-15"},
                {"symbol": "000002", "quantity": 200, "cost_price": "20.00", "buy_trade_date": "2026-02-01"},
            ],
        )

    def test_import_positions_json_output(self, tmp_path, capsys):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n000001,100,10.50,2026-01-15\n")
        client = _mock_client()
        client.import_positions.return_value = {"imported_count": 1, "positions": []}

        exit_code = main(
            ["--json", "account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )

        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["imported_count"] == 1

    def test_import_positions_missing_file_is_validation_error(self):
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", "/nonexistent/file.csv"],
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_missing_account_id_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n000001,100,10.50,2026-01-15\n")
        exit_code = main(
            ["account", "import-positions", "--file", str(csv_path)],
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_empty_csv_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n")
        client = _mock_client()
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_missing_columns_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("symbol,quantity\n000001,100\n")
        client = _mock_client()
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_strips_whitespace_from_symbols(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n  000001  ,100,10.50,2026-01-15\n")
        client = _mock_client()
        client.import_positions.return_value = {"imported_count": 1, "positions": []}

        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )

        assert exit_code == EXIT_CODES["OK"]
        client.import_positions.assert_called_once_with(
            account_id=1,
            positions=[
                {"symbol": "000001", "quantity": 100, "cost_price": "10.50", "buy_trade_date": "2026-01-15"},
            ],
        )

    def test_import_positions_bad_quantity_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n000001,not-int,10.50,2026-01-15\n")
        client = _mock_client()
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_bad_cost_price_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n000001,100,not-a-price,2026-01-15\n")
        client = _mock_client()
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_import_positions_bad_trade_date_is_validation_error(self, tmp_path):
        csv_path = tmp_path / "holdings.csv"
        csv_path.write_text("symbol,quantity,cost_price,buy_trade_date\n000001,100,10.50,not-a-date\n")
        client = _mock_client()
        exit_code = main(
            ["account", "import-positions", "--account-id", "1", "--file", str(csv_path)],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestAccountUpdateFee:
    def test_update_account_fees_calls_client_with_partial_payload(self):
        client = _mock_client()
        client.update_account_fees.return_value = client.get_account.return_value

        exit_code = main(
            [
                "account",
                "update-fee",
                "--account-id",
                "1",
                "--commission-rate",
                "0.0002",
                "--min-commission",
                "3",
            ],
            client=client,
        )

        assert exit_code == EXIT_CODES["OK"]
        client.update_account_fees.assert_called_once_with(
            account_id=1,
            commission_rate=Decimal("0.0002"),
            min_commission=Decimal("3"),
        )

    def test_update_account_fees_rejects_empty_payload(self):
        client = _mock_client()

        exit_code = main(["account", "update-fee", "--account-id", "1"], client=client)

        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_update_account_fees_rejects_negative_fee(self):
        client = _mock_client()

        exit_code = main(
            ["account", "update-fee", "--account-id", "1", "--commission-rate", "-0.0001"],
            client=client,
        )

        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.update_account_fees.assert_not_called()


# ---------------------------------------------------------------------------
# Order commands
# ---------------------------------------------------------------------------


class TestOrderCreate:
    def test_create_order_calls_client(self):
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-01-15",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        client.create_order.assert_called_once_with(
            account_id=1,
            symbol="AAPL",
            side="buy",
            quantity=100,
            limit_price=Decimal("150.00"),
            trade_date="2024-01-15",
            idempotency_key=None,
        )

    def test_create_order_with_idempotency_key(self):
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "sell",
                "--quantity",
                "50",
                "--limit-price",
                "160.00",
                "--trade-date",
                "2024-01-16",
                "--idempotency-key",
                "my-key-123",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        client.create_order.assert_called_once_with(
            account_id=1,
            symbol="AAPL",
            side="sell",
            quantity=50,
            limit_price=Decimal("160.00"),
            trade_date="2024-01-16",
            idempotency_key="my-key-123",
        )

    def test_create_order_json(self, capsys):
        client = _mock_client()
        exit_code = main(
            [
                "--json",
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-01-15",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == 10
        assert payload["status"] == "pending"

    def test_create_order_validation_missing_required(self):
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                # missing --limit-price and --trade-date
            ]
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_order_bad_side_is_validation_error(self):
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "invalid",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-01-15",
            ]
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_order_bad_quantity(self):
        """Non-integer quantity should fail argparse type conversion."""
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "not-int",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-01-15",
            ]
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_order_bad_limit_price_is_validation_error(self):
        """Malformed --limit-price must not produce Internal Error."""
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "not-a-price",
                "--trade-date",
                "2024-01-15",
            ]
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_create_order_bad_trade_date_is_validation_error(self, capsys):
        """Malformed --trade-date must return exit code 2 and not call client."""
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "not-a-date",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.create_order.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "not-a-date" in out

    def test_create_order_wrong_format_trade_date_is_validation_error(self, capsys):
        """Wrong date format (e.g. 01/15/2024) must also fail."""
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "01/15/2024",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.create_order.assert_not_called()

    def test_create_order_non_zero_padded_trade_date_is_validation_error(self, capsys):
        """Non-zero-padded date (e.g. 2024-1-5) must return exit code 2."""
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-1-5",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.create_order.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "2024-1-5" in out

    def test_create_order_impossible_calendar_date_is_validation_error(self, capsys):
        """Impossible date (e.g. 2024-02-30) must return exit code 2."""
        client = _mock_client()
        exit_code = main(
            [
                "order",
                "create",
                "--account-id",
                "1",
                "--symbol",
                "AAPL",
                "--side",
                "buy",
                "--quantity",
                "100",
                "--limit-price",
                "150.00",
                "--trade-date",
                "2024-02-30",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.create_order.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "2024-02-30" in out


class TestOrderList:
    def test_list_orders_calls_client(self):
        client = _mock_client()
        exit_code = main(["order", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_orders.assert_called_once_with(account_id=1)

    def test_list_orders_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "order", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)

    def test_list_orders_text(self, capsys):
        client = _mock_client()
        exit_code = main(["order", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "AAPL" in capsys.readouterr().out

    def test_list_orders_missing_account_id(self):
        exit_code = main(["order", "list"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestOrderGet:
    def test_get_order_calls_client(self):
        client = _mock_client()
        exit_code = main(["order", "get", "--order-id", "10"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.get_order.assert_called_once_with(order_id=10)

    def test_get_order_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "order", "get", "--order-id", "10"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == 10

    def test_get_order_missing_id(self):
        exit_code = main(["order", "get"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestOrderCancel:
    def test_cancel_order_calls_client(self):
        client = _mock_client()
        exit_code = main(["order", "cancel", "--order-id", "10"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.cancel_order.assert_called_once_with(order_id=10)

    def test_cancel_order_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "order", "cancel", "--order-id", "10"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "cancelled"

    def test_cancel_order_missing_id(self):
        exit_code = main(["order", "cancel"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


class TestOrderValidityChecks:
    def test_validity_checks_calls_client(self):
        client = _mock_client()
        exit_code = main(
            ["order", "validity-checks", "--account-id", "1", "--order-id", "10"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        client.list_order_validity_checks.assert_called_once_with(account_id=1, order_id=10)

    def test_validity_checks_json(self, capsys):
        client = _mock_client()
        exit_code = main(
            [
                "--json",
                "order",
                "validity-checks",
                "--account-id",
                "1",
                "--order-id",
                "10",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["status"] == "passed"

    def test_validity_checks_missing_args(self):
        exit_code = main(["order", "validity-checks", "--account-id", "1"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# Trade commands
# ---------------------------------------------------------------------------


class TestTradeList:
    def test_list_trades_calls_client(self):
        client = _mock_client()
        exit_code = main(["trade", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_trades.assert_called_once_with(account_id=1)

    def test_list_trades_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "trade", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["symbol"] == "AAPL"

    def test_list_trades_text(self, capsys):
        client = _mock_client()
        exit_code = main(["trade", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "AAPL" in capsys.readouterr().out

    def test_list_trades_missing_account_id(self):
        exit_code = main(["trade", "list"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# Matching commands
# ---------------------------------------------------------------------------


class TestMatchingRun:
    def test_run_paper_trading_matching_builds_client_and_returns_result(self):
        with patch("tools.paper_trading_cli.PaperTradingApiClient") as mock_cls:
            client = mock_cls.return_value
            client.run_matching.return_value = {"id": 123, "trade_date": "2024-01-15"}

            result = run_paper_trading_matching(
                "2024-01-15",
                base_url="http://paper-trading:8000",
                token="test-token",
            )

        mock_cls.assert_called_once_with(base_url="http://paper-trading:8000", token="test-token")
        client.run_matching.assert_called_once_with(trade_date="2024-01-15", account_id=None)
        assert result == {"id": 123, "trade_date": "2024-01-15"}

    def test_run_matching_calls_client(self):
        client = _mock_client()
        exit_code = main(["matching", "run", "--trade-date", "2024-01-15"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.run_matching.assert_called_once_with(trade_date="2024-01-15", account_id=None)

    def test_run_matching_with_account_id(self):
        client = _mock_client()
        exit_code = main(
            [
                "matching",
                "run",
                "--trade-date",
                "2024-01-15",
                "--account-id",
                "1",
            ],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        client.run_matching.assert_called_once_with(trade_date="2024-01-15", account_id=1)

    def test_run_matching_json(self, capsys):
        client = _mock_client()
        exit_code = main(
            ["--json", "matching", "run", "--trade-date", "2024-01-15"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "completed"

    def test_run_matching_missing_trade_date(self):
        exit_code = main(["matching", "run"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_run_matching_bad_trade_date_is_validation_error(self, capsys):
        """Malformed --trade-date must return exit code 2 and not call client."""
        client = _mock_client()
        exit_code = main(
            ["matching", "run", "--trade-date", "bad-date"],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.run_matching.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "bad-date" in out

    def test_run_matching_wrong_format_trade_date_is_validation_error(self, capsys):
        """Wrong date format (e.g. 2024/01/15) must also fail."""
        client = _mock_client()
        exit_code = main(
            ["matching", "run", "--trade-date", "2024/01/15"],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.run_matching.assert_not_called()

    def test_run_matching_non_zero_padded_trade_date_is_validation_error(self, capsys):
        """Non-zero-padded date (e.g. 2024-1-5) must return exit code 2."""
        client = _mock_client()
        exit_code = main(
            ["matching", "run", "--trade-date", "2024-1-5"],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.run_matching.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "2024-1-5" in out

    def test_run_matching_impossible_calendar_date_is_validation_error(self, capsys):
        """Impossible date (e.g. 2024-02-30) must return exit code 2."""
        client = _mock_client()
        exit_code = main(
            ["matching", "run", "--trade-date", "2024-02-30"],
            client=client,
        )
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
        client.run_matching.assert_not_called()
        out = capsys.readouterr().out
        assert "trade-date" in out.lower() or "2024-02-30" in out


class TestMatchingList:
    def test_list_matching_runs_calls_client(self):
        client = _mock_client()
        exit_code = main(["matching", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_matching_runs.assert_called_once_with()

    def test_list_matching_runs_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "matching", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["status"] == "completed"

    def test_list_matching_runs_text(self, capsys):
        client = _mock_client()
        exit_code = main(["matching", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "completed" in capsys.readouterr().out


class TestMatchingGet:
    def test_get_matching_run_calls_client(self):
        client = _mock_client()
        exit_code = main(["matching", "get", "--run-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.get_matching_run.assert_called_once_with(run_id=1)

    def test_get_matching_run_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "matching", "get", "--run-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert payload["id"] == 1

    def test_get_matching_run_missing_id(self):
        exit_code = main(["matching", "get"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# Snapshot commands
# ---------------------------------------------------------------------------


class TestSnapshotList:
    def test_list_snapshots_calls_client(self):
        client = _mock_client()
        exit_code = main(["snapshot", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        client.list_snapshots.assert_called_once_with(account_id=1)

    def test_list_snapshots_json(self, capsys):
        client = _mock_client()
        exit_code = main(["--json", "snapshot", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["total_assets"] == "35000.00"

    def test_list_snapshots_text(self, capsys):
        client = _mock_client()
        exit_code = main(["snapshot", "list", "--account-id", "1"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert "35000.00" in capsys.readouterr().out

    def test_list_snapshots_missing_account_id(self):
        exit_code = main(["snapshot", "list"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# Global flags & configuration
# ---------------------------------------------------------------------------


class TestGlobalFlags:
    def test_base_url_flag_overrides_default(self):
        client = _mock_client()
        exit_code = main(
            ["--base-url", "http://other:9000", "account", "list"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        # base_url is set on client object
        assert client.base_url == "http://other:9000"

    def test_token_flag_sets_client_token(self):
        client = _mock_client()
        exit_code = main(
            ["--token", "custom-token", "account", "list"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        assert client.token == "custom-token"

    def test_default_base_url(self):
        client = _mock_client()
        exit_code = main(["account", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert client.base_url == "http://localhost:8000"

    def test_base_url_trailing_slash_stripped(self):
        """Trailing slash on base_url must be stripped to avoid // in URLs."""
        client = _mock_client()
        exit_code = main(
            ["--base-url", "http://example.com:8000/", "account", "list"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        assert client.base_url == "http://example.com:8000"

    @patch.dict(os.environ, {"PAPER_TRADING_API_TOKEN": "env-token"})
    def test_token_from_env(self):
        """When no client is injected, main constructs one from env vars."""
        # Patch PaperTradingApiClient so no real HTTP calls happen
        with patch("tools.paper_trading_cli.PaperTradingApiClient") as mock_cls:
            mock_instance = _mock_client()
            mock_cls.return_value = mock_instance
            exit_code = main(["account", "list"])
        assert exit_code == EXIT_CODES["OK"]
        # The constructor was called with token=None, meaning it reads from env
        mock_cls.assert_called_once_with(base_url=None, token=None)
        assert mock_instance.token == "test-token"

    @patch.dict(os.environ, {"PAPER_TRADING_API_BASE_URL": "http://env-url:9000", "PAPER_TRADING_API_TOKEN": "tok"})
    def test_base_url_from_env(self):
        """When no client is injected, main constructs one using env vars."""
        with patch("tools.paper_trading_cli.PaperTradingApiClient") as mock_cls:
            mock_instance = _mock_client()
            mock_cls.return_value = mock_instance
            exit_code = main(["account", "list"])
        assert exit_code == EXIT_CODES["OK"]
        mock_cls.assert_called_once_with(base_url=None, token=None)

    @patch.dict(os.environ, {"PAPER_TRADING_API_BASE_URL": "http://env-url:9000"})
    def test_base_url_flag_overrides_env(self):
        client = _mock_client()
        exit_code = main(
            ["--base-url", "http://cli-url:8000", "account", "list"],
            client=client,
        )
        assert exit_code == EXIT_CODES["OK"]
        assert client.base_url == "http://cli-url:8000"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_token_is_config_error(self):
        """Without env var or --token, should be a config error."""
        exit_code = main(["account", "list"])
        assert exit_code == EXIT_CODES["CONFIG_ERROR"]

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_token_with_flag_ok(self):
        """--token flag should allow running without env var."""
        client = _mock_client()
        exit_code = main(["--token", "explicit", "account", "list"], client=client)
        assert exit_code == EXIT_CODES["OK"]
        assert client.token == "explicit"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_http_error_returns_exit_code_3(self, capsys):
        """API returning non-2xx should yield exit code 3."""
        client = _mock_client()
        client.list_accounts.side_effect = requests.exceptions.HTTPError("HTTP 500: Server Error")
        exit_code = main(["--json", "account", "list"], client=client)
        assert exit_code == EXIT_CODES["API_ERROR"]
        payload = json.loads(capsys.readouterr().out)
        assert "error" in payload or "success" in payload

    def test_unexpected_error_returns_exit_code_1(self, capsys):
        """Non-API exception from client yields exit code 1."""
        client = _mock_client()
        client.list_accounts.side_effect = RuntimeError("something unexpected")
        exit_code = main(["--json", "account", "list"], client=client)
        assert exit_code == EXIT_CODES["INTERNAL_ERROR"]

    def test_http_error_text_output(self, capsys):
        client = _mock_client()
        client.list_accounts.side_effect = requests.exceptions.HTTPError("HTTP 500")
        exit_code = main(["account", "list"], client=client)
        assert exit_code == EXIT_CODES["API_ERROR"]
        assert "error" in capsys.readouterr().out.lower()

    def test_validation_error_on_missing_command(self):
        exit_code = main([])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_validation_error_on_bad_command(self):
        exit_code = main(["nonexistent"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]

    def test_validation_error_on_bad_subcommand(self):
        exit_code = main(["account", "nonexistent"])
        assert exit_code == EXIT_CODES["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# Text output format details
# ---------------------------------------------------------------------------


class TestTextOutput:
    def test_account_list_text_shows_id_and_name(self, capsys):
        client = _mock_client()
        main(["account", "list"], client=client)
        out = capsys.readouterr().out
        assert "Test" in out
        assert "1" in out

    def test_order_list_text_shows_symbol_and_status(self, capsys):
        client = _mock_client()
        main(["order", "list", "--account-id", "1"], client=client)
        out = capsys.readouterr().out
        assert "AAPL" in out
        assert "pending" in out

    def test_matching_list_text_shows_date_and_status(self, capsys):
        client = _mock_client()
        main(["matching", "list"], client=client)
        out = capsys.readouterr().out
        assert "2024-01-15" in out
        assert "completed" in out

    def test_snapshot_list_text_shows_date_and_assets(self, capsys):
        client = _mock_client()
        main(["snapshot", "list", "--account-id", "1"], client=client)
        out = capsys.readouterr().out
        assert "2024-01-15" in out
        assert "35000.00" in out


# ---------------------------------------------------------------------------
# Client construction (integration test with mocked HTTP)
# ---------------------------------------------------------------------------


class TestClientConstruction:
    """Verify that when no client is passed, PaperTradingApiClient is constructed."""

    def test_client_init_from_env(self):
        """Verify PaperTradingApiClient reads env vars correctly."""
        from tools.paper_trading_cli import PaperTradingApiClient

        with patch.dict(
            os.environ,
            {
                "PAPER_TRADING_API_TOKEN": "env-token",
                "PAPER_TRADING_API_BASE_URL": "http://env:8000",
            },
        ):
            c = PaperTradingApiClient()
            assert c.token == "env-token"
            assert c.base_url == "http://env:8000"

    def test_client_init_default_base_url(self):
        """Without env var, base_url should be default."""
        from tools.paper_trading_cli import PaperTradingApiClient

        with patch.dict(os.environ, {"PAPER_TRADING_API_TOKEN": "tok"}, clear=True):
            c = PaperTradingApiClient()
            assert c.base_url == "http://localhost:8000"

    def test_client_init_missing_token_raises(self):
        """Without any token, constructor should raise ValueError."""
        from tools.paper_trading_cli import PaperTradingApiClient

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="token"):
                PaperTradingApiClient()

    def test_client_init_explicit_token_overrides_env(self):
        """Explicit token arg should take precedence."""
        from tools.paper_trading_cli import PaperTradingApiClient

        with patch.dict(os.environ, {"PAPER_TRADING_API_TOKEN": "env-tok"}, clear=True):
            c = PaperTradingApiClient(token="explicit-tok")
            assert c.token == "explicit-tok"

    def test_default_timeout_applied_to_requests(self):
        """All client requests must pass a timeout to avoid hangs."""
        from tools.paper_trading_cli import PaperTradingApiClient

        with patch.dict(os.environ, {"PAPER_TRADING_API_TOKEN": "tok"}, clear=True):
            client = PaperTradingApiClient()
        mock_resp = MagicMock(status_code=200, json=lambda: {})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            client.list_accounts()
        _, kwargs = mock_req.call_args
        assert kwargs.get("timeout") == PaperTradingApiClient.TIMEOUT
