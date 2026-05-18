from __future__ import annotations

from dataclasses import dataclass

from storage import get_storage
from utility import send_email

from .ssf_alert import build_ssf_change_alert_email
from .ssf_change_analyzer import analyze_ssf_change


@dataclass
class SSFAlertSummary:
    candidates: int = 0
    inserted: int = 0
    emailed: int = 0


def run_ssf_change_alert() -> SSFAlertSummary:
    storage = get_storage()
    storage.ensure_ssf_change_signals_table()

    summary = SSFAlertSummary()
    candidates = storage.list_ssf_change_signal_candidates()
    summary.candidates = len(candidates)

    signal_payloads = []
    for stock_id, _ in candidates:
        history_df = storage.load_top10_floatholders_history(stock_id)
        signal = analyze_ssf_change(stock_id, history_df)
        if signal is not None:
            signal_payloads.append(signal)

    inserted_ids = storage.save_ssf_change_signals(signal_payloads)
    summary.inserted = len(inserted_ids)

    pending = storage.list_pending_ssf_change_signals()
    if not pending:
        return summary

    ann_date = str(max(item.ann_date for item in pending))
    subject, body = build_ssf_change_alert_email(pending, ann_date)
    send_email(subject, body)
    storage.mark_ssf_change_signals_alerted([item.id for item in pending])
    summary.emailed = len(pending)
    return summary
