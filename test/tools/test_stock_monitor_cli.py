import json
from unittest.mock import MagicMock

from tools.stock_monitor_cli import EXIT_INTERNAL_ERROR, EXIT_VALIDATION_ERROR, main


def test_add_command_parses_args_and_calls_service(capsys):
    service = MagicMock()
    service.add_target.return_value = {
        "success": True,
        "code": "OK",
        "message": "target created",
        "data": {"id": 1},
    }

    exit_code = main(
        [
            "target",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--condition",
            '{"type":"price_threshold","direction":"below","value":1500}',
            "--note",
            "watch",
            "--frequency",
            "daily",
            "--reset-mode",
            "auto",
        ],
        service=service,
    )

    assert exit_code == 0
    service.add_target.assert_called_once_with(
        stock_code="600519",
        market="A",
        condition='{"type":"price_threshold","direction":"below","value":1500}',
        note="watch",
        frequency="daily",
        reset_mode="auto",
        enabled=True,
        last_state=False,
    )
    assert "OK" in capsys.readouterr().out


def test_add_command_json_output_uses_service_payload(capsys):
    service = MagicMock()
    service.add_target.return_value = {
        "success": False,
        "code": "VALIDATION_ERROR",
        "message": "invalid condition",
        "data": None,
    }

    exit_code = main(
        [
            "--json",
            "target",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--condition",
            "not-json",
        ],
        service=service,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"


def test_add_command_returns_positive_exit_code_on_service_exception(capsys):
    service = MagicMock()
    service.add_target.side_effect = ValueError("bad input")

    exit_code = main(
        [
            "--json",
            "target",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--condition",
            '{"type":"price_threshold","direction":"below","value":1500}',
        ],
        service=service,
    )

    assert exit_code == EXIT_INTERNAL_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "INTERNAL_ERROR"


def test_target_update_command_calls_service_update():
    service = MagicMock()
    service.update.return_value = {"success": True, "code": "OK", "message": "updated", "data": {"id": 1}}

    exit_code = main(
        [
            "target",
            "update",
            "--target-id",
            "1",
            "--note",
            "new-note",
            "--disabled",
        ],
        service=service,
    )

    assert exit_code == 0
    service.update.assert_called_once_with(1, note="new-note", enabled=False)


def test_target_remove_list_get_and_status_commands_are_wired():
    service = MagicMock()
    service.remove.return_value = {"success": True, "code": "OK", "message": "removed", "data": {"id": 1}}
    service.list.return_value = {"success": True, "code": "OK", "message": "listed", "data": []}
    service.get.return_value = {"success": True, "code": "OK", "message": "fetched", "data": {"id": 1}}
    service.get_status.return_value = {"success": True, "code": "OK", "message": "status", "data": {"total": 1}}

    assert main(["target", "remove", "--target-id", "1"], service=service) == 0
    assert main(["target", "list", "--frequency", "daily", "--enabled"], service=service) == 0
    assert main(["target", "get", "--target-id", "1"], service=service) == 0
    assert main(["status"], service=service) == 0

    service.remove.assert_called_once_with(1)
    service.list.assert_called_once_with(frequency="daily", enabled=True)
    service.get.assert_called_once_with(1)
    service.get_status.assert_called_once_with()
