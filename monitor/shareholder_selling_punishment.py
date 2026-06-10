"""Apply shareholder-selling punishment through blackroom bans."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from monitor.blackroom_service import BlackroomService


class ShareholderSellingPunishmentService:
    _DATE_PATTERN = re.compile(r"^\d{8}$")

    def __init__(self, blackroom_service: BlackroomService | None = None) -> None:
        self.blackroom_service = (
            BlackroomService() if blackroom_service is None else blackroom_service
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
            reset = 0
            skipped = 0
            records: list[dict[str, Any]] = []

            for row in unique_rows:
                stock_code = row["stock_code"]
                market = row["market"]
                ann_date = row["ann_date"]
                holder_name = row["holder_name"]

                try:
                    announcement_start = self._parse_announcement_date(ann_date)
                except ValueError as exc:
                    return self._result(False, "VALIDATION_ERROR", str(exc), None)
                note = f"股东减持公告 {ann_date} / {holder_name}"

                active_result = self.blackroom_service.get_active_record(
                    stock_code, market
                )
                if not active_result.get("success"):
                    return self._propagate_failure(
                        active_result,
                        default_code="BLACKROOM_CHECK_FAILED",
                        default_message="blackroom check failed",
                    )

                active_record = active_result.get("data")
                if active_record:
                    record_id = active_record.get("id")
                    update_result = self.blackroom_service.update_record(
                        record_id,
                        start_at=announcement_start,
                        ban_days=ban_days,
                        remaining_days=ban_days,
                        source="shareholder_selling",
                        note=note,
                    )
                    if not update_result.get("success"):
                        return self._propagate_failure(
                            update_result,
                            default_code="BLACKROOM_UPDATE_FAILED",
                            default_message="blackroom update failed",
                        )
                    reset += 1
                    action = "reset"
                else:
                    add_result = self.blackroom_service.ban(
                        stock_code=stock_code,
                        market=market,
                        ban_days=ban_days,
                        start_at=announcement_start,
                        source="shareholder_selling",
                        note=note,
                    )
                    if not add_result.get("success"):
                        return self._propagate_failure(
                            add_result,
                            default_code="BLACKROOM_ADD_FAILED",
                            default_message="blackroom add failed",
                        )
                    added += 1
                    action = "added"

                records.append(
                    {
                        "stock_code": stock_code,
                        "market": market,
                        "ann_date": ann_date,
                        "holder_name": holder_name,
                        "action": action,
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
                    "reset": reset,
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
            raise ValueError("start_date 不能晚于 end_date")

    @classmethod
    def _validate_date(cls, value: Any, field_name: str) -> None:
        if not isinstance(value, str) or not cls._DATE_PATTERN.match(value):
            raise ValueError(f"{field_name} 必须是 YYYYMMDD 格式")
        datetime.strptime(value, "%Y%m%d")

    @classmethod
    def _parse_announcement_date(cls, value: Any) -> datetime:
        try:
            cls._validate_date(value, "ann_date")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        parsed = datetime.strptime(value, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc)

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

        rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for row in data.to_dict("records"):
            stock_code, market = self._normalize_ts_code(row.get("ts_code"))
            key = (stock_code, market)
            normalized_row = {
                "stock_code": stock_code,
                "market": market,
                "ann_date": str(row.get("ann_date") or ""),
                "holder_name": str(row.get("holder_name") or ""),
            }
            if key not in rows_by_key:
                rows_by_key[key] = normalized_row
                order.append(key)
                continue
            if normalized_row["ann_date"] > rows_by_key[key]["ann_date"]:
                rows_by_key[key] = normalized_row

        return [rows_by_key[key] for key in order]

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
