import json
from unittest.mock import MagicMock

from tools.stock_monitor_cli import (
    EXIT_INTERNAL_ERROR,
    EXIT_NOT_FOUND,
    EXIT_VALIDATION_ERROR,
    main,
)


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
    service.update.return_value = {
        "success": True,
        "code": "OK",
        "message": "updated",
        "data": {"id": 1},
    }

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
    service.remove.return_value = {
        "success": True,
        "code": "OK",
        "message": "removed",
        "data": {"id": 1},
    }
    service.list.return_value = {
        "success": True,
        "code": "OK",
        "message": "listed",
        "data": [],
    }
    service.get.return_value = {
        "success": True,
        "code": "OK",
        "message": "fetched",
        "data": {"id": 1},
    }
    service.get_status.return_value = {
        "success": True,
        "code": "OK",
        "message": "status",
        "data": {"total": 1},
    }

    assert main(["target", "remove", "--target-id", "1"], service=service) == 0
    assert (
        main(["target", "list", "--frequency", "daily", "--enabled"], service=service)
        == 0
    )
    assert main(["target", "get", "--target-id", "1"], service=service) == 0
    assert main(["status"], service=service) == 0

    service.remove.assert_called_once_with(1)
    service.list.assert_called_once_with(frequency="daily", enabled=True)
    service.get.assert_called_once_with(1)
    service.get_status.assert_called_once_with()


# ---------------------------------------------------------------------------
# Blackroom subcommand tests
# ---------------------------------------------------------------------------


def test_blackroom_add_parses_args_and_calls_service(capsys):
    bsvc = MagicMock()
    bsvc.add_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record created",
        "data": {"id": 1},
    }

    exit_code = main(
        [
            "blackroom",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--ban-days",
            "30",
        ],
        blackroom_service=bsvc,
    )

    assert exit_code == 0
    bsvc.add_record.assert_called_once_with(
        stock_code="600519", market="A", ban_days=30, note=None
    )
    assert "OK" in capsys.readouterr().out


def test_blackroom_add_with_note_calls_service(capsys):
    bsvc = MagicMock()
    bsvc.add_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record created",
        "data": {"id": 2},
    }

    exit_code = main(
        [
            "--json",
            "blackroom",
            "add",
            "--stock-code",
            "000001",
            "--market",
            "A",
            "--ban-days",
            "7",
            "--note",
            "watch",
        ],
        blackroom_service=bsvc,
    )

    assert exit_code == 0
    bsvc.add_record.assert_called_once_with(
        stock_code="000001", market="A", ban_days=7, note="watch"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["data"]["id"] == 2


def test_blackroom_update_command_sends_updates():
    bsvc = MagicMock()
    bsvc.update_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record updated",
        "data": {"id": 5},
    }

    exit_code = main(
        ["blackroom", "update", "--id", "5", "--ban-days", "60", "--disabled"],
        blackroom_service=bsvc,
    )

    assert exit_code == 0
    bsvc.update_record.assert_called_once_with(5, ban_days=60, enabled=False)


def test_blackroom_update_enabled_flag():
    bsvc = MagicMock()
    bsvc.update_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record updated",
        "data": {"id": 3},
    }

    exit_code = main(
        ["blackroom", "update", "--id", "3", "--note", "revised", "--enabled"],
        blackroom_service=bsvc,
    )

    assert exit_code == 0
    bsvc.update_record.assert_called_once_with(3, note="revised", enabled=True)


def test_blackroom_remove_calls_service():
    bsvc = MagicMock()
    bsvc.remove_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record deleted",
        "data": {"id": 4, "deleted": True},
    }

    exit_code = main(["blackroom", "remove", "--id", "4"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.remove_record.assert_called_once_with(4)


def test_blackroom_list_calls_service():
    bsvc = MagicMock()
    bsvc.list_records.return_value = {
        "success": True,
        "code": "OK",
        "message": "records listed",
        "data": [],
    }

    exit_code = main(["blackroom", "list"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.list_records.assert_called_once_with(enabled=None)


def test_blackroom_list_active_only_passes_enabled_true():
    bsvc = MagicMock()
    bsvc.list_records.return_value = {
        "success": True,
        "code": "OK",
        "message": "records listed",
        "data": [{"id": 1, "stock_code": "600519"}],
    }

    exit_code = main(["blackroom", "list", "--active-only"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.list_records.assert_called_once_with(enabled=True)


def test_blackroom_list_stock_code_filter_applied_client_side(capsys):
    bsvc = MagicMock()
    bsvc.list_records.return_value = {
        "success": True,
        "code": "OK",
        "message": "records listed",
        "data": [
            {"id": 1, "stock_code": "600519"},
            {"id": 2, "stock_code": "000001"},
        ],
    }

    main(
        ["--json", "blackroom", "list", "--stock-code", "600519"],
        blackroom_service=bsvc,
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert len(payload["data"]) == 1
    assert payload["data"][0]["stock_code"] == "600519"


def test_blackroom_get_calls_service():
    bsvc = MagicMock()
    bsvc.get_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record fetched",
        "data": {"id": 7},
    }

    exit_code = main(["blackroom", "get", "--id", "7"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.get_record.assert_called_once_with(7)


def test_blackroom_status_calls_service():
    bsvc = MagicMock()
    bsvc.get_status.return_value = {
        "success": True,
        "code": "OK",
        "message": "status fetched",
        "data": {"total": 3, "enabled": 2, "disabled": 1},
    }

    exit_code = main(["blackroom", "status"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.get_status.assert_called_once_with()


def test_blackroom_validation_error_returns_exit_code_10(capsys):
    bsvc = MagicMock()
    bsvc.add_record.return_value = {
        "success": False,
        "code": "VALIDATION_ERROR",
        "message": "ban_days 必须是正整数",
        "data": None,
    }

    exit_code = main(
        [
            "--json",
            "blackroom",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--ban-days",
            "0",
        ],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"


def test_blackroom_not_found_returns_exit_code_11(capsys):
    bsvc = MagicMock()
    bsvc.get_record.return_value = {
        "success": False,
        "code": "NOT_FOUND",
        "message": "blackroom record not found: 99",
        "data": None,
    }

    exit_code = main(
        ["--json", "blackroom", "get", "--id", "99"], blackroom_service=bsvc
    )

    assert exit_code == EXIT_NOT_FOUND
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "NOT_FOUND"


def test_blackroom_service_exception_returns_exit_code_12(capsys):
    bsvc = MagicMock()
    bsvc.add_record.side_effect = RuntimeError("db down")

    exit_code = main(
        [
            "--json",
            "blackroom",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--ban-days",
            "30",
        ],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_INTERNAL_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "INTERNAL_ERROR"


def test_blackroom_update_bad_start_at_returns_validation_error(capsys):
    bsvc = MagicMock()

    exit_code = main(
        ["--json", "blackroom", "update", "--id", "1", "--start-at", "not-a-date"],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    assert "start-at" in payload["message"]
    bsvc.update_record.assert_not_called()


def test_blackroom_update_bad_expire_at_returns_validation_error(capsys):
    bsvc = MagicMock()

    exit_code = main(
        ["--json", "blackroom", "update", "--id", "1", "--expire-at", "2024-99-99"],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    assert "expire-at" in payload["message"]
    bsvc.update_record.assert_not_called()


def test_blackroom_add_missing_required_args_returns_validation_error(capsys):
    """argparse missing required arg must exit 10, not raw SystemExit(2)."""
    bsvc = MagicMock()

    # omit --market and --ban-days
    exit_code = main(
        ["--json", "blackroom", "add", "--stock-code", "600519"],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    bsvc.add_record.assert_not_called()


def test_blackroom_add_bad_ban_days_type_returns_validation_error(capsys):
    """argparse type=int failure must exit 10, not raw SystemExit(2)."""
    bsvc = MagicMock()

    exit_code = main(
        [
            "--json",
            "blackroom",
            "add",
            "--stock-code",
            "600519",
            "--market",
            "A",
            "--ban-days",
            "not-an-int",
        ],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    bsvc.add_record.assert_not_called()


def test_blackroom_update_missing_id_returns_validation_error(capsys):
    """blackroom update --id is required; missing it must exit 10."""
    bsvc = MagicMock()

    exit_code = main(
        ["--json", "blackroom", "update", "--ban-days", "5"],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    bsvc.update_record.assert_not_called()


def test_blackroom_update_bad_id_type_returns_validation_error(capsys):
    """blackroom update --id type=int failure must exit 10."""
    bsvc = MagicMock()

    exit_code = main(
        ["--json", "blackroom", "update", "--id", "abc", "--ban-days", "5"],
        blackroom_service=bsvc,
    )

    assert exit_code == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["code"] == "VALIDATION_ERROR"
    bsvc.update_record.assert_not_called()


def test_existing_target_commands_unaffected_by_blackroom_changes():
    """Regression: existing target/status commands still work when blackroom_service is absent."""
    svc = MagicMock()
    svc.get_status.return_value = {
        "success": True,
        "code": "OK",
        "message": "status",
        "data": {"total": 0},
    }

    exit_code = main(["status"], service=svc)

    assert exit_code == 0
    svc.get_status.assert_called_once_with()
