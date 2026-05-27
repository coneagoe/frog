from __future__ import annotations

from enum import Enum
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


class SSFChangeAnalysisOutcome(Enum):
    INSUFFICIENT_HISTORY = "insufficient_history"


def _aggregate_period_ssf(period_df: pd.DataFrame) -> pd.DataFrame:
    return period_df.groupby(COL_FLOAT_HOLDER_NAME, as_index=False)[
        [COL_FLOAT_HOLDER_HOLD_AMOUNT, COL_FLOAT_HOLDER_HOLD_RATIO]
    ].sum()


def analyze_ssf_change(
    stock_id: str, history_df: pd.DataFrame
) -> dict[str, Any] | None | SSFChangeAnalysisOutcome:
    """Compare the latest two SSF disclosure periods and rank meaningful changes.

    Score combines four bounded components:
    - event_score: average event weight in [-1, 1] for entry/increase/decrease/exit
    - count_change_score: normalized holder-count delta in [-1, 1]
    - ratio_change_score: normalized SSF total ratio delta in [-1, 1]
    - ratio_level_score: normalized latest SSF total ratio in [0, 1] (small tie-breaker)
    """

    ann_date_series = pd.to_datetime(history_df[COL_ANN_DATE]).dt.date
    ann_dates = sorted(ann_date_series.unique(), reverse=True)
    if len(ann_dates) < 2:
        return SSFChangeAnalysisOutcome.INSUFFICIENT_HISTORY

    latest_ann_date, prev_ann_date = ann_dates[:2]
    latest_df = history_df[ann_date_series == latest_ann_date]
    prev_df = history_df[ann_date_series == prev_ann_date]

    latest_ssf = latest_df[
        latest_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)
    ]
    prev_ssf = prev_df[prev_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)]
    if latest_ssf.empty and prev_ssf.empty:
        return None

    latest_ssf = _aggregate_period_ssf(
        latest_ssf[latest_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].notna()]
    )
    prev_ssf = _aggregate_period_ssf(
        prev_ssf[prev_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].notna()]
    )

    latest_map = dict(
        zip(
            latest_ssf[COL_FLOAT_HOLDER_NAME].astype(str),
            latest_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].astype(float),
        )
    )
    prev_map = dict(
        zip(
            prev_ssf[COL_FLOAT_HOLDER_NAME].astype(str),
            prev_ssf[COL_FLOAT_HOLDER_HOLD_AMOUNT].astype(float),
        )
    )

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
    count_change_score = max(min((count_now - count_prev) / 2.0, 1.0), -1.0)
    ratio_change_score = max(min((latest_ratio - prev_ratio) / 1.5, 1.0), -1.0)
    # Keep latest ratio as a weak tie-breaker and let ratio delta dominate.
    ratio_level_score = max(min(latest_ratio / 5.0, 1.0), 0.0)
    score = round(
        60 * event_score
        + 10 * count_change_score
        + 25 * ratio_change_score
        + 5 * ratio_level_score,
        2,
    )

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
