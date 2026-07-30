from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _read_signal_value(signal: Any, key: str) -> Any:
    if isinstance(signal, Mapping):
        return signal[key]
    return getattr(signal, key)


def build_ssf_change_alert_email(signals: list[Any], ann_date: str) -> tuple[str, str]:
    ranked = sorted(
        signals,
        key=lambda item: float(_read_signal_value(item, "score")),
        reverse=True,
    )
    subject = f"[社保持仓变动提醒] {ann_date} 新增 {len(ranked)} 只，按综合分排序"
    lines = [f"公告日期: {ann_date}", ""]

    for idx, item in enumerate(ranked, start=1):
        stock_id = _read_signal_value(item, "stock_id")
        event_types = _read_signal_value(item, "event_types")
        score = _read_signal_value(item, "score")
        count_change = _read_signal_value(item, "ssf_holder_count_change")
        ratio_change = _read_signal_value(item, "ssf_total_hold_ratio_change")
        lines.append(
            f"{idx}. {stock_id} | score={score} | events={','.join(event_types)} | "
            f"count_change={count_change} | ratio_change={ratio_change}"
        )

    return subject, "\n".join(lines)
