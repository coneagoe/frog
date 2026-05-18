from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from storage import get_storage
from utility import send_email

from .ssf_alert import build_ssf_change_alert_email
from .ssf_change_analyzer import analyze_ssf_change

logger = logging.getLogger(__name__)


@dataclass
class SSFAlertSummary:
    candidates: int = 0
    inserted: int = 0
    emailed: int = 0
    no_signal: int = 0
    failed: int = 0


def _build_no_signal_marker(
    stock_id: str, ann_date: str, history_df: pd.DataFrame
) -> dict[str, str]:
    ann_dates = sorted(
        pd.to_datetime(history_df["公告日期"]).dt.date.unique(),
        reverse=True,
    )
    latest_ann_date = pd.to_datetime(ann_date).date()
    prev_ann_date = ann_dates[1] if len(ann_dates) > 1 else latest_ann_date
    return {
        "stock_id": stock_id,
        "ann_date": latest_ann_date.isoformat(),
        "prev_ann_date": prev_ann_date.isoformat(),
    }


def run_ssf_change_alert() -> SSFAlertSummary:
    storage = get_storage()
    storage.ensure_ssf_change_signals_table()

    summary = SSFAlertSummary()
    candidates = storage.list_ssf_change_signal_candidates()
    summary.candidates = len(candidates)

    signal_payloads = []
    no_signal_markers = []
    for stock_id, ann_date in candidates:
        try:
            history_df = storage.load_top10_floatholders_history(stock_id)
            signal = analyze_ssf_change(stock_id, history_df)
            if signal is not None:
                signal_payloads.append(signal)
                continue

            no_signal_markers.append(
                _build_no_signal_marker(stock_id, ann_date, history_df)
            )
        except Exception:
            summary.failed += 1
            logger.exception("Failed to process SSF change candidate %s", stock_id)

    inserted_ids = storage.save_ssf_change_signals(signal_payloads)
    summary.inserted = len(inserted_ids)
    no_signal_ids = storage.mark_ssf_change_candidates_processed(no_signal_markers)
    summary.no_signal = len(no_signal_ids)

    pending = storage.list_pending_ssf_change_signals()
    if not pending:
        return summary

    pending_by_ann_date = defaultdict(list)
    for item in pending:
        pending_by_ann_date[item.ann_date].append(item)

    for ann_date in sorted(pending_by_ann_date, reverse=True):
        grouped_pending = pending_by_ann_date[ann_date]
        subject, body = build_ssf_change_alert_email(grouped_pending, str(ann_date))
        send_email(subject, body)
        # We only mark rows after send_email succeeds so delivery failures stay pending
        # for retry. The tradeoff is that a later DB failure can cause one resend on retry,
        # which is safer than silently losing the alert summary.
        storage.mark_ssf_change_signals_alerted([item.id for item in grouped_pending])

    summary.emailed = len(pending)
    return summary
