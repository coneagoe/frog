"""Sync shareholder-reduction announcements into blackroom bans."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from monitor.blackroom_management_service import BlackroomManagementService


class ShareholderReductionBlackroomSyncService:
    _DATE_PATTERN = re.compile(r"^\d{8}$")

    def __init__(
        self, blackroom_service: BlackroomManagementService | None = None
    ) -> None:
        self.blackroom_service = (
            BlackroomManagementService()
            if blackroom_service is None
            else blackroom_service
        )

    def sync(self, start_date: str, end_date: str, ban_days: int) -> dict[str, Any]:
        try:
            self._validate_date_range(start_date, end_date)
            self._validate_ban_days(ban_days)
        except ValueError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

        try:
            client = self._create_tushare_client()
            data = client.stk_holdertrade(
                start_date=start_date,
                end_date=end_date,
                in_de="DE",
            )

            fetched = len(data) if data is not None else 0
            unique_rows = self._build_unique_rows(data)

            added = 0
            skipped = 0
            records: list[dict[str, Any]] = []

            for row in unique_rows:
                stock_code = row["stock_code"]
                market = row["market"]
                ann_date = row["ann_date"]
                holder_name = row["holder_name"]

                check_result = self.blackroom_service.check(stock_code, market)
                if not check_result.get("success"):
                    return self._propagate_failure(
                        check_result,
                        default_code="BLACKROOM_CHECK_FAILED",
                        default_message="blackroom check failed",
                    )
                banned = bool((check_result.get("data") or {}).get("banned"))
                if banned:
                    skipped += 1
                    continue

                note = f"股东减持公告 {ann_date} / {holder_name}"
                add_result = self.blackroom_service.add(
                    stock_code=stock_code,
                    market=market,
                    ban_days=ban_days,
                    source="shareholder_reduction",
                    note=note,
                )
                if not add_result.get("success"):
                    return self._propagate_failure(
                        add_result,
                        default_code="BLACKROOM_ADD_FAILED",
                        default_message="blackroom add failed",
                    )
                added += 1
                records.append(
                    {
                        "stock_code": stock_code,
                        "market": market,
                        "ann_date": ann_date,
                        "holder_name": holder_name,
                    }
                )

            return self._result(
                True,
                "OK",
                "sync completed",
                {
                    "fetched": fetched,
                    "unique_stocks": len(unique_rows),
                    "added": added,
                    "skipped": skipped,
                    "records": records,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    def _create_tushare_client(self) -> Any:
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("TUSHARE_TOKEN is required")

        import tushare as ts

        return ts.pro_api(token)

    @classmethod
    def _validate_date_range(cls, start_date: Any, end_date: Any) -> None:
        cls._validate_date(start_date, "start_date")
        cls._validate_date(end_date, "end_date")
        if start_date > end_date:
            raise ValueError("start_date 不echo end_date")

    @classmethod
    def _validate_date(cls, value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not cls._DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} 必须是 YYYYMMDD 格式")
        datetime.strptime(value, "%Y%m%d")

    @staticmethod
    def _validate_ban_days(ban_days: Any) -> None:
        if type(ban_days) is not int or ban_days <= 0:
            raise ValueError("ban_days 必须是正整数")

    @staticmethod
    def _normalize_ts_code(ts_code: Any) -> tuple[str, str]:
        if not isinstance(ts_code, str) or "." not in ts_code:
            raise ValueError("ts_code 格式无效")

        stock_code, suffix = ts_code.split(".", 1)
        market = {"SH": "A", "SZ": "A", "BJ": "A", "HK": "HK"}.get(suffix.upper())
        if market is None:
            raise ValueError(f"不支持的 ts_code 市场后缀: {suffix}")
        return stock_code, market

    def _build_unique_rows(self, data: Any) -> list[dict[str, Any]]:
        if data is None or getattr(data, "empty", False):
            return []

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in data.to_dict("records"):
            stock_code, market = self._normalize_ts_code(row.get("ts_code"))
            key = (stock_code, market)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "stock_code": stock_code,
                    "market": market,
                    "ann_date": str(row.get("ann_date") or ""),
                    "holder_name": str(row.get("holder_name") or ""),
                }
            )
        return rows

    @staticmethod
    def _result(success: bool, code: str, message: str, data: Any) -> dict[str, Any]:
        return {
            "success": success,
            "code": code,
            "message": message,
            "data": data,
        }

    def _propagate_failure(
        self, result: dict[str, Any], default_code: str, default_message: str
    ) -> dict[str, Any]:
        return self._result(
            False,
            str(result.get("code") or default_code),
            str(result.get("message") or default_message),
            result.get("data"),
        )
