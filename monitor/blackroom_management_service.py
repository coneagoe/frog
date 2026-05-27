"""Service layer for blackroom (global buy-ban) management with validation and stable payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from storage import get_storage


class BlackroomValidationError(ValueError):
    """Raised when blackroom record input is invalid."""


class BlackroomNotFoundError(LookupError):
    """Raised when a blackroom record cannot be found."""


class BlackroomManagementService:
    _ALLOWED_MARKETS = {"A", "HK", "ETF"}
    _ALLOWED_SOURCES = {"manual", "shareholder_reduction"}
    _ALLOWED_UPDATE_FIELDS = {
        "stock_code",
        "market",
        "ban_days",
        "start_at",
        "expire_at",
        "source",
        "note",
        "enabled",
    }

    def __init__(self, storage: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_record(
        self,
        stock_code: str,
        market: str,
        ban_days: Optional[int] = None,
        start_at: Optional[datetime] = None,
        source: str = "manual",
        note: Optional[str] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        try:
            self._validate_stock_code(stock_code)
            self._validate_market(market)
            self._validate_source(source)
            self._validate_ban_days(ban_days)
            self._validate_bool(enabled, "enabled")
            if start_at is not None and not isinstance(start_at, datetime):
                raise BlackroomValidationError("start_at 必须是 datetime 或 None")

            effective_start = start_at if start_at is not None else datetime.now(timezone.utc)

            record = self.storage.create_blackroom_record(
                stock_code=stock_code,
                market=market,
                ban_days=ban_days,
                start_at=effective_start,
                source=source,
                note=note,
                enabled=enabled,
            )
            return self._result(True, "OK", "record created", self._serialize(record))
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    def get_record(self, record_id: int) -> dict[str, Any]:
        try:
            self._validate_record_id(record_id)
            record = self.storage.get_blackroom_record(record_id)
            if record is None:
                raise BlackroomNotFoundError(f"blackroom record not found: {record_id}")
            return self._result(True, "OK", "record fetched", self._serialize(record))
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except BlackroomNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    def list_records(
        self,
        market: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> dict[str, Any]:
        try:
            if market is not None:
                self._validate_market(market)
            if enabled is not None:
                self._validate_bool(enabled, "enabled")
            records = self.storage.list_blackroom_records(market=market, enabled=enabled)
            data = [self._serialize(r) for r in records]
            return self._result(True, "OK", "records listed", data)
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    def update_record(self, record_id: int, **updates: Any) -> dict[str, Any]:
        try:
            self._validate_record_id(record_id)
            if not updates:
                raise BlackroomValidationError("至少需要一个更新字段")

            invalid_fields = set(updates) - self._ALLOWED_UPDATE_FIELDS
            if invalid_fields:
                raise BlackroomValidationError(f"不支持更新字段: {sorted(invalid_fields)}")

            if "stock_code" in updates:
                self._validate_stock_code(updates["stock_code"])
            if "market" in updates:
                self._validate_market(updates["market"])
            if "source" in updates:
                self._validate_source(updates["source"])
            if "ban_days" in updates:
                self._validate_ban_days(updates["ban_days"])
            if "enabled" in updates:
                self._validate_bool(updates["enabled"], "enabled")
            if (
                "start_at" in updates
                and updates["start_at"] is not None
                and not isinstance(updates["start_at"], datetime)
            ):
                raise BlackroomValidationError("start_at 必须是 datetime 或 None")
            if (
                "expire_at" in updates
                and updates["expire_at"] is not None
                and not isinstance(updates["expire_at"], datetime)
            ):
                raise BlackroomValidationError("expire_at 必须是 datetime 或 None")

            record = self.storage.update_blackroom_record(record_id, **updates)
            if record is None:
                raise BlackroomNotFoundError(f"blackroom record not found: {record_id}")
            return self._result(True, "OK", "record updated", self._serialize(record))
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except BlackroomNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    def remove_record(self, record_id: int) -> dict[str, Any]:
        try:
            self._validate_record_id(record_id)
            deleted = self.storage.delete_blackroom_record(record_id)
            if not deleted:
                raise BlackroomNotFoundError(f"blackroom record not found: {record_id}")
            return self._result(True, "OK", "record deleted", {"id": record_id, "deleted": True})
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except BlackroomNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)

    # ------------------------------------------------------------------
    # Buy-ban query helpers
    # ------------------------------------------------------------------

    def filter_buy_candidates(
        self, candidates: List[str], market: str
    ) -> dict[str, Any]:
        try:
            if not isinstance(candidates, list):
                raise BlackroomValidationError("candidates 必须是列表")
            for item in candidates:
                if not isinstance(item, str):
                    raise BlackroomValidationError(
                        f"candidates 中的每个元素必须是字符串, 得到: {type(item).__name__}"
                    )
            self._validate_market(market)

            active = self.storage.list_active_blackroom_records(market=market)
            banned_codes = {getattr(r, "stock_code", None) for r in active}

            allowed = [c for c in candidates if c not in banned_codes]
            banned = [c for c in candidates if c in banned_codes]

            return self._result(
                True,
                "OK",
                "candidates filtered",
                {"allowed": allowed, "banned": banned},
            )
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    def is_buy_banned(self, stock_code: str, market: str) -> dict[str, Any]:
        try:
            self._validate_stock_code(stock_code)
            self._validate_market(market)

            active = self.storage.list_active_blackroom_records(market=market)
            banned_codes = {getattr(r, "stock_code", None) for r in active}
            banned = stock_code in banned_codes

            return self._result(
                True,
                "OK",
                "ban status checked",
                {"stock_code": stock_code, "market": market, "banned": banned},
            )
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)

    # ------------------------------------------------------------------
    # Public short aliases (mirrors target-management-service pattern)
    # ------------------------------------------------------------------

    def add(
        self,
        stock_code: str,
        market: str,
        ban_days: Optional[int] = None,
        start_at: Optional[datetime] = None,
        source: str = "manual",
        note: Optional[str] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        return self.add_record(
            stock_code=stock_code,
            market=market,
            ban_days=ban_days,
            start_at=start_at,
            source=source,
            note=note,
            enabled=enabled,
        )

    def update(self, record_id: int, **updates: Any) -> dict[str, Any]:
        return self.update_record(record_id, **updates)

    def list(
        self,
        market: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> dict[str, Any]:
        return self.list_records(market=market, enabled=enabled)

    def get(self, record_id: int) -> dict[str, Any]:
        return self.get_record(record_id)

    def remove(self, record_id: int) -> dict[str, Any]:
        return self.remove_record(record_id)

    def filter(self, candidates: List[str], market: str) -> dict[str, Any]:
        return self.filter_buy_candidates(candidates=candidates, market=market)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        try:
            records = self.storage.list_blackroom_records(market=None, enabled=None)
            data = {
                "total": len(records),
                "enabled": sum(1 for r in records if getattr(r, "enabled", False)),
                "disabled": sum(1 for r in records if not getattr(r, "enabled", False)),
            }
            return self._result(True, "OK", "status fetched", data)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _result(success: bool, code: str, message: str, data: Any) -> dict[str, Any]:
        return {
            "success": success,
            "code": code,
            "message": message,
            "data": data,
        }

    @staticmethod
    def _validate_record_id(record_id: Any) -> None:
        if type(record_id) is not int or record_id <= 0:
            raise BlackroomValidationError("record_id 必须是正整数")

    @staticmethod
    def _validate_stock_code(stock_code: Any) -> None:
        if not isinstance(stock_code, str) or not stock_code.strip():
            raise BlackroomValidationError("stock_code 不能为空")

    def _validate_market(self, market: Any) -> None:
        if not isinstance(market, str) or market not in self._ALLOWED_MARKETS:
            raise BlackroomValidationError(
                f"market 必须是 {sorted(self._ALLOWED_MARKETS)} 之一"
            )

    def _validate_source(self, source: Any) -> None:
        if not isinstance(source, str) or source not in self._ALLOWED_SOURCES:
            raise BlackroomValidationError(
                f"source 必须是 {sorted(self._ALLOWED_SOURCES)} 之一"
            )

    @staticmethod
    def _validate_ban_days(ban_days: Any) -> None:
        if type(ban_days) is not int or ban_days <= 0:
            raise BlackroomValidationError("ban_days 必须是正整数")

    @staticmethod
    def _validate_bool(value: Any, field_name: str) -> None:
        if not isinstance(value, bool):
            raise BlackroomValidationError(f"{field_name} 必须是布尔值")

    @staticmethod
    def _serialize(record: Any) -> dict[str, Any]:
        return {
            "id": getattr(record, "id", None),
            "stock_code": getattr(record, "stock_code", None),
            "market": getattr(record, "market", None),
            "ban_days": getattr(record, "ban_days", None),
            "start_at": BlackroomManagementService._to_iso(
                getattr(record, "start_at", None)
            ),
            "expire_at": BlackroomManagementService._to_iso(
                getattr(record, "expire_at", None)
            ),
            "source": getattr(record, "source", None),
            "note": getattr(record, "note", None),
            "enabled": getattr(record, "enabled", None),
            "created_at": BlackroomManagementService._to_iso(
                getattr(record, "created_at", None)
            ),
            "updated_at": BlackroomManagementService._to_iso(
                getattr(record, "updated_at", None)
            ),
        }

    @staticmethod
    def _to_iso(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value
