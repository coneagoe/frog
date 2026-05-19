from __future__ import annotations

from datetime import date, datetime
from collections.abc import Mapping
from typing import Any


def _read_signal_value(signal: Any, key: str) -> Any:
    if isinstance(signal, Mapping):
        return signal[key]
    return getattr(signal, key)


def _format_ann_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_ann_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def build_ssf_change_alert_email(signals: list[Any]) -> tuple[str, str]:
    ranked = sorted(
        signals,
        key=lambda item: float(_read_signal_value(item, "score")),
        reverse=True,
    )
    ann_dates = [_parse_ann_date(_read_signal_value(item, "ann_date")) for item in ranked]
    if ann_dates:
        unique_ann_dates = {d.isoformat() for d in ann_dates}
        ann_date_range = (
            _format_ann_date(min(ann_dates))
            if len(unique_ann_dates) == 1
            else f"{_format_ann_date(min(ann_dates))} ~ {_format_ann_date(max(ann_dates))}"
        )
    else:
        ann_date_range = "-"
    subject = f"[社保持仓周报] 本周新增 {len(ranked)} 只，按综合分排序"
    lines = [
        f"待发送信号数: {len(ranked)}",
        f"公告日期范围: {ann_date_range}",
        "排序规则: 按单条信号综合分降序",
        "",
    ]

    for idx, item in enumerate(ranked, start=1):
        stock_id = _read_signal_value(item, "stock_id")
        ann_date = _format_ann_date(_read_signal_value(item, "ann_date"))
        event_types = _read_signal_value(item, "event_types")
        score = _read_signal_value(item, "score")
        count_change = _read_signal_value(item, "ssf_holder_count_change")
        ratio_change = _read_signal_value(item, "ssf_total_hold_ratio_change")
        lines.append(
            f"{idx}. {stock_id} | ann_date={ann_date} | score={score} | events={','.join(event_types)} | "
            f"count_change={count_change} | ratio_change={ratio_change}"
        )

    return subject, "\n".join(lines)
