from __future__ import annotations

from typing import Sequence

from monitor.blackroom_management_service import BlackroomManagementService


def filter_explicit_buy_codes(
    codes: Sequence[str],
    market: str,
    service: BlackroomManagementService | None = None,
) -> list[str]:
    guard_service = BlackroomManagementService() if service is None else service
    result = guard_service.filter(candidates=list(codes), market=market)
    if not result.get("success"):
        raise RuntimeError(f'{result.get("code")}: {result.get("message")}')

    data = result.get("data") or {}
    allowed = data.get("allowed")
    if not isinstance(allowed, list):
        raise RuntimeError("blackroom filter returned invalid allowed payload")
    return allowed


def should_block_positive_target(
    stock_code: str,
    target: float,
    market: str,
    service: BlackroomManagementService | None = None,
) -> bool:
    if target <= 0:
        return False

    guard_service = BlackroomManagementService() if service is None else service
    result = guard_service.check(stock_code=stock_code, market=market)
    if not result.get("success"):
        raise RuntimeError(f'{result.get("code")}: {result.get("message")}')

    data = result.get("data") or {}
    return bool(data.get("banned"))
