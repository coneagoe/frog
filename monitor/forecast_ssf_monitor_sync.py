"""Synchronize qualified forecasts into workflow-owned MA20 targets."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pandas as pd

from common.const import (
    COL_ANN_DATE,
    COL_END_DATE,
    COL_FLOAT_HOLDER_NAME,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_STOCK_ID,
)
from monitor.blackroom_service import BlackroomService
from storage import get_storage
from top10_floatholder.ssf_detector import is_social_security_holder

WORKFLOW_NAME = "forecast_ssf_ma20"
_CONDITION = {"type": "price_vs_ma", "direction": "above", "period": 20, "workflow": WORKFLOW_NAME}
_NOTE = "业绩预增+社保基金+MA20"


class ForecastSSFMonitorSyncService:
    def __init__(self, storage: Any = None, blackroom_service: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage
        self.blackroom_service = (
            BlackroomService(storage=self.storage) if blackroom_service is None else blackroom_service
        )

    def sync(self, as_of_date: date) -> dict[str, Any]:
        forecasts = self.storage.load_active_forecast_candidates(as_of_date)
        summary = {
            "forecast_candidates": len(forecasts),
            "blackroom_excluded": 0,
            "ssf_matched": 0,
            "deferred": 0,
            "created": 0,
            "updated": 0,
            "disabled": 0,
            "unchanged": 0,
            "errors": 0,
        }
        blackroom_results: dict[str, bool] = {}
        for raw_row in forecasts.to_dict("records"):
            row = cast(dict[str, Any], raw_row)
            stock_code = str(row[COL_STOCK_ID])
            result = self.blackroom_service.is_banned(stock_code, "A")
            if not result.get("success"):
                raise RuntimeError(result.get("message", "blackroom status check failed"))
            blackroom_results[stock_code] = bool((result.get("data") or {}).get("banned"))

        previous_candidates = {
            candidate.stock_code: candidate for candidate in self.storage.list_forecast_ssf_candidates()
        }
        for raw_row in forecasts.to_dict("records"):
            row = cast(dict[str, Any], raw_row)
            self._sync_candidate(
                row=row,
                as_of_date=as_of_date,
                banned=blackroom_results[str(row[COL_STOCK_ID])],
                previous_candidate=previous_candidates.get(str(row[COL_STOCK_ID])),
                summary=summary,
            )
        self._retire_absent_candidates(
            current_stock_codes={str(row[COL_STOCK_ID]) for row in forecasts.to_dict("records")},
            previous_candidates=previous_candidates,
            as_of_date=as_of_date,
            summary=summary,
        )
        return {"success": True, "code": "OK", "message": "forecast SSF monitor targets synchronized", "data": summary}

    def _retire_absent_candidates(
        self,
        current_stock_codes: set[str],
        previous_candidates: dict[str, Any],
        as_of_date: date,
        summary: dict[str, int],
    ) -> None:
        for stock_code, candidate in previous_candidates.items():
            if stock_code in current_stock_codes:
                continue
            evidence = dict(getattr(candidate, "evidence", None) or {})
            evidence["lifecycle"] = {
                "as_of_date": as_of_date.isoformat(),
                "reason": "forecast_no_longer_qualified",
            }
            target_id = getattr(candidate, "monitor_target_id", None)
            if target_id is None:
                self._persist(
                    stock_code,
                    candidate.report_end_date,
                    "ineligible",
                    "forecast_no_longer_qualified",
                    evidence,
                    None,
                )
                continue
            target = self.storage.find_workflow_monitor_target(stock_code, "A", "daily", WORKFLOW_NAME)
            if target is None or target.id != target_id:
                self._persist(
                    stock_code,
                    candidate.report_end_date,
                    "ineligible",
                    "forecast_no_longer_qualified",
                    evidence,
                    None,
                )
                continue
            self._persist_with_target(
                stock_code,
                candidate.report_end_date,
                "ineligible",
                "forecast_no_longer_qualified",
                evidence,
                target,
                False,
                False,
                summary,
            )

    def _sync_candidate(
        self,
        row: dict[str, Any],
        as_of_date: date,
        banned: bool,
        previous_candidate: Any | None,
        summary: dict[str, int],
    ) -> None:
        stock_code = str(row[COL_STOCK_ID])
        report_end_date = self._as_date(row[COL_END_DATE])
        evidence: dict[str, Any] = {
            "forecast": {
                "report_end_date": report_end_date.isoformat(),
                "ann_date": self._as_date(row[COL_ANN_DATE]).isoformat(),
                "type": str(row[COL_FORECAST_TYPE]),
                "p_change_min": float(row[COL_FORECAST_CHANGE_MIN]),
            },
            "shareholder": {"ann_date": None, "matched_holder": None},
            "blackroom": {"banned": banned},
        }
        target = self.storage.find_workflow_monitor_target(stock_code, "A", "daily", WORKFLOW_NAME)
        target_id = getattr(target, "id", None)
        if banned:
            summary["blackroom_excluded"] += 1
            self._persist_with_target(
                stock_code, report_end_date, "blackroom", "active_blackroom", evidence, target, False, False, summary
            )
            return

        try:
            holders = self.storage.load_latest_top10_floatholders(stock_code)
        except Exception:  # noqa: BLE001
            summary["errors"] += 1
            summary["deferred"] += 1
            self._persist(stock_code, report_end_date, "deferred", "holder_query_failed", evidence, target_id)
            return

        if holders.empty:
            summary["deferred"] += 1
            self._persist(stock_code, report_end_date, "deferred", "holder_disclosure_missing", evidence, target_id)
            return
        disclosure_date = self._as_date(holders.iloc[0][COL_ANN_DATE])
        evidence["shareholder"]["ann_date"] = disclosure_date.isoformat()
        if disclosure_date < self._two_months_before(as_of_date):
            summary["deferred"] += 1
            self._persist(stock_code, report_end_date, "deferred", "holder_disclosure_stale", evidence, target_id)
            return

        matched_holder = next(
            (str(name) for name in holders[COL_FLOAT_HOLDER_NAME] if is_social_security_holder(name)), None
        )
        evidence["shareholder"]["matched_holder"] = matched_holder
        if matched_holder is None:
            self._persist_with_target(
                stock_code,
                report_end_date,
                "ineligible",
                "ssf_holder_not_found",
                evidence,
                target,
                False,
                False,
                summary,
            )
            return

        summary["ssf_matched"] += 1
        reset_last_state = target is None or not (
            getattr(previous_candidate, "state", None) == "eligible"
            and getattr(previous_candidate, "monitor_target_id", None) == target_id
        )
        updated_target = self.storage.upsert_forecast_ssf_candidate_with_workflow_target(
            stock_code=stock_code,
            market="A",
            report_end_date=report_end_date,
            state="eligible",
            state_reason="ssf_holder_match",
            evidence=evidence,
            workflow=WORKFLOW_NAME,
            frequency="daily",
            condition=_CONDITION,
            note=_NOTE,
            target_enabled=True,
            reset_last_state=reset_last_state,
        )
        target_id = updated_target.id
        if target is None:
            summary["created"] += 1
        elif reset_last_state:
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1

    def _persist_with_target(
        self,
        stock_code: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        target: Any | None,
        target_enabled: bool,
        reset_last_state: bool,
        summary: dict[str, int],
    ) -> None:
        if target is None:
            self._persist(stock_code, report_end_date, state, state_reason, evidence, None)
            return
        self.storage.upsert_forecast_ssf_candidate_with_workflow_target(
            stock_code=stock_code,
            market="A",
            report_end_date=report_end_date,
            state=state,
            state_reason=state_reason,
            evidence=evidence,
            frequency="daily",
            workflow=WORKFLOW_NAME,
            condition=_CONDITION,
            note=_NOTE,
            target_enabled=target_enabled,
            reset_last_state=reset_last_state,
        )
        if target.enabled and not target_enabled:
            summary["disabled"] += 1

    def _persist(
        self,
        stock_code: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        monitor_target_id: int | None,
    ) -> None:
        self.storage.upsert_forecast_ssf_candidate(
            stock_code=stock_code,
            market="A",
            report_end_date=report_end_date,
            state=state,
            state_reason=state_reason,
            evidence=evidence,
            monitor_target_id=monitor_target_id,
        )

    @staticmethod
    def _as_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, pd.Timestamp):
            return value
        return pd.Timestamp(value).date()

    @staticmethod
    def _two_months_before(value: date) -> date:
        month = value.month - 2
        year = value.year
        if month <= 0:
            year -= 1
            month += 12
        last_day = pd.Period(f"{year}-{month:02d}").days_in_month
        return date(year, month, min(value.day, last_day))
