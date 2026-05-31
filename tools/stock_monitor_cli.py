"""CLI adapter for monitor target management service."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from monitor.blackroom_management_service import BlackroomManagementService
from monitor.shareholder_reduction_blackroom_sync import (
    ShareholderReductionBlackroomSyncService,
)
from monitor.target_management_service import (
    TargetManagementService,
    TargetNotFoundError,
    TargetValidationError,
)


class _ParserError(Exception):
    """Raised by _StableParser instead of calling sys.exit(2)."""


class _StableParser(argparse.ArgumentParser):
    """ArgumentParser that raises _ParserError on bad/missing args."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ParserError(message)


EXIT_OK = 0
EXIT_VALIDATION_ERROR = 10
EXIT_NOT_FOUND = 11
EXIT_INTERNAL_ERROR = 12

_EXIT_CODE_MAP = {
    "VALIDATION_ERROR": EXIT_VALIDATION_ERROR,
    "NOT_FOUND": EXIT_NOT_FOUND,
    "STORAGE_ERROR": EXIT_INTERNAL_ERROR,
}


def build_parser() -> _StableParser:
    parser = _StableParser(
        description="Stock monitor target management CLI",
        formatter_class=argparse.HelpFormatter,
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="输出JSON结果"
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=_StableParser
    )

    target_parser = subparsers.add_parser("target", help="监控目标管理")
    target_subparsers = target_parser.add_subparsers(
        dest="target_command", required=True, parser_class=_StableParser
    )

    add_parser = target_subparsers.add_parser("add", help="添加监控目标")
    add_parser.add_argument("--stock-code", required=True, help="股票代码")
    add_parser.add_argument("--market", required=True, help="市场，例如 A/HK/ETF")
    add_parser.add_argument("--condition", required=True, help="条件JSON字符串")
    add_parser.add_argument("--note", default=None, help="备注")
    add_parser.add_argument("--frequency", default="daily", help="执行频率")
    add_parser.add_argument("--reset-mode", default="auto", help="重置模式")
    add_parser.add_argument(
        "--enabled", action="store_true", default=True, help="启用目标（默认）"
    )
    add_parser.add_argument(
        "--disabled", action="store_false", dest="enabled", help="禁用目标"
    )
    add_parser.add_argument(
        "--last-state", action="store_true", default=False, help="上次状态"
    )

    update_parser = target_subparsers.add_parser("update", help="更新监控目标")
    update_parser.add_argument(
        "--target-id", type=int, required=True, help="监控目标ID"
    )
    update_parser.add_argument("--stock-code", default=None, help="股票代码")
    update_parser.add_argument("--market", default=None, help="市场，例如 A/HK/ETF")
    update_parser.add_argument("--condition", default=None, help="条件JSON字符串")
    update_parser.add_argument("--note", default=None, help="备注")
    update_parser.add_argument("--frequency", default=None, help="执行频率")
    update_parser.add_argument("--reset-mode", default=None, help="重置模式")
    update_parser.add_argument(
        "--enabled",
        action="store_const",
        const=True,
        default=None,
        help="将 enabled 设置为 true",
    )
    update_parser.add_argument(
        "--disabled", action="store_const", const=False, dest="enabled", help="禁用目标"
    )
    update_parser.add_argument(
        "--last-state",
        action="store_const",
        const=True,
        default=None,
        help="上次状态为 true",
    )
    update_parser.add_argument(
        "--last-state-false",
        action="store_const",
        const=False,
        dest="last_state",
        help="上次状态为 false",
    )

    remove_parser = target_subparsers.add_parser("remove", help="删除监控目标")
    remove_parser.add_argument(
        "--target-id", type=int, required=True, help="监控目标ID"
    )

    list_parser = target_subparsers.add_parser("list", help="列出监控目标")
    list_parser.add_argument("--frequency", default=None, help="执行频率")
    list_parser.add_argument(
        "--enabled",
        action="store_const",
        const=True,
        default=None,
        help="仅列出启用目标",
    )
    list_parser.add_argument(
        "--disabled",
        action="store_const",
        const=False,
        dest="enabled",
        help="仅列出禁用目标",
    )

    get_parser = target_subparsers.add_parser("get", help="查询单个监控目标")
    get_parser.add_argument("--target-id", type=int, required=True, help="监控目标ID")

    subparsers.add_parser("status", help="获取监控目标状态汇总")

    # ------------------------------------------------------------------
    # blackroom subcommand
    # ------------------------------------------------------------------
    blackroom_parser = subparsers.add_parser("blackroom", help="黑屋（全局禁买）管理")
    blackroom_subparsers = blackroom_parser.add_subparsers(
        dest="blackroom_command", required=True, parser_class=_StableParser
    )

    br_add = blackroom_subparsers.add_parser("add", help="添加黑屋记录")
    br_add.add_argument("--stock-code", required=True, help="股票代码")
    br_add.add_argument("--market", required=True, help="市场，例如 A/HK/ETF")
    br_add.add_argument("--ban-days", type=int, required=True, help="禁买天数")
    br_add.add_argument("--note", default=None, help="备注")

    br_update = blackroom_subparsers.add_parser("update", help="更新黑屋记录")
    br_update.add_argument(
        "--id", type=int, required=True, dest="record_id", help="记录ID"
    )
    br_update.add_argument("--ban-days", type=int, default=None, help="禁买天数")
    br_update.add_argument("--note", default=None, help="备注")
    br_update.add_argument(
        "--enabled",
        action="store_const",
        const=True,
        default=None,
        help="启用记录",
    )
    br_update.add_argument(
        "--disabled",
        action="store_const",
        const=False,
        dest="enabled",
        help="禁用记录",
    )
    br_update.add_argument("--start-at", default=None, help="禁买开始时间 (ISO 8601)")
    br_update.add_argument("--expire-at", default=None, help="禁买到期时间 (ISO 8601)")

    br_remove = blackroom_subparsers.add_parser("remove", help="删除黑屋记录")
    br_remove.add_argument(
        "--id", type=int, required=True, dest="record_id", help="记录ID"
    )

    br_list = blackroom_subparsers.add_parser("list", help="列出黑屋记录")
    br_list.add_argument(
        "--active-only",
        action="store_true",
        default=False,
        help="仅列出有效（启用）记录",
    )
    br_list.add_argument("--stock-code", default=None, help="按股票代码过滤")

    br_get = blackroom_subparsers.add_parser("get", help="查询单条黑屋记录")
    br_get.add_argument(
        "--id", type=int, required=True, dest="record_id", help="记录ID"
    )

    blackroom_subparsers.add_parser("status", help="获取黑屋状态汇总")
    br_sync = blackroom_subparsers.add_parser(
        "sync-shareholder-reduction", help="同步股东减持公告到黑屋"
    )
    br_sync.add_argument("--start-date", required=True, help="开始日期 (YYYYMMDD)")
    br_sync.add_argument("--end-date", required=True, help="结束日期 (YYYYMMDD)")
    br_sync.add_argument("--ban-days", type=int, default=180, help="禁买天数")

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


def main(
    argv: list[str] | None = None,
    service: TargetManagementService | None = None,
    blackroom_service: BlackroomManagementService | None = None,
    sync_service: ShareholderReductionBlackroomSyncService | None = None,
) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _ParserError as exc:
        result: dict[str, Any] = {
            "success": False,
            "code": "VALIDATION_ERROR",
            "message": str(exc),
            "data": None,
        }
        effective_argv = argv if argv is not None else sys.argv[1:]
        json_output = "--json" in effective_argv
        _emit(result, json_output=json_output)
        return EXIT_VALIDATION_ERROR

    try:
        if args.command == "target":
            _svc = service or TargetManagementService()
            if args.target_command == "add":
                result = _svc.add_target(
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
                result = _svc.update(args.target_id, **updates)
            elif args.target_command == "remove":
                result = _svc.remove(args.target_id)
            elif args.target_command == "list":
                result = _svc.list(frequency=args.frequency, enabled=args.enabled)
            elif args.target_command == "get":
                result = _svc.get(args.target_id)
            else:
                result = {
                    "success": False,
                    "code": "VALIDATION_ERROR",
                    "message": f"unsupported target command: {args.target_command}",
                    "data": None,
                }
        elif args.command == "status":
            _svc = service or TargetManagementService()
            result = _svc.get_status()
        elif args.command == "blackroom":
            result = _handle_blackroom(
                args,
                blackroom_service,
                sync_service,
            )
        else:
            result = {
                "success": False,
                "code": "VALIDATION_ERROR",
                "message": f"unsupported command: {args.command}",
                "data": None,
            }
    except TargetValidationError as exc:
        result = {
            "success": False,
            "code": "VALIDATION_ERROR",
            "message": str(exc),
            "data": None,
        }
    except TargetNotFoundError as exc:
        result = {
            "success": False,
            "code": "NOT_FOUND",
            "message": str(exc),
            "data": None,
        }
    except Exception as exc:
        result = {
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": str(exc),
            "data": None,
        }

    _emit(result, json_output=args.json_output)
    return _to_exit_code(result)


def _handle_blackroom(
    args: argparse.Namespace,
    bsvc: BlackroomManagementService | None = None,
    sync_service: ShareholderReductionBlackroomSyncService | None = None,
) -> dict[str, Any]:
    cmd = args.blackroom_command

    def _get_bsvc() -> BlackroomManagementService:
        return bsvc or BlackroomManagementService()

    if cmd == "add":
        return _get_bsvc().add_record(
            stock_code=args.stock_code,
            market=args.market,
            ban_days=args.ban_days,
            note=args.note,
        )
    if cmd == "update":
        updates: dict[str, Any] = {}
        if args.ban_days is not None:
            updates["ban_days"] = args.ban_days
        if args.note is not None:
            updates["note"] = args.note
        if args.enabled is not None:
            updates["enabled"] = args.enabled
        if args.start_at is not None:
            try:
                updates["start_at"] = datetime.fromisoformat(args.start_at)
            except ValueError:
                return {
                    "success": False,
                    "code": "VALIDATION_ERROR",
                    "message": f"invalid --start-at value: {args.start_at!r}",
                    "data": None,
                }
        if args.expire_at is not None:
            try:
                updates["expire_at"] = datetime.fromisoformat(args.expire_at)
            except ValueError:
                return {
                    "success": False,
                    "code": "VALIDATION_ERROR",
                    "message": f"invalid --expire-at value: {args.expire_at!r}",
                    "data": None,
                }
        return _get_bsvc().update_record(args.record_id, **updates)
    if cmd == "remove":
        return _get_bsvc().remove_record(args.record_id)
    if cmd == "list":
        enabled_filter = True if args.active_only else None
        result = _get_bsvc().list_records(enabled=enabled_filter)
        if args.stock_code and result.get("data") is not None:
            result = dict(result)
            result["data"] = [
                r for r in result["data"] if r.get("stock_code") == args.stock_code
            ]
        return result
    if cmd == "get":
        return _get_bsvc().get_record(args.record_id)
    if cmd == "status":
        return _get_bsvc().get_status()
    if cmd == "sync-shareholder-reduction":
        effective_sync_service = (
            sync_service
            or ShareholderReductionBlackroomSyncService(blackroom_service=_get_bsvc())
        )
        return effective_sync_service.sync(
            start_date=args.start_date, end_date=args.end_date, ban_days=args.ban_days
        )
    return {
        "success": False,
        "code": "VALIDATION_ERROR",
        "message": f"unsupported blackroom command: {cmd}",
        "data": None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
