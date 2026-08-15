"""Synchronize qualified forecasts into workflow-owned MA20 targets."""

from __future__ import annotations

import re
from datetime import date
from math import isfinite
from typing import Any, cast

import pandas as pd

from common.const import (
    COL_ANN_DATE,
    COL_END_DATE,
    COL_FLOAT_HOLDER_NAME,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_LIST_STATUS,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)
from monitor.blackroom_service import BlackroomService
from storage import get_storage
from top10_floatholder.ssf_detector import is_social_security_holder

WORKFLOW_NAME = "forecast_ssf_ma20"
_CONDITION = {"type": "close_cross_ma", "direction": "above", "period": 20, "workflow": WORKFLOW_NAME}
_NOTE = "业绩预增+社保基金+MA20"
_SUPPORTED_A_SHARE_CODE = re.compile(r"^[036]\d{5}$")


class NoEligibleForecastSnapshotError(RuntimeError):
    """Raised when synchronization has no completed immutable forecast input."""


class ForecastSSFMonitorSyncService:
    def __init__(self, storage: Any = None, blackroom_service: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage
        self.blackroom_service = (
            BlackroomService(storage=self.storage) if blackroom_service is None else blackroom_service
        )

    def sync(self, as_of_date: date) -> dict[str, Any]:
        snapshot = self.storage.get_latest_completed_forecast_snapshot_run(as_of_date)
        if snapshot is None:
            raise NoEligibleForecastSnapshotError(
                f"no completed forecast snapshot eligible as of {as_of_date.isoformat()}"
            )
        forecasts = self.storage.load_selected_forecast_snapshot_records(snapshot.id, as_of_date)
        selected_rows = [cast(dict[str, Any], row) for row in forecasts.to_dict("records")]
        previous_candidates = {
            candidate.stock_code: candidate for candidate in self.storage.list_forecast_ssf_candidates()
        }
        selected_stock_codes = {str(row[COL_STOCK_ID]) for row in selected_rows}
        all_stock_codes = selected_stock_codes | set(previous_candidates)
        listing = self.storage.load_a_stock_listing_status(sorted(all_stock_codes))
        listing_by_code: dict[str, dict[str, Any]] = {
            str(row[COL_STOCK_ID]): cast(dict[str, Any], row) for row in listing.to_dict("records")
        }
        current_rows = [
            row for row in selected_rows if self._qualifies(row, listing_by_code.get(str(row[COL_STOCK_ID])))
        ]
        current_stock_codes = {str(row[COL_STOCK_ID]) for row in current_rows}
        summary = {
            "forecast_candidates": len(current_rows),
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
        for stock_code in current_stock_codes:
            result = self.blackroom_service.is_banned(stock_code, "A")
            if not result.get("success"):
                raise RuntimeError(result.get("message", "blackroom status check failed"))
            blackroom_results[stock_code] = bool((result.get("data") or {}).get("banned"))
        for row in current_rows:
            stock_code = str(row[COL_STOCK_ID])
            self._sync_candidate(
                row=row,
                as_of_date=as_of_date,
                banned=blackroom_results[str(row[COL_STOCK_ID])],
                previous_candidate=previous_candidates.get(str(row[COL_STOCK_ID])),
                summary=summary,
                snapshot=snapshot,
            )
        self._retire_absent_candidates(
            current_stock_codes=current_stock_codes,
            previous_candidates=previous_candidates,
            as_of_date=as_of_date,
            summary=summary,
            listing_by_code=listing_by_code,
            snapshot=snapshot,
            selected_rows_by_code={str(row[COL_STOCK_ID]): row for row in selected_rows},
        )
        return {"success": True, "code": "OK", "message": "forecast SSF monitor targets synchronized", "data": summary}

    def _retire_absent_candidates(
        self,
        current_stock_codes: set[str],
        previous_candidates: dict[str, Any],
        as_of_date: date,
        summary: dict[str, int],
        listing_by_code: dict[str, Any],
        snapshot: Any,
        selected_rows_by_code: dict[str, dict[str, Any]],
    ) -> None:
        for stock_code, candidate in previous_candidates.items():
            if stock_code in current_stock_codes:
                continue
            reason = (
                "delisted_or_unlisted"
                if stock_code not in listing_by_code or listing_by_code[stock_code].get(COL_LIST_STATUS) != "L"
                else "forecast_no_longer_qualified"
            )
            state = "delisted_or_unlisted" if reason == "delisted_or_unlisted" else "ineligible"
            evidence = self._snapshot_evidence(snapshot)
            selected_row = selected_rows_by_code.get(stock_code)
            if selected_row is not None:
                evidence["forecast"] = self._forecast_evidence(selected_row)
            else:
                evidence["forecast"] = {"selected": False, "ann_date": None, "source_order": None}
            evidence = self._with_lifecycle(candidate, evidence, as_of_date, state, reason)
            target_id = getattr(candidate, "monitor_target_id", None)
            if target_id is None:
                self._persist(
                    stock_code,
                    candidate.report_end_date,
                    state,
                    reason,
                    evidence,
                    None,
                    candidate,
                    as_of_date,
                )
                continue
            target = self.storage.find_workflow_monitor_target(stock_code, "A", "daily", WORKFLOW_NAME)
            if target is None or target.id != target_id:
                self._persist(
                    stock_code,
                    candidate.report_end_date,
                    state,
                    reason,
                    evidence,
                    None,
                    candidate,
                    as_of_date,
                )
                continue
            self._delete_target_or_persist(
                stock_code,
                candidate.report_end_date,
                state,
                reason,
                evidence,
                target,
                summary,
                candidate,
                as_of_date,
            )

    def _sync_candidate(
        self,
        row: dict[str, Any],
        as_of_date: date,
        banned: bool,
        previous_candidate: Any | None,
        summary: dict[str, int],
        snapshot: Any,
    ) -> None:
        stock_code = str(row[COL_STOCK_ID])
        report_end_date = self._as_date(row[COL_END_DATE])
        evidence: dict[str, Any] = {
            **self._snapshot_evidence(snapshot),
            "forecast": self._forecast_evidence(row),
            "shareholder": {"ann_date": None, "matched_holder": None},
            "blackroom": {"banned": banned},
        }
        target = self.storage.find_workflow_monitor_target(stock_code, "A", "daily", WORKFLOW_NAME)
        target_found = target is not None
        target_id = getattr(target, "id", None)
        if previous_candidate is None or getattr(previous_candidate, "monitor_target_id", None) != target_id:
            target = None
            target_id = None
        if banned:
            summary["blackroom_excluded"] += 1
            self._delete_target_or_persist(
                stock_code,
                report_end_date,
                "blackroom",
                "active_blackroom",
                evidence,
                target,
                summary,
                previous_candidate,
                as_of_date,
            )
            return
        if previous_candidate is not None and report_end_date > getattr(
            previous_candidate, "report_end_date", report_end_date
        ):
            self._delete_target_or_persist(
                stock_code,
                report_end_date,
                "ineligible",
                "reporting_period_superseded",
                evidence,
                target,
                summary,
                previous_candidate,
                as_of_date,
            )
            return

        try:
            holders = self.storage.load_latest_top10_floatholders(stock_code, as_of_date)
        except Exception:  # noqa: BLE001
            summary["errors"] += 1
            summary["deferred"] += 1
            if getattr(target, "paused", False):
                self._persist_with_target(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_query_failed",
                    evidence,
                    target,
                    False,
                    False,
                    summary,
                    previous_candidate,
                    as_of_date,
                )
            else:
                self._persist(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_query_failed",
                    evidence,
                    target_id,
                    previous_candidate,
                    as_of_date,
                )
            return

        if holders.empty:
            summary["deferred"] += 1
            if getattr(target, "paused", False):
                self._persist_with_target(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_disclosure_missing",
                    evidence,
                    target,
                    False,
                    False,
                    summary,
                    previous_candidate,
                    as_of_date,
                )
            else:
                self._persist(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_disclosure_missing",
                    evidence,
                    target_id,
                    previous_candidate,
                    as_of_date,
                )
            return
        disclosure_date = self._as_date(holders.iloc[0][COL_ANN_DATE])
        evidence["shareholder"]["ann_date"] = disclosure_date.isoformat()
        if disclosure_date < self._two_months_before(as_of_date):
            summary["deferred"] += 1
            if getattr(target, "paused", False):
                self._persist_with_target(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_disclosure_stale",
                    evidence,
                    target,
                    False,
                    False,
                    summary,
                    previous_candidate,
                    as_of_date,
                )
            else:
                self._persist(
                    stock_code,
                    report_end_date,
                    "deferred",
                    "holder_disclosure_stale",
                    evidence,
                    target_id,
                    previous_candidate,
                    as_of_date,
                )
            return

        matched_holder = next(
            (str(name) for name in holders[COL_FLOAT_HOLDER_NAME] if is_social_security_holder(name)), None
        )
        evidence["shareholder"]["matched_holder"] = matched_holder
        if matched_holder is None:
            self._delete_target_or_persist(
                stock_code,
                report_end_date,
                "ineligible",
                "ssf_holder_not_found",
                evidence,
                target,
                summary,
                previous_candidate,
                as_of_date,
            )
            return

        summary["ssf_matched"] += 1
        if target is None and (previous_candidate is not None or target_found):
            self._persist(
                stock_code,
                report_end_date,
                "eligible",
                "ssf_holder_match",
                evidence,
                None,
                previous_candidate,
                as_of_date,
            )
            return
        effective_state = "paused" if getattr(target, "paused", False) else "eligible"
        reset_last_state = target is None or not (
            getattr(previous_candidate, "state", None) == effective_state
            and getattr(previous_candidate, "monitor_target_id", None) == target_id
        )
        automatic_state = "eligible"
        if getattr(target, "paused", False):
            evidence["evaluation"] = {"state": automatic_state, "reason": "ssf_holder_match"}
        updated_target = self.storage.upsert_forecast_ssf_candidate_with_workflow_target(
            stock_code=stock_code,
            market="A",
            report_end_date=report_end_date,
            state="paused" if getattr(target, "paused", False) else automatic_state,
            state_reason="manual_pause" if getattr(target, "paused", False) else "ssf_holder_match",
            evidence=self._with_lifecycle(
                previous_candidate,
                evidence,
                as_of_date,
                "paused" if getattr(target, "paused", False) else automatic_state,
                "manual_pause" if getattr(target, "paused", False) else "ssf_holder_match",
            ),
            workflow=WORKFLOW_NAME,
            frequency="daily",
            condition=_CONDITION,
            note=_NOTE,
            target_enabled=False if getattr(target, "paused", False) else True,
            reset_last_state=reset_last_state,
        )
        target_id = updated_target.id
        if target is None:
            summary["created"] += 1
        elif reset_last_state:
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1

    def _delete_target_or_persist(
        self,
        stock_code: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        target: Any | None,
        summary: dict[str, int],
        previous_candidate: Any | None = None,
        as_of_date: date | None = None,
    ) -> None:
        evidence = self._with_lifecycle(previous_candidate, evidence, as_of_date or date.today(), state, state_reason)
        if state_reason == "reporting_period_superseded" and previous_candidate is not None:
            evidence["lifecycle"].update(
                {
                    "old_report_end_date": self._as_date(previous_candidate.report_end_date).isoformat(),
                    "new_report_end_date": report_end_date.isoformat(),
                }
            )
        if target is not None and self.storage.disable_forecast_ssf_target_with_candidate_transition(
            target.id, state, state_reason, evidence
        ):
            summary["disabled"] += 1
            return
        self._persist(stock_code, report_end_date, state, state_reason, evidence, None)

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
        previous_candidate: Any | None = None,
        as_of_date: date | None = None,
    ) -> None:
        if target is None:
            self._persist(
                stock_code, report_end_date, state, state_reason, evidence, None, previous_candidate, as_of_date
            )
            return
        automatic_state, automatic_reason = state, state_reason
        if getattr(target, "paused", False):
            evidence = dict(evidence)
            evidence["evaluation"] = {"state": automatic_state, "reason": automatic_reason}
            state, state_reason, target_enabled = "paused", "manual_pause", False
        evidence = self._with_lifecycle(previous_candidate, evidence, as_of_date or date.today(), state, state_reason)
        if automatic_reason == "reporting_period_superseded" and previous_candidate is not None:
            evidence["lifecycle"].update(
                {
                    "old_report_end_date": self._as_date(previous_candidate.report_end_date).isoformat(),
                    "new_report_end_date": report_end_date.isoformat(),
                }
            )
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

    def _persist(
        self,
        stock_code: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        monitor_target_id: int | None,
        previous_candidate: Any | None = None,
        as_of_date: date | None = None,
    ) -> None:
        if as_of_date is not None:
            evidence = self._with_lifecycle(previous_candidate, evidence, as_of_date, state, state_reason)
        self.storage.upsert_forecast_ssf_candidate(
            stock_code=stock_code,
            market="A",
            report_end_date=report_end_date,
            state=state,
            state_reason=state_reason,
            evidence=evidence,
            monitor_target_id=monitor_target_id,
        )

    def _with_lifecycle(
        self, previous_candidate: Any | None, evidence: dict[str, Any], as_of_date: date, state: str, reason: str
    ) -> dict[str, Any]:
        result = dict(getattr(previous_candidate, "evidence", None) or {})
        result.update(evidence)
        lifecycle = {"as_of_date": as_of_date.isoformat(), "state": state, "reason": reason}
        previous_state = getattr(previous_candidate, "state", None)
        if previous_state is not None and previous_state != state:
            lifecycle["previous_state"] = previous_state
        result["lifecycle"] = lifecycle
        return result

    @staticmethod
    def _qualifies(row: dict[str, Any], listing: dict[str, Any] | None) -> bool:
        stock_code = str(row.get(COL_STOCK_ID, ""))
        if _SUPPORTED_A_SHARE_CODE.fullmatch(stock_code) is None:
            return False
        if listing is None or listing.get(COL_LIST_STATUS) != "L":
            return False
        if "ST" in str(listing.get(COL_STOCK_NAME, "")).upper():
            return False
        if row.get(COL_FORECAST_TYPE) != "预增":
            return False
        try:
            growth_min = float(row[COL_FORECAST_CHANGE_MIN])
        except (KeyError, TypeError, ValueError):
            return False
        return isfinite(growth_min) and growth_min >= 50

    @staticmethod
    def _snapshot_evidence(snapshot: Any) -> dict[str, Any]:
        return {
            "snapshot": {
                "id": snapshot.id,
                "report_end_date": snapshot.report_end_date.isoformat(),
                "announcement_start_date": snapshot.announcement_start_date.isoformat(),
                "announcement_end_date": snapshot.announcement_end_date.isoformat(),
                "completed_at": snapshot.completed_at.isoformat(),
            }
        }

    def _forecast_evidence(self, row: dict[str, Any]) -> dict[str, Any]:
        growth_min = row[COL_FORECAST_CHANGE_MIN]
        try:
            growth_min = float(growth_min)
        except (TypeError, ValueError):
            pass
        return {
            "report_end_date": self._as_date(row[COL_END_DATE]).isoformat(),
            "ann_date": self._as_date(row[COL_ANN_DATE]).isoformat(),
            "type": str(row[COL_FORECAST_TYPE]),
            "p_change_min": growth_min,
            "source_order": int(row["source_order"]),
        }

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
