from __future__ import annotations

from typing import Any

import pandas as pd

from common.const import (
    COL_ANN_DATE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
)

from .ssf_detector import is_social_security_holder

EVENT_WEIGHTS = {
    "new_entry": 1.0,
    "increase": 0.7,
    "decrease": -0.7,
    "exit": -1.0,
}
EVENT_ORDER = ["new_entry", "increase", "decrease", "exit"]


def analyze_ssf_change(
    stock_id: str, history_df: pd.DataFrame
) -> dict[str, Any] | None:
    ann_dates = sorted(
        pd.to_datetime(history_df[COL_ANN_DATE]).dt.date.unique(), reverse=True
    )
    if len(ann_dates) < 2:
        return None

    latest_ann_date, prev_ann_date = ann_dates[:2]
    latest_df = history_df[
        pd.to_datetime(history_df[COL_ANN_DATE]).dt.date == latest_ann_date
    ]
    prev_df = history_df[
        pd.to_datetime(history_df[COL_ANN_DATE]).dt.date == prev_ann_date
    ]

    latest_ssf = latest_df[
        latest_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)
    ]
    prev_ssf = prev_df[prev_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)]
    if latest_ssf.empty and prev_ssf.empty:
        return None

    latest_ssf = latest_ssf[latest_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].notna()]
    prev_ssf = prev_ssf[prev_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].notna()]

    latest_map = latest_ssf.set_index(COL_FLOAT_HOLDER_NAME)[
        COL_FLOAT_HOLDER_HOLD_AMOUNT
    ].to_dict()
    prev_map = prev_ssf.set_index(COL_FLOAT_HOLDER_NAME)[
        COL_FLOAT_HOLDER_HOLD_AMOUNT
    ].to_dict()

    event_types: list[str] = []
    detail_rows: list[dict[str, Any]] = []
    for holder_name in sorted(set(latest_map) | set(prev_map)):
        latest_amount = latest_map.get(holder_name)
        prev_amount = prev_map.get(holder_name)
        if prev_amount is None:
            event_type = "new_entry"
        elif latest_amount is None:
            event_type = "exit"
        elif float(latest_amount) > float(prev_amount):
            event_type = "increase"
        elif float(latest_amount) < float(prev_amount):
            event_type = "decrease"
        else:
            continue
        event_types.append(event_type)
        detail_rows.append(
            {
                "holder_name": holder_name,
                "event_type": event_type,
                "latest_amount": latest_amount,
                "prev_amount": prev_amount,
            }
        )

    if not event_types:
        return None

    latest_ratio = float(latest_ssf[COL_FLOAT_HOLDER_HOLD_RATIO].fillna(0).sum())
    prev_ratio = float(prev_ssf[COL_FLOAT_HOLDER_HOLD_RATIO].fillna(0).sum())
    count_now = int(len(latest_ssf))
    count_prev = int(len(prev_ssf))

    event_score = sum(EVENT_WEIGHTS[event] for event in event_types) / len(event_types)
    count_score = min(max((count_now - count_prev) + count_now, 0), 5) / 5
    concentration_score = (
        min(max(latest_ratio - prev_ratio + latest_ratio, 0.0), 5.0) / 5.0
    )
    score = round(50 * event_score + 20 * count_score + 30 * concentration_score, 2)

    return {
        "stock_id": stock_id,
        "ann_date": latest_ann_date.isoformat(),
        "prev_ann_date": prev_ann_date.isoformat(),
        "event_types": [event for event in EVENT_ORDER if event in event_types],
        "score": score,
        "ssf_holder_count_now": count_now,
        "ssf_holder_count_prev": count_prev,
        "ssf_holder_count_change": count_now - count_prev,
        "ssf_total_hold_ratio_now": round(latest_ratio, 4),
        "ssf_total_hold_ratio_prev": round(prev_ratio, 4),
        "ssf_total_hold_ratio_change": round(latest_ratio - prev_ratio, 4),
        "detail_json": {"holders": detail_rows},
    }
