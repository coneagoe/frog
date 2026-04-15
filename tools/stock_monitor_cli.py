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

    target_parser = subparsers.add_parser("target", help="监控目标管理")
    target_subparsers = target_parser.add_subparsers(dest="target_command", required=True)

    add_parser = target_subparsers.add_parser("add", help="添加监控目标")
    add_parser.add_argument("--stock-code", required=True, help="股票代码")
    add_parser.add_argument("--market", required=True, help="市场，例如 A/HK/ETF")
    add_parser.add_argument("--condition", required=True, help="条件JSON字符串")
    add_parser.add_argument("--note", default=None, help="备注")
    add_parser.add_argument("--frequency", default="daily", help="执行频率")
    add_parser.add_argument("--reset-mode", default="auto", help="重置模式")
    add_parser.add_argument("--enabled", action="store_true", default=True, help="启用目标（默认）")
    add_parser.add_argument("--disabled", action="store_false", dest="enabled", help="禁用目标")
    add_parser.add_argument("--last-state", action="store_true", default=False, help="上次状态")

    update_parser = target_subparsers.add_parser("update", help="更新监控目标")
    update_parser.add_argument("--target-id", type=int, required=True, help="监控目标ID")
    update_parser.add_argument("--stock-code", default=None, help="股票代码")
    update_parser.add_argument("--market", default=None, help="市场，例如 A/HK/ETF")
    update_parser.add_argument("--condition", default=None, help="条件JSON字符串")
    update_parser.add_argument("--note", default=None, help="备注")
    update_parser.add_argument("--frequency", default=None, help="执行频率")
    update_parser.add_argument("--reset-mode", default=None, help="重置模式")
    update_parser.add_argument(
        "--enabled", action="store_const", const=True, default=None, help="将 enabled 设置为 true"
    )
    update_parser.add_argument("--disabled", action="store_const", const=False, dest="enabled", help="禁用目标")
    update_parser.add_argument("--last-state", action="store_const", const=True, default=None, help="上次状态为 true")
    update_parser.add_argument(
        "--last-state-false",
        action="store_const",
        const=False,
        dest="last_state",
        help="上次状态为 false",
    )

    remove_parser = target_subparsers.add_parser("remove", help="删除监控目标")
    remove_parser.add_argument("--target-id", type=int, required=True, help="监控目标ID")

    list_parser = target_subparsers.add_parser("list", help="列出监控目标")
    list_parser.add_argument("--frequency", default=None, help="执行频率")
    list_parser.add_argument("--enabled", action="store_const", const=True, default=None, help="仅列出启用目标")
    list_parser.add_argument("--disabled", action="store_const", const=False, dest="enabled", help="仅列出禁用目标")

    get_parser = target_subparsers.add_parser("get", help="查询单个监控目标")
    get_parser.add_argument("--target-id", type=int, required=True, help="监控目标ID")

    subparsers.add_parser("status", help="获取监控目标状态汇总")

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
        if args.command == "target":
            if args.target_command == "add":
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
            elif args.target_command == "update":
                updates = {
                    key: value
                    for key, value in {
                        "stock_code": args.stock_code,
                        "market": args.market,
                        "condition": args.condition,
                        "note": args.note,
                        "frequency": args.frequency,
                        "reset_mode": args.reset_mode,
                        "enabled": args.enabled,
                        "last_state": args.last_state,
                    }.items()
                    if value is not None
                }
                result = service.update(args.target_id, **updates)
            elif args.target_command == "remove":
                result = service.remove(args.target_id)
            elif args.target_command == "list":
                result = service.list(frequency=args.frequency, enabled=args.enabled)
            elif args.target_command == "get":
                result = service.get(args.target_id)
            else:
                result = {
                    "success": False,
                    "code": "VALIDATION_ERROR",
                    "message": f"unsupported target command: {args.target_command}",
                    "data": None,
                }
        elif args.command == "status":
            result = service.get_status()
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
