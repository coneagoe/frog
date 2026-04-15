"""CLI adapter for monitor target management service."""

from __future__ import annotations

import argparse
import json
from typing import Any

from monitor.target_management_service import (
    TargetManagementService,
    TargetNotFoundError,
    TargetValidationError,
)

EXIT_OK = 0
EXIT_VALIDATION_ERROR = 10
EXIT_NOT_FOUND = 11
EXIT_INTERNAL_ERROR = 12

_EXIT_CODE_MAP = {
    "VALIDATION_ERROR": EXIT_VALIDATION_ERROR,
    "NOT_FOUND": EXIT_NOT_FOUND,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock monitor target management CLI")
    parser.add_argument("--json", action="store_true", dest="json_output", help="输出JSON结果")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="添加监控目标")
    add_parser.add_argument("--stock-code", required=True, help="股票代码")
    add_parser.add_argument("--market", required=True, help="市场，例如 A/HK/ETF")
    add_parser.add_argument("--condition", required=True, help="条件JSON字符串")
    add_parser.add_argument("--note", default=None, help="备注")
    add_parser.add_argument("--frequency", default="daily", help="执行频率")
    add_parser.add_argument("--reset-mode", default="auto", help="重置模式")
    add_parser.add_argument("--enabled", action="store_true", default=True, help="启用目标（默认）")
    add_parser.add_argument("--disabled", action="store_false", dest="enabled", help="禁用目标")
    add_parser.add_argument("--last-state", action="store_true", default=False, help="上次状态")

    return parser


def _emit(result: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False))
        return

    print(f"{result.get('code', 'UNKNOWN')}: {result.get('message', '')}")
    if result.get("data") is not None:
        print(json.dumps(result["data"], ensure_ascii=False))


def _to_exit_code(result: dict[str, Any]) -> int:
    if result.get("success"):
        return EXIT_OK
    return _EXIT_CODE_MAP.get(result.get("code"), EXIT_INTERNAL_ERROR)


def main(argv: list[str] | None = None, service: TargetManagementService | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = service or TargetManagementService()

    try:
        if args.command == "add":
            result = service.add_target(
                stock_code=args.stock_code,
                market=args.market,
                condition=args.condition,
                note=args.note,
                frequency=args.frequency,
                reset_mode=args.reset_mode,
                enabled=args.enabled,
                last_state=args.last_state,
            )
        else:
            result = {
                "success": False,
                "code": "VALIDATION_ERROR",
                "message": f"unsupported command: {args.command}",
                "data": None,
            }
    except TargetValidationError as exc:
        result = {"success": False, "code": "VALIDATION_ERROR", "message": str(exc), "data": None}
    except TargetNotFoundError as exc:
        result = {"success": False, "code": "NOT_FOUND", "message": str(exc), "data": None}
    except Exception as exc:
        result = {"success": False, "code": "INTERNAL_ERROR", "message": str(exc), "data": None}

    _emit(result, json_output=args.json_output)
    return _to_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
